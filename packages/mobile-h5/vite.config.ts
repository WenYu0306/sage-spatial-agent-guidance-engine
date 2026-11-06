import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 手机端代理：agent(8941) chat/路线缓存；events(8946) 直报；其余 content(8945)
export default defineConfig({
  // base：公网部署在 nginx /m/ 路径下（Dockerfile.admin 注入 VITE_BASE）；本地 dev 保持 /
  base: process.env.VITE_BASE ?? "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5194,
    proxy: {
      "/api/v1/agent": { target: process.env.AGENT_URL ?? "http://localhost:8941", changeOrigin: true },
      "/api/v1/route": { target: process.env.AGENT_URL ?? "http://localhost:8941", changeOrigin: true },
      "/api/v1/events": { target: process.env.ANALYTICS_URL ?? "http://localhost:8946", changeOrigin: true },
      "/api": { target: process.env.CONTENT_SERVICE_URL ?? "http://localhost:8945", changeOrigin: true },
    },
  },
});
