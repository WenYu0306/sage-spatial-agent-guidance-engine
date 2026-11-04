/** 浏览器直报埋点（PRD 7.4：events 免鉴权、event_id 幂等、单批 ≤50）。 */

export interface TrackEvent {
  event_id: string;
  tenant_id: number;
  venue_id: number;
  event_type: string;
  actor_type: string;
  device_id: number | null;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export function buildEvent(input: {
  tenantId: number;
  venueId: number;
  eventType: string;
  deviceId: number | null;
  payload?: Record<string, unknown>;
}): TrackEvent {
  return {
    event_id: crypto.randomUUID(),
    tenant_id: input.tenantId,
    venue_id: input.venueId,
    event_type: input.eventType,
    actor_type: "device",
    device_id: input.deviceId,
    payload: input.payload ?? {},
    occurred_at: new Date().toISOString(),
  };
}

export function trackEvents(events: TrackEvent[], signal?: AbortSignal): void {
  void fetch("/api/v1/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events }),
    keepalive: true,
    signal,
  }).catch(() => undefined); // 遥测失败静默：不干扰交互主链路
}

export function track(event: TrackEvent): void {
  trackEvents([event]);
}
