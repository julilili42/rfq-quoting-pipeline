import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite configuration.
 *
 * The proxy lets the dev server forward `/api/*` to the FastAPI backend
 * on :8000. In production the React app is served by something else
 * (nginx, Caddy, the FastAPI server itself) and the proxy is unused.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
