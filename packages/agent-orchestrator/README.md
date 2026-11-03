# M5 agent-orchestrator — LangGraph Agent 编排

## 做什么

意图解析（LLM 结构化输出）→ 8 工具编排（PRD 8.2，带超时/降级/入参指纹去重）→ 知识引用 → 生成（幻觉三规则 + 店名后置校验）→ SSE 流式输出；每步写 `agent_traces`；多轮：checkpointer（PostgreSQL）thread_id=session_id，且每轮注入会话最近 6 条历史到意图解析（跨轮指代可用）。

## 图结构（LangGraph）

```
START → intent ──→ tools ──→ rag ──→ rank ──→ generate ──→ END
```

- **State（显式 schema，可序列化）**：tenant_id/venue_id/message/trace_id/session_id/message_id、intent、tool_results、tool_calls、degraded、error_codes(append)、citations、answer、cards、turn_started。ToolContext/provider 经 `config["configurable"]` 注入（checkpointer 兼容）
- **intent**：8 类意图，prompt 存 `prompts/intent_system.txt`，JSON Schema 校验失败重试 1 次、再失败回落 fallback（`intent_parse` trace）
- **tools**：按 `TOOL_PLAN` 意图计划表依序执行（数据驱动，非正则路由）；预算 ≤6 次工具调用 / 12s 总耗时，超限标 `degraded`；每步 `tool_call` trace（status/latency/error_code）
- **rag**：从 knowledge.query 结果提取 citations（document_id/标题/片段）
- **rank**：显式占位节点（排序已在 tools 计划步内，保持"一事一节点"）
- **generate**：`prompts/answer_system.txt` 幻觉三规则；后置校验——回答中"店/铺/餐厅/馆/屋/坊"结尾候选（尾 5 字）须匹配本轮工具结果店名，否则记 warning 并降级为列表卡片（`post_validate` trace）
- **条件边**：V1 为线性链（路由逻辑内化在 TOOL_PLAN 数据表中——意图到工具的映射即"条件"，可视化更简单）；checkpointer=PostgresSaver（失败回落 InMemory）

## 对外接口

- `POST /api/v1/agent/chat`：SSE（meta → delta* → card* → citations → done），请求体按 PRD 7.1；错误 1001/1003/3001/3004
- `GET /api/v1/agent/sessions/{id}/trace`：完整 trace 步骤（时间线视图消费）
- `python -m uvicorn agent_orchestrator.app:app --port 8941`

## 如何单独运行（本模块）

```bash
cd packages/agent-orchestrator && make demo   # 进程内 ASGI 内联兄弟服务，无需起端口
make test
```

全链路（三服务 + 评测，仓库根执行；评测前必须 ingest——make seed 只灌文档不灌向量）：

```bash
make compose-up && make migrate && make seed && make ingest
set -a; . ./.env; set +a
uv run --package route-engine uvicorn route_engine.app:app --port 8942 &
uv run --package knowledge-rag uvicorn knowledge_rag.app:app --port 8943 &
uv run --package agent-orchestrator uvicorn agent_orchestrator.app:app --port 8941 &
uv run python scripts/run_agent_eval.py --stage full
```

## 示例（20 问全链路评测，DeepSeek chat + 百炼向量，2026-11-04）

通过率 **90%（18/20）**，PRD 红线 ≥80%。完整表：

| id | 期望意图 | 实际 | 工具链 | 幻觉拦截 | ms | 结论 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| E01-E02 | facility_nearest | ✓ | facility.nearest→route.plan | 否 | ~2.4s | ✓ |
| E03 | poi_search | ✓ | poi.search | 否 | 1.8s | ✓ |
| E04/E13 | poi_recommend | ✓ | poi.search→promotion.list→recommend.rank | E13 拦截一次 | ~2.5s | ✓/✗ |
| E05 | promotion_query | ✓ | promotion.list | 否 | 3.4s | ✓ |
| E06/E10 | navigate | ✓ | route.plan | 否 | ~1.8s | ✓ |
| E07/E09/E20 | venue_info | ✓ | knowledge.query（带引用） | 否 | ~2s | ✓ |
| E08/E12/E17/E18 | poi_search | ✓ | poi.search | 否 | ~1.9s | ✓ |
| E11/E14 | facility_nearest | ✓ | 同 E01 | 否 | ~2.7s | ✓ |
| E15 | venue_info | ✗ poi_search | poi.search | 否 | 3.5s | ✗ 单轮无指代历史 |
| E16 | coupon_claim | ✓ | coupon.claim（幂等） | 否 | 2.1s | ✓ |
| E19 | fallback | ✓ | knowledge.query→兜底话术 | 否 | 2.0s | ✓ |

未命中归因：E15"这家店现在营业吗"依赖上一轮指代（V1 无多轮历史注入，checkpointer 已就位、历史注入随多轮增强）；E13 为幻觉拦截器的一次真实触发（符合设计）。trace JSON 示例见 `docs/trace-example.json`；前端时间线：`pnpm --filter @sage/map-render demo` → `/trace.html`。

## 如何摘出复用到其他项目

三块独立可搬：① `intent.py`（prompt 文件 + JSON Schema 校验 + 重试回落，换枚举即用）；② `tools.py` 的注册表模式（spec 表 + handler + 指纹去重 + 预算循环，与领域无关）；③ `graph.py` 的"计划步"模式——意图到工具序列的映射是纯数据表，加意图不改代码。Provider 抽象在 `platform_core/llm.py`（L0），换供应商只改 env。
