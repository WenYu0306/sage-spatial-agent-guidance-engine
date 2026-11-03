import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
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
