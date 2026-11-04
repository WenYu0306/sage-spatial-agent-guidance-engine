import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 大屏代理：agent(8941) 承接 chat/路线缓存；events(8946) 免鉴权直报；其余 content(8945)
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5192,
    proxy: {
      // 顺序敏感：具体前缀必须先于 /api 命中
      "/api/v1/agent": { target: process.env.AGENT_URL ?? "http://localhost:8941", changeOrigin: true },
      "/api/v1/route": { target: process.env.AGENT_URL ?? "http://localhost:8941", changeOrigin: true },
      "/api/v1/events": { target: process.env.ANALYTICS_URL ?? "http://localhost:8946", changeOrigin: true },
      "/api": { target: process.env.CONTENT_SERVICE_URL ?? "http://localhost:8945", changeOrigin: true },
    },
  },
});
