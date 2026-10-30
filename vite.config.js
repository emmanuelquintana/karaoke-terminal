import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const vercelBuild = mode === "vercel" || process.env.VERCEL === "1";
  const env = loadEnv(mode, process.cwd(), "");
  const apiOrigin = (env.VITE_API_ORIGIN || "").trim().replace(/\/+$/, "");
  if (vercelBuild && !apiOrigin) {
    throw new Error("Configura VITE_API_ORIGIN con la URL HTTPS del backend antes de desplegar en Vercel.");
  }
  if (apiOrigin) {
    const invalidOrigin = "VITE_API_ORIGIN debe ser un origen, por ejemplo https://karaoke-api.onrender.com (sin /api/v1).";
    let url;
    try {
      url = new URL(apiOrigin);
    } catch {
      throw new Error(invalidOrigin);
    }
    if (!["http:", "https:"].includes(url.protocol) || url.pathname !== "/" || apiOrigin.includes("?") || apiOrigin.includes("#") || url.username || url.password) {
      throw new Error(invalidOrigin);
    }
    if (vercelBuild && url.protocol !== "https:") {
      throw new Error("VITE_API_ORIGIN debe usar HTTPS en Vercel.");
    }
  }
  return {
    root: "web",
    envDir: "..",
    base: vercelBuild ? "/" : "/web/",
    plugins: [react()],
    server: {
      proxy: { "/api": "http://127.0.0.1:8765" },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
