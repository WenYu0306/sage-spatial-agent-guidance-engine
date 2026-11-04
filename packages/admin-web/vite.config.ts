import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// M8 content-service（auth+内容端点，8945）；demo 单模块独立：代理走环境变量可换
export default defineConfig({
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
