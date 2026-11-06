import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// M8 content-service（auth+内容端点，8945）；demo 单模块独立：代理走环境变量可换
// base：部署在 nginx /admin/ 路径下（Dockerfile.admin 注入 VITE_BASE）；本地 dev 保持 /
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5191,
    proxy: {
      // 顺序敏感：/api/v1/metrics 必须先于 /api 命中 analytics(8946)
      "/api/v1/metrics": { target: process.env.ANALYTICS_URL ?? "http://localhost:8946", changeOrigin: true },
      "/api": { target: process.env.CONTENT_SERVICE_URL ?? "http://localhost:8945", changeOrigin: true },
      "/recommend": { target: process.env.RECOMMENDER_URL ?? "http://localhost:8944", changeOrigin: true },
    },
  },
});
