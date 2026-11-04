/** SSE 流解析（纯函数状态机，node:test 直测）：喂 chunk → 吐 (event, data)。 */

export type SSEHandler = (event: string, data: string) => void;

export function createSSEParser(onEvent: SSEHandler): (chunk: string) => void {
  let buf = "";
  return (chunk: string) => {
    buf += chunk;
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += (data ? "\n" : "") + line.slice(6);
      }
      if (data) onEvent(event, data);
    }
  };
}
