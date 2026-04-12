import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5899,
    proxy: {
      "/run": { target: "http://localhost:8899", changeOrigin: true },
      "/runs": { target: "http://localhost:8899", changeOrigin: true },
      "/health": { target: "http://localhost:8899", changeOrigin: true },
      "/sessions": { target: "http://localhost:8899", changeOrigin: true },
      "/skills": { target: "http://localhost:8899", changeOrigin: true },
      "/swarm/presets": { target: "http://localhost:8899", changeOrigin: true },
      "/swarm/runs": { target: "http://localhost:8899", changeOrigin: true },
      "/upload": { target: "http://localhost:8899", changeOrigin: true },
      "/api": { target: "http://localhost:8899", changeOrigin: true },
      "/system": { target: "http://localhost:8899", changeOrigin: true },
    },
    hmr: {
      port: 5901,
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }

          if (id.includes("/react/") || id.includes("/react-dom/") || id.includes("/react-router")) {
            return "vendor-react";
          }

          if (id.includes("/echarts/")) {
            return "vendor-charts";
          }

          if (
            id.includes("/react-markdown/")
            || id.includes("/remark-gfm/")
            || id.includes("/rehype-highlight/")
            || id.includes("/highlight.js/")
          ) {
            return "vendor-markdown";
          }

          if (id.includes("/lucide-react/") || id.includes("/zustand/")) {
            return "vendor-ui";
          }
        },
      },
    },
  },
});
