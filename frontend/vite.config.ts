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
      "/auth": { target: "http://localhost:8899", changeOrigin: true },
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
    // Keep prior hashed assets so already-open tabs can still finish lazy imports
    // after a newer build is written to the same dist directory.
    emptyOutDir: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }

          // Core React and routing
          if (id.includes("/react/") || id.includes("/react-dom/") || id.includes("/react-router")) {
            return "vendor-react";
          }

          // Large charting libraries
          if (id.includes("/echarts/")) {
            return "vendor-charts";
          }

          if (id.includes("/@visactor/vchart")) {
            return "vendor-vchart";
          }

          // Mermaid is excluded here to allow its own internal dynamic splitting to work
          // (it generates dozens of small diagram-specific chunks).

          // Markdown and syntax highlighting
          if (
            id.includes("/react-markdown/")
            || id.includes("/remark-gfm/")
            || id.includes("/rehype-highlight/")
            || id.includes("/highlight.js/")
          ) {
            return "vendor-markdown";
          }

          // Common UI utilities
          if (id.includes("/lucide-react/") || id.includes("/zustand/") || id.includes("/clsx/") || id.includes("/tailwind-merge/")) {
            return "vendor-ui";
          }
        },
      },
    },
  },
});
