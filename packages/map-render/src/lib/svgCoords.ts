/** 屏幕坐标 → SVG 用户坐标（viewBox 坐标系）换算与网格约束（纯函数）。 */

export interface SvgPoint {
  x: number;
  y: number;
}

/** 用 SVG 元素的屏幕 CTM 把客户端坐标反解为 SVG 用户坐标（自动含缩放/平移）。 */
export function clientToSvg(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): SvgPoint {
  const ctm = svg.getScreenCTM();
  if (!ctm) throw new Error("SVG 未挂载（getScreenCTM 为空）");
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

/** 网格取整：默认 1 SVG 单位（0.15 米）。 */
export function snap(v: number, step = 1): number {
  return Math.round(v / step) * step;
}

/** viewBox 边界检查（宽高由调用方按底图传入）。 */
export function inBounds(x: number, y: number, w: number, h: number): boolean {
  return x > 0 && x < w && y > 0 && y < h;
}
