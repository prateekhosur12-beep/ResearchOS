import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend serves the built SPA from frontend/dist, so no CORS in production.
// During development, /api is proxied to the FastAPI server.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // SSE needs buffering disabled
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache";
          });
        },
      },
    },
  },
  build: {
    outDir: "../backend/static/ui",
    emptyOutDir: true,
    sourcemap: false,
  },
});
