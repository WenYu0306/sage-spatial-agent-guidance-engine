/** 大屏问答页：SSE 流式（meta/delta/card/citations/route/done）+ 思考动画 + 超时/服务不可用兜底。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { KioskShell } from "../components/ui.tsx";
import type { DeviceIdentity } from "../lib/device.ts";
import { createSSEParser } from "@sage/map-render/src/lib/http/sse.ts";
import type { RoutePayload } from "../lib/route.ts";

const FIRST_EVENT_TIMEOUT_MS = 15_000;

interface PoiCardItem {
  poi_id: number;
  name: string;
  floor?: string;
  distance_meter?: number;
  eta_seconds?: number;
  reasons?: string[];
  coupon?: { title: string } | null;
}

interface ChatMessage {
  role: "user" | "ai";
  text: string;
  cards?: PoiCardItem[];
  route?: RoutePayload;
  degraded?: boolean;
}

type Phase = "idle" | "thinking" | "streaming" | "done" | "error" | "timeout" | "down";

export function Chat({
  session,
  seed,
  onBack,
  onRoute,
}: {
  session: DeviceIdentity;
  seed: string;
  onBack: () => void;
  onRoute: (payload: RoutePayload) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorText, setErrorText] = useState("");
  const [draft, setDraft] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const sentSeedRef = useRef(false);

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || phase === "thinking" || phase === "streaming") return;
    setDraft("");
    setMessages((m) => [...m, { role: "user", text }]);
    setPhase("thinking");
    setErrorText("");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const firstEventTimer = setTimeout(
      () => ctrl.abort(),
      FIRST_EVENT_TIMEOUT_MS,
    );
    let sawFirstEvent = false;
    try {
      const resp = await fetch("/api/v1/agent/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
          "X-Client": "screen",
          "X-Device-Id": String(session.deviceId),
        },
        body: JSON.stringify({
          venue_id: session.venueId,
          device_id: session.deviceId,
          floor_id: session.floorId,
          message: text,
          context: { position_x: session.positionX, position_y: session.positionY },
        }),
        signal: ctrl.signal,
      });
      if (!resp.ok || !resp.body) {
        clearTimeout(firstEventTimer);
        setPhase(resp.status >= 500 || resp.status === 0 ? "down" : "error");
        setErrorText(`服务响应异常（HTTP ${resp.status}）`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      const parser = createSSEParser((event, data) => {
        if (!sawFirstEvent) {
          sawFirstEvent = true;
          clearTimeout(firstEventTimer);
        }
        const payload = JSON.parse(data);
        if (event === "delta") {
          setPhase("streaming");
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last && last.role === "ai") {
              return [...m.slice(0, -1), { ...last, text: last.text + payload.text }];
            }
            return [...m, { role: "ai", text: payload.text }];
          });
        } else if (event === "card" && payload.type === "poi_list") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last && last.role === "ai") {
              return [...m.slice(0, -1), { ...last, cards: payload.items }];
            }
            return [...m, { role: "ai", text: "", cards: payload.items }];
          });
        } else if (event === "route") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last && last.role === "ai") {
              return [...m.slice(0, -1), { ...last, route: payload }];
            }
            return [...m, { role: "ai", text: "", route: payload }];
          });
        } else if (event === "done" && payload.status === "degraded") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last && last.role === "ai") {
              return [...m.slice(0, -1), { ...last, degraded: true }];
            }
            return m;
          });
        }
      });
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parser(decoder.decode(value, { stream: true }));
      }
      setPhase("done");
    } catch (cause) {
      clearTimeout(firstEventTimer);
      if ((cause as Error).name === "AbortError") {
        setPhase(sawFirstEvent ? "done" : "timeout");
        return;
      }
      setPhase("down");
      setErrorText(cause instanceof Error ? cause.message : "网络异常");
    }
  }, [phase, session]);

  useEffect(() => {
    if (!sentSeedRef.current && seed) {
      sentSeedRef.current = true;
      void send(seed);
    }
  }, [seed, send]);
  // 注意：不做 unmount abort——StrictMode 模拟卸载会误杀 seed 自动发送；
  // 挂死由 FIRST_EVENT_TIMEOUT 计时器兜底，离开页面后流完成写入为无害 no-op。

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, phase]);

  const thinking = phase === "thinking";
  return (
    <KioskShell>
      <header className="flex items-center justify-between">
        <button onClick={onBack}
          className="rounded-lg border border-rule bg-paper-2 px-6 py-2 text-xl text-ink-2 hover:bg-paper-3">
          ← 返回首页
        </button>
        <div className="flex items-center gap-3">
          <button disabled title="语音能力未启用（V2）"
            className="rounded-lg border border-rule bg-paper-2 px-5 py-2 text-xl text-muted">语音</button>
          <button disabled title="数字人能力未启用（V2）"
            className="rounded-lg border border-rule bg-paper-2 px-5 py-2 text-xl text-muted">数字人</button>
        </div>
      </header>

      {phase === "down" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="text-5xl">服务暂时不可用</div>
          <div className="text-2xl text-muted">
            您可以前往 {session.venueName} 服务台（F1 中庭）获取帮助
          </div>
          <div className="text-2xl text-muted">营业时间 {session.businessHours ?? "10:00-22:00"}</div>
          <button onClick={onBack}
            className="rounded-xl bg-accent px-10 py-4 text-2xl text-ink hover:bg-accent-deep">
            返回首页
          </button>
        </div>
      ) : phase === "timeout" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="text-5xl">回应超时了</div>
          <div className="text-2xl text-muted">请再试一次，或前往服务台咨询</div>
          <button onClick={onBack}
            className="rounded-xl bg-accent px-10 py-4 text-2xl text-ink hover:bg-accent-deep">
            返回首页
          </button>
        </div>
      ) : (
        <>
          <div ref={listRef} className="mt-6 flex-1 space-y-6 overflow-y-auto pr-2">
            {messages.map((m, i) => (
              <div key={i}
                className={m.role === "user" ? "flex justify-end" : "flex flex-col items-start gap-3"}>
                {m.role === "ai" && (
                  <div className="text-base font-medium tracking-wide text-muted">栖云小雀</div>
                )}
                <div className={
                  m.role === "user"
                    ? "max-w-[70%] rounded-2xl rounded-br-md bg-accent px-6 py-4 text-2xl text-ink"
                    : "max-w-[80%] rounded-2xl rounded-bl-md border border-rule bg-paper-2 px-6 py-4 text-2xl shadow-card"
                }>
                  <div className="whitespace-pre-wrap">{m.text}</div>
                </div>
                {m.cards && m.cards.length > 0 && (
                  <div className="flex max-w-full gap-4 overflow-x-auto pb-2">
                    {m.cards.map((c) => (
                      <div key={c.poi_id}
                        className="min-w-64 rounded-card border border-rule bg-paper-2 p-4 shadow-card">
                        <div className="text-2xl font-semibold text-ink">{c.name}</div>
                        <div className="mt-1 text-xl text-muted">
                          {c.floor ?? ""}层
                          {c.distance_meter != null && ` · ${c.distance_meter}米`}
                          {c.eta_seconds != null && ` · 约${Math.round(c.eta_seconds)}秒`}
                        </div>
                        {c.reasons && c.reasons.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {c.reasons.map((r) => (
                              <span key={r}
                                className="rounded-md border border-rule bg-paper-3 px-2 py-0.5 text-lg text-ink-2">
                                {r}
                              </span>
                            ))}
                          </div>
                        )}
                        {c.coupon && (
                          <div className="mt-2 text-xl font-medium text-accent-deep">券 · {c.coupon.title}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {m.route && (
                  <button
                    onClick={() => onRoute(m.route as RoutePayload)}
                    className="rounded-xl bg-ok px-6 py-3 text-2xl text-white hover:bg-ok/90">
                    查看路线 · {m.route.summary.distance_meter}米 / 约{Math.round(m.route.summary.eta_seconds / 60)}分钟
                  </button>
                )}
                {m.degraded && (
                  <div className="text-xl font-medium text-warn">
                    注意：部分能力降级，结果可能不完整
                  </div>
                )}
              </div>
            ))}
            {thinking && (
              <div className="flex items-center gap-2 px-2">
                {[0, 1, 2].map((i) => (
                  <span key={i}
                    className="size-3 animate-bounce rounded-full bg-accent-deep"
                    style={{ animationDelay: `${i * 150}ms` }} />
                ))}
                <span className="ml-2 text-2xl text-muted">正在思考…</span>
              </div>
            )}
          </div>

          {phase === "error" && (
            <div className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-6 py-3 text-2xl text-danger">
              {errorText || "出错了，请重试"}
            </div>
          )}
          <form
            className="mt-4 flex gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void send(draft);
            }}
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="请输入您的问题，例如：有没有适合情侣吃饭的地方？"
              className="flex-1 rounded-2xl border border-rule bg-paper-2 px-6 py-4 text-2xl outline-none
                         placeholder:text-muted focus:ring-2 focus:ring-accent-deep"
            />
            <button type="submit" disabled={thinking || !draft.trim()}
              className="rounded-2xl bg-accent px-10 text-2xl font-semibold text-ink
                         hover:bg-accent-deep disabled:opacity-40">
              发送
            </button>
          </form>
        </>
      )}
    </KioskShell>
  );
}
