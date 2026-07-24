// 폰 프레임 SSOT 강제 가드.
//
// 라우트로 노출되는 모든 화면은 main-home 프레임 규격에 픽셀 단위로 고정되고 상단바를 갖는다.
// 이 테스트는 각 라우트 화면 소스를 정적으로 검사한다:
//   1) 프레임을 그리는 화면은 공용 클래스 `app-phone-frame` 을 사용한다(치수는 index.css --phone-frame-* SSOT 를 상속).
//   2) 어떤 화면도 프레임 높이 치수(min(844px …))를 인라인 스타일/JSX 로 하드코딩하지 않는다.
//   3) 프레임을 iframe(100vh)에 위임하는 화면은 허용 목록에서만 예외로 둔다.
//
// Vite 의 import.meta.glob(?raw)로 .tsx 원본을 문자열로 읽는다(@types/node 불필요).
// CSS 치수 하드코딩 금지는 문서(frontend/AGENTS.md·CLAUDE.md)와 코드리뷰로 함께 강제한다.

import { describe, expect, it } from "vitest";

const pageTsxModules = import.meta.glob("./pages/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// 프레임을 자체적으로 그리지 않고 100vh iframe 으로 위임하는 라우트 화면.
const IFRAME_FULLSCREEN_PAGES = new Set([
  "ProfileHtmlPage.tsx",
  "SlangiTouchPage.tsx",
]);

function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

function routeScreenEntries(): Array<[string, string]> {
  return Object.entries(pageTsxModules)
    .map(([path, src]) => [basename(path), src] as [string, string])
    .filter(([file]) => file.endsWith(".tsx") && !file.endsWith(".test.tsx"));
}

describe("폰 프레임 SSOT (main-home 기준 픽셀 고정)", () => {
  it("프레임을 그리는 라우트 화면은 공용 app-phone-frame 을 사용한다", () => {
    const offenders: string[] = [];
    for (const [file, source] of routeScreenEntries()) {
      if (IFRAME_FULLSCREEN_PAGES.has(file)) continue;
      const looksLikeScreen = /className="[^"]*-(stage|phone|frame|frame-wrap)/.test(source)
        || source.includes("app-phone-stage");
      if (!looksLikeScreen) continue;
      if (!source.includes("app-phone-frame")) offenders.push(file);
    }
    expect(
      offenders,
      `다음 화면이 공용 app-phone-frame 을 쓰지 않습니다(main-home 프레임 강제): ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("공용 프레임을 쓰는 화면이 최소 하나 이상 존재한다(가드 회귀 방지)", () => {
    const users = routeScreenEntries().filter(([, src]) => src.includes("app-phone-frame"));
    expect(users.length).toBeGreaterThanOrEqual(5);
  });

  it("어떤 라우트 화면도 프레임 높이 치수를 JSX 인라인으로 하드코딩하지 않는다", () => {
    const offenders: string[] = [];
    for (const [file, source] of routeScreenEntries()) {
      if (/min\(\s*844px/.test(source)) offenders.push(file);
    }
    expect(
      offenders,
      `프레임 치수는 index.css --phone-frame-* 변수만 써야 합니다. 인라인 하드코딩: ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});
