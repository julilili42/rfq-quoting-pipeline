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
    // The Review UI runs on 5174 — 5173 belongs to the Outlook add-in dev
    // server. Defaulting to 5173 let a standalone `npm run dev` silently
    // squat the add-in's port (IPv4/IPv6 split → the add-in icon/taskpane
    // loaded only intermittently). strictPort makes a clash fail loudly.
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
