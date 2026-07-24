import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8321" },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 4600,
    rollupOptions: {
      output: {
        manualChunks: { monaco: ["monaco-editor"] },
      },
    },
  },
});
