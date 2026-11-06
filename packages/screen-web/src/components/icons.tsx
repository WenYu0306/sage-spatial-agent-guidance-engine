/** 大屏线性图标（U1-c）：自绘 24px stroke，无图标库依赖（D-023 复制式原则）。 */

function base(props: { className?: string }) {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: props.className ?? "size-10",
    "aria-hidden": true,
  };
}

export function IconChat(props: { className?: string }) {
  return (
    <svg {...base(props)}>
      <path d="M4 5h16v10H10l-6 5V5Z" />
      <path d="M8 9h8M8 12h5" />
    </svg>
  );
}

export function IconMeal(props: { className?: string }) {
  return (
    <svg {...base(props)}>
      <path d="M4 13a8 8 0 0 0 16 0H4Z" />
      <path d="M9 6c0-1 1-1.2 1-2.2M14 6c0-1 1-1.2 1-2.2" />
    </svg>
  );
}

export function IconBag(props: { className?: string }) {
  return (
    <svg {...base(props)}>
      <path d="M6 8h12l-1.2 12H7.2L6 8Z" />
      <path d="M9 10V6a3 3 0 0 1 6 0v4" />
    </svg>
  );
}

export function IconWC(props: { className?: string }) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="4.5" r="1.8" />
      <path d="M12 8v6M7.5 10h9M12 14l-3.5 7M12 14l3.5 7" />
    </svg>
  );
}

export function IconStore(props: { className?: string }) {
  return (
    <svg {...base(props)}>
      <path d="M4 9l1.5-4h13L20 9M5 9v11h14V9" />
      <path d="M4 9c0 1.4 1.2 2.5 2.7 2.5S9.3 10.4 9.3 9c0 1.4 1.2 2.5 2.7 2.5s2.7-1.1 2.7-2.5c0 1.4 1.2 2.5 2.7 2.5S20 10.4 20 9" />
      <path d="M9.5 20v-5h5v5" />
    </svg>
  );
}

/** 楼层色带（多维色板：每层一个专属色，出现在楼层钮/卡片/分段上）。 */
export function floorPillClass(floor: string | null | undefined): string {
  switch ((floor ?? "").toUpperCase()) {
    case "B1":
      return "bg-floor-b1";
    case "F2":
      return "bg-floor-f2";
    default:
      return "bg-floor-f1";
  }
}
