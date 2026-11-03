import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// M8 content-service（auth+内容端点，8945）；demo 单模块独立：代理走环境变量可换
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5191,
    proxy: {
      "/api": { target: process.env.CONTENT_SERVICE_URL ?? "http://localhost:8945", changeOrigin: true },
    },
  },
});
