import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // trace 页同源直连编排服务（U1-f：VITE_ORCH_URL 缺省改同源，CORS 不再依赖浏览器外回填）
      "/api/v1/agent": "http://localhost:8941",
    },
  },
  build: {
    rollupOptions: {
      input: {
        poipicker: resolve(__dirname, "index.html"),
        route: resolve(__dirname, "route.html"),
        trace: resolve(__dirname, "trace.html"),
      },
    },
  },
});
