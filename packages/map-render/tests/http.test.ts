import assert from "node:assert/strict";
import { test } from "node:test";
import { createSSEParser } from "../src/lib/http/sse.ts";
import { buildEvent } from "../src/lib/http/events.ts";

test("createSSEParser：跨 chunk 事件帧与多 data 行", () => {
  const seen: Array<[string, string]> = [];
  const feed = createSSEParser((event, data) => seen.push([event, data]));
  feed('event: met');
  feed('a\ndata: {"session_id": 88}\n\nevent: delta\ndata: {"text": "你');
  feed('好"}\n\n');
  assert.deepEqual(seen, [
    ["meta", '{"session_id": 88}'],
    ["delta", '{"text": "你好"}'],
  ]);
});

test("buildEvent：uuid/时间戳/字段完整", () => {
  const e = buildEvent({ tenantId: 1, venueId: 2, eventType: "ad_impression",
                         deviceId: 3, payload: { x: 1 } });
  assert.equal(e.event_type, "ad_impression");
  assert.equal(e.actor_type, "device");
  assert.equal(e.device_id, 3);
  assert.ok(/^[0-9a-f-]{36}$/.test(e.event_id));
  assert.ok(!Number.isNaN(Date.parse(e.occurred_at)));
});
