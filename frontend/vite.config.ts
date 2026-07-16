import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // host: true → 127.0.0.1·LAN 모두 바인딩(기본값은 IPv6 localhost만). 폰 PWA 테스트도 가능.
  server: { host: true },
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
