// 跨包 import 边界检查（ARCHITECTURE 4.1 第 3 条）。
// 脚手架阶段用 .js 演示文件验证；前端代码落地时再引入 @typescript-eslint（届时登记 REUSE.md）。
import boundaries from "eslint-plugin-boundaries";

const pkgs = ["api-contract", "map-render", "admin-web", "screen-web", "mobile-h5"];

export default [
  {
    ignores: ["**/node_modules/**", "**/dist/**", "packages/api-contract/generated/**"],
  },
  {
    files: pkgs.map((p) => `packages/${p}/**/*.{js,ts,tsx}`),
    plugins: { boundaries },
    settings: {
      "boundaries/elements": pkgs.map((p) => ({ type: p, pattern: `packages/${p}` })),
    },
    rules: {
      // 默认禁止一切跨元素 import；同包（同元素类型）允许
      "boundaries/element-types": [
        "error",
        { default: "disallow", rules: pkgs.map((p) => ({ from: p, allow: [p] })) },
      ],
    },
  },
];
