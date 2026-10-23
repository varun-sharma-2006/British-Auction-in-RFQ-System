import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /api and /ws are proxied to the FastAPI server so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
