import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // envDir: ".." → 레포 루트의 단일 .env 를 참조한다. Vite 는 VITE_ 접두사 변수만
  // 브라우저 번들에 노출하므로, 루트 .env 의 서버 비밀키는 절대 클라이언트로 새지 않는다.
  envDir: "..",
  // host: true → 127.0.0.1·LAN 모두 바인딩(기본값은 IPv6 localhost만). 폰 PWA 테스트도 가능.
  server: { host: true },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      workbox: {
        // Only revisioned build assets enter Cache Storage. API and SSE routes
        // have no runtime rule and are explicitly fetched with cache: no-store.
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff,woff2,webmanifest}"],
        // The supplied standalone benchmark bundle includes large source HTML
        // files that must remain available but are not suitable for precaching.
        globIgnores: ["benchmark-html/**"],
        runtimeCaching: [],
      },
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
