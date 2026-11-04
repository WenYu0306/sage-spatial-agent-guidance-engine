"""agent-orchestrator HTTP 服务（M5-④）：POST /api/v1/agent/chat（SSE）+ trace 查询。

SSE 事件（PRD 7.1）：meta → delta* → card* → citations → done。
demo 阶段 delta 粒度=按句切分（provider.chat 非流式；token 级流式随
chat_stream 增强，README 已注明）。角色校验留 M1 完整版 RBAC。
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.memory import InMemorySaver
from platform_core import trace as trace_mod
from platform_core.config import Settings
from pydantic import BaseModel, Field

from .graph import build_graph
from .tools import ToolContext

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
TENANT_CODE = "shanqueli-demo"
VENUE_NAME = "山雀里·栖云广场"


class ChatRequest(BaseModel):
    session_id: int | None = None
    venue_id: int
    device_id: int | None = None
    floor_id: int | None = None
    message: str = Field(min_length=1, max_length=500)
    anonymous_id: str | None = Field(default=None, max_length=64)
    context: dict | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


ROUTE_TTL_S = 1800  # PRD 872：route_id 缓存 30 分钟，扫码接力不重算


class _RouteCache:
    """route_id → 路线结果：Redis SETEX 为主，内存 TTL 兜底（同 TokenBlacklist 策略）。"""

    _PREFIX = "sage:route:"

    def __init__(self, redis_url: str):
        self._mem: dict[str, tuple[float, str]] = {}
        self._redis = None
        try:
            import redis

            self._redis = redis.Redis.from_url(
                redis_url, socket_connect_timeout=1, socket_timeout=1)
            self._redis.ping()
        except Exception:
            self._redis = None

    def put(self, route_id: int, payload: dict, ttl_s: int = ROUTE_TTL_S) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        if self._redis is not None:
            try:
                self._redis.setex(f"{self._PREFIX}{route_id}", ttl_s, raw)
                return
            except Exception:
                pass
        self._mem[str(route_id)] = (time.monotonic() + ttl_s, raw)

    def get(self, route_id: int) -> dict | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(f"{self._PREFIX}{route_id}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        item = self._mem.get(str(route_id))
        if item is None:
            return None
        expires_at, raw = item
        if time.monotonic() >= expires_at:
            self._mem.pop(str(route_id), None)
            return None
        return json.loads(raw)


def _node_floor(nodes: dict, node_id) -> str | None:
    node = nodes.get(str(node_id)) or nodes.get(node_id) or {}
    return node.get("floor")


def _route_payload(route: dict, venue_id: int, route_id: int) -> dict:
    """PRD 642 结构：summary（floors/transfers 摘要）+ 完整 nodes/segments（大屏直画）。

    route-engine 响应键：node_path、nodes{id:{label,floor,x,y}}、segments{from_id,to_id}。
    """
    nodes = route.get("nodes") or {}
    path = route.get("node_path") or []
    floors: list[str] = []
    for nid in path:
        node = nodes.get(str(nid)) or nodes.get(nid) or {}
        f = node.get("floor")
        if f and f not in floors:
            floors.append(f)
    transfers = [
        {"type": s["edge_type"],
         "from": _node_floor(nodes, s["from_id"]),
         "to": _node_floor(nodes, s["to_id"])}
        for s in route.get("segments", []) if s.get("edge_type") != "walk"
    ]

    def _label(nid) -> str | None:
        node = nodes.get(str(nid)) or nodes.get(nid) or {}
        return node.get("label")

    return {
        "route_id": route_id,
        "venue_id": venue_id,
        "start_label": _label(path[0]) if path else None,
        "goal_label": _label(path[-1]) if path else None,
        "summary": {"distance_meter": route.get("total_distance_meter"),
                    "eta_seconds": route.get("total_time_s"),
                    "floors": floors, "transfers": transfers},
        "nodes": nodes,
        "segments": route.get("segments", []),
    }



def _emit_event(dsn: str, event: dict) -> None:
    """埋点失败不阻断问答（M9 SDK 的容错包装）。"""
    try:
        from platform_core.events import new_event_id, track

        track(dsn, {**event, "event_id": new_event_id()})
    except Exception:  # noqa: BLE001  遥测不拖垮主链路
        pass


def create_app(provider=None, checkpointer=None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    prov = provider
    saver = checkpointer
    graph = None
    http_route = httpx.Client(base_url=settings.route_engine_url, timeout=5)
    http_knowledge = httpx.Client(base_url=settings.knowledge_rag_url, timeout=5)
    http_recommender = httpx.Client(base_url=settings.recommender_url, timeout=5)
    route_cache = _RouteCache(settings.redis_url)

    app = FastAPI(title="agent-orchestrator", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    def _ensure_graph():
        """惰性初始化（TestClient/uvicorn 均可用，不依赖 lifespan 时机）。"""
        nonlocal prov, saver, graph
        if graph is not None:
            return
        from platform_core.llm import make_provider

        prov = prov or make_provider()
        if saver is None:
            try:
                from langgraph.checkpoint.postgres import PostgresSaver

                saver = PostgresSaver.from_conn_string(settings.database_url)
                saver.setup()
            except Exception:
                saver = InMemorySaver()
        graph = build_graph(checkpointer=saver)

    def _resolve_tenant_venue(cur, venue_id: int) -> tuple[int, int] | None:
        cur.execute("select id from tenants where code=%s", (TENANT_CODE,))
        row = cur.fetchone()
        if not row:
            return None
        tid = row[0]
        cur.execute(
            "select id from venues where id=%s and tenant_id=%s", (venue_id, tid)
        )
        if not cur.fetchone():
            return None
        return tid, venue_id

    @app.post("/api/v1/agent/chat")
    def chat(req: ChatRequest):
        if not (1 <= len(req.message) <= 500):
            return JSONResponse(status_code=422,
                                content={"error_code": 1001, "message": "message 长度 1—500"})
        t0 = time.monotonic()
        trace_id = trace_mod.new_trace_id()
        with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
            pair = _resolve_tenant_venue(cur, req.venue_id)
            if not pair:
                return JSONResponse(status_code=200, content={
                    "error_code": 1003, "message": "场地不属于当前租户"})
            tenant_id, venue_id = pair
            if req.session_id:
                cur.execute(
                    "select id from agent_sessions where id=%s and tenant_id=%s and venue_id=%s",
                    (req.session_id, tenant_id, venue_id),
                )
                row = cur.fetchone()
                if not row:
                    return JSONResponse(status_code=200, content={
                        "error_code": 1003, "message": "会话不存在或不属于该场地"})
                session_id = row[0]
            else:
                cur.execute(
                    "insert into agent_sessions (tenant_id, venue_id, device_id, anonymous_id) "
                    "values (%s, %s, %s, %s) returning id",
                    (tenant_id, venue_id, req.device_id, req.anonymous_id),
                )
                session_id = cur.fetchone()[0]
            cur.execute(
                "insert into agent_messages (session_id, tenant_id, role, content) "
                "values (%s, %s, 'user', %s) returning id",
                (session_id, tenant_id, req.message),
            )
            message_id = cur.fetchone()[0]
            cur.execute(
                "select role, content from agent_messages "
                "where session_id=%s and id <= %s order by id desc limit 6",
                (session_id, message_id),
            )
            history = [{"role": r[0], "content": r[1]} for r in reversed(cur.fetchall())]

        pos = {}
        if req.context:
            pos = {"x": req.context.get("position_x"), "y": req.context.get("position_y"),
                   "floor_id": req.floor_id}
        ctx = ToolContext(
            tenant_id=tenant_id, venue_id=venue_id, tenant_code=TENANT_CODE,
            venue_name=VENUE_NAME, dsn=settings.database_url,
            # 测试可经 app.state.http_route 注入内联 transport；生产走 settings 客户端
            http_route=getattr(app.state, "http_route", None) or http_route,
            http_knowledge=http_knowledge,
            http_recommender=http_recommender, position=pos,
            prefer_accessible=bool((req.context or {}).get("prefer_accessible")),
        )

        def stream():
            _ensure_graph()
            yield _sse("meta", {"session_id": session_id, "message_id": message_id,
                                "trace_id": trace_id})
            status, error_code = "ok", None
            try:
                final = graph.invoke(
                    {"tenant_id": tenant_id, "venue_id": venue_id, "message": req.message,
                     "trace_id": trace_id, "session_id": session_id, "message_id": message_id},
                    {"configurable": {"thread_id": session_id, "ctx": ctx, "provider": prov,
                                      "prompts_dir": PROMPTS_DIR,
                                      "anonymous_id": req.anonymous_id,
                                      "history": history},
                     "recursion_limit": 25},
                )
            except Exception:  # 3001：Agent 链路异常 → 兜底话术，不 500 不泄栈
                status, error_code = "error", 3001
                final = {"answer": "我暂时没有这方面的信息，你可以问问商场服务台（F1 层）。",
                         "cards": [], "citations": [], "degraded": True}
            _emit_event(settings.database_url, {
                "tenant_id": tenant_id, "venue_id": venue_id,
                "event_type": "ai_query" if status != "error" else "ai_query_failed",
                "actor_type": "guest", "actor_id": req.anonymous_id,
                "device_id": req.device_id, "session_id": session_id,
                "trace_id": trace_id,
                "payload": {
                    "intent": (final.get("intent") or {}).get("intent"),
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "degraded": final.get("degraded", False),
                    "tool_count": len(final.get("tool_results") or {}),
                    **({"error_code": 3001} if status == "error" else {}),
                },
            })
            for piece in re.split(r"(?<=[。！？!?\n])", final.get("answer", "")):
                if piece.strip():
                    yield _sse("delta", {"text": piece})
            for card in final.get("cards", []):
                yield _sse("card", card)
            route = (final.get("tool_results") or {}).get("route.plan") or {}
            if status == "ok" and route.get("segments"):
                route_id = secrets.randbits(31)
                while route_cache.get(route_id) is not None:
                    route_id = secrets.randbits(31)
                payload = _route_payload(route, venue_id, route_id)
                route_cache.put(route_id, payload)
                floors = payload["summary"]["floors"]
                _emit_event(settings.database_url, {
                    "tenant_id": tenant_id, "venue_id": venue_id,
                    "event_type": "route_plan", "actor_type": "guest",
                    "actor_id": req.anonymous_id, "device_id": req.device_id,
                    "session_id": session_id, "trace_id": trace_id,
                    "payload": {"route_id": route_id,
                                "from_floor": floors[0] if floors else None,
                                "to_floor": floors[-1] if floors else None,
                                "distance_meter": payload["summary"]["distance_meter"]},
                })
                yield _sse("route", payload)
            if final.get("citations"):
                yield _sse("citations", {"items": final["citations"]})
            if status == "ok" and final.get("degraded"):
                status, error_code = "degraded", 3004
            with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into agent_messages (session_id, tenant_id, role, content, structured) "
                    "values (%s, %s, 'assistant', %s, %s)",
                    (session_id, tenant_id, final.get("answer", ""),
                     json.dumps({"cards": final.get("cards", []),
                                 "citations": final.get("citations", [])},
                                ensure_ascii=False)),
                )
                cur.execute(
                    "update agent_sessions set last_active_at = now() where id=%s",
                    (session_id,),
                )
            yield _sse("done", {"status": status, "latency_ms": int((time.monotonic() - t0) * 1000),
                                "degraded": final.get("degraded", False),
                                "error_code": error_code})

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/v1/route/{route_id}")
    def route_by_id(route_id: int):
        """手机扫码接力（F-11/PRD 690）：按 route_id 取缓存路线；过期/不存在 → 404/2005。"""
        payload = route_cache.get(route_id)
        if not payload:
            return JSONResponse(status_code=404, content={
                "error_code": 2005, "message": "路线已过期或不存在，请在大屏重新查询"})
        return payload

    @app.get("/api/v1/agent/sessions/{session_id}/trace")
    def session_trace(session_id: int):
        with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "select id, message_id, trace_id, step_index, step_type, tool_code, "
                "input, output, status, latency_ms, error_code "
                "from agent_traces where session_id=%s order by message_id, step_index",
                (session_id,),
            )
            rows = cur.fetchall()
        return {"steps": [
            {"id": r[0], "message_id": r[1], "trace_id": r[2], "step_index": r[3],
             "step_type": r[4], "tool_code": r[5], "input": r[6], "output": r[7],
             "status": r[8], "latency_ms": r[9], "error_code": r[10]}
            for r in rows
        ]}

    return app


app = create_app()
