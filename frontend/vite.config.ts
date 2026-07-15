import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "연금 코파일럿",
        short_name: "연금코파일럿",
        description: "세 연금계좌의 통합 포트폴리오 운용 가이드",
        display: "standalone",
        start_url: "/",
        theme_color: "#1a4fd8",
        background_color: "#ffffff",
      },
    }),
  ],
});
