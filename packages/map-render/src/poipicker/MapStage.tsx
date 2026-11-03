/** 缩放/拖动舞台：react-zoom-pan-pinch 包裹，内部是分层 SVG。 */

import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

export function MapStage({ children }: { children: React.ReactNode }) {
  return (
    <TransformWrapper
      initialScale={1}
      minScale={0.6}
      maxScale={6}
      centerOnInit
      doubleClick={{ disabled: true }}
    >
      <TransformComponent
        wrapperStyle={{ width: "100%", height: "72vh", background: "#eef2f7" }}
        contentStyle={{ width: "100%" }}
      >
        {children}
      </TransformComponent>
    </TransformWrapper>
  );
}
