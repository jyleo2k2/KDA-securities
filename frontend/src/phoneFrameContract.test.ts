// 폰 프레임 SSOT 강제 가드.
//
// 라우트로 노출되는 모든 화면은 main-home 프레임 규격에 픽셀 단위로 고정되고 상단바를 갖는다.
// 이 테스트는 각 라우트 화면 소스를 정적으로 검사한다:
//   1) 프레임을 그리는 화면은 공용 클래스 `app-phone-frame` 을 사용한다(치수는 index.css --phone-frame-* SSOT 를 상속).
//   2) 어떤 화면도 프레임 높이 치수(min(844px …))를 인라인 스타일/JSX 로 하드코딩하지 않는다.
//   3) 프레임을 iframe(100vh)에 위임하는 화면은 허용 목록에서만 예외로 둔다.
//   4) 프레임을 그리는 화면은 공용 <StatusBar /> 를 렌더한다(상단바 재복사 금지).
//   5) iframe 위임 화면이 품는 HTML 은 상단바에 font-family 를 스스로 지정한다
//      — 지정이 없으면 부모 컨테이너 폰트(Cafe24SsurroundAir 등)를 상속해 시각 글꼴이 화면마다 달라진다.
//
// Vite 의 import.meta.glob(?raw)로 .tsx 원본을 문자열로 읽는다(@types/node 불필요).
// CSS 치수 하드코딩 금지는 문서(frontend/AGENTS.md·CLAUDE.md)와 코드리뷰로 함께 강제한다.

import { describe, expect, it } from "vitest";

const pageTsxModules = import.meta.glob("./pages/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// 라우트에서 실제로 띄우는 iframe HTML(public/) 원본. 상단바를 자체 소유하므로 같은 규격을 직접 검사한다.
const embeddedHtmlModules = import.meta.glob(
  [
    "../public/profile-html/index.html",
    "../public/slangi/index.html",
    "../public/benchmark-html/투자 벤치마킹.dc.html",
    "../public/pension-calculator-html/연금계산기.dc.html",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

// 프레임을 자체적으로 그리지 않고 100vh iframe 으로 위임하는 라우트 화면.
const IFRAME_FULLSCREEN_PAGES = new Set([
  "ProfileHtmlPage.tsx",
  "SlangiTouchPage.tsx",
]);

// 프레임은 공용 클래스로 그리되 상단바는 내부 iframe HTML 이 소유하는 화면.
const IFRAME_STATUSBAR_PAGES = new Set([
  "PensionPlannerPage.tsx",
  "UserPickBenchmarkScreen.tsx",
]);

function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

// 시각("9:41")을 품은 상단바 컨테이너의 여는 태그만 뽑는다.
// 인라인 style 형(벤치마킹·계산기·profile)과 id + CSS 규칙 형(slangi)을 모두 잡기 위해,
// 시각 직전에서 가장 가까운 <div/<span 여는 태그를 역방향으로 찾는다.
function statusBarTags(html: string): string[] {
  const tags: string[] = [];
  for (const chunk of html.split("9:41").slice(0, -1)) {
    // 시각을 감싼 <span>…을 건너뛰고 그 바깥 컨테이너 태그를 고른다.
    const opens = chunk.match(/<(?:div|span)\b[^>]*>/g) ?? [];
    const container = opens.reverse().find((tag) => !/<span\b[^>]*>$/.test(tag)) ?? opens[0];
    if (container !== undefined) tags.push(container);
  }
  return tags;
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

describe("상단바 SSOT (main-home 기준 통일)", () => {
  it("프레임을 그리는 라우트 화면은 공용 StatusBar 를 렌더한다", () => {
    const offenders: string[] = [];
    for (const [file, source] of routeScreenEntries()) {
      if (IFRAME_FULLSCREEN_PAGES.has(file) || IFRAME_STATUSBAR_PAGES.has(file)) continue;
      if (!source.includes("app-phone-frame")) continue;
      if (!source.includes("<StatusBar")) offenders.push(file);
    }
    expect(
      offenders,
      `새 화면은 <StatusBar /> 를 렌더하거나(권장) iframe 위임 목록에 등록해야 합니다: ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("라우트 화면은 상단바 아이콘 path 를 자체 복사하지 않는다", () => {
    // 셀룰러 신호 첫 막대 path — StatusBar.tsx 밖에서 다시 나타나면 상단바를 손으로 복제한 것이다.
    const signalPath = "M10 3c0-.552.448-1 1-1h1c.552 0";
    const offenders = routeScreenEntries()
      .filter(([, source]) => source.includes(signalPath))
      .map(([file]) => file);
    expect(
      offenders,
      `상단바 아이콘은 components/StatusBar.tsx 만 소유합니다. 복사한 화면: ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("iframe 화면의 상단바도 main-home 과 같은 시스템 글꼴을 스스로 지정한다", () => {
    const offenders: string[] = [];
    for (const [path, html] of Object.entries(embeddedHtmlModules)) {
      const bars = statusBarTags(html);
      if (bars.length === 0) continue;
      const declaresFont = bars.every((tag) => {
        if (/font-family/.test(tag)) return true;
        const id = /id="([^"]+)"/.exec(tag)?.[1];
        return id !== undefined && new RegExp(`#${id}\\s*\\{[^}]*font-family`).test(html);
      });
      if (!declaresFont) offenders.push(basename(path));
    }
    expect(
      offenders,
      `상단바에 font-family 가 없으면 부모 폰트를 상속해 시각 글꼴이 어긋납니다: ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});
