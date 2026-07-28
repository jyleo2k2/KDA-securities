// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authMocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  unsubscribe: vi.fn(),
}));

vi.mock("../auth/supabase", () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      getSession: authMocks.getSession,
      onAuthStateChange: authMocks.onAuthStateChange,
    },
  },
}));

import {
  chatGuideStorageKey,
  firstUseGuideStorageKey,
  FirstUseGuide,
  pensionPlannerGuideStorageKey,
  strategyDetailGuideStorageKey,
  userPickGuideStorageKey,
} from "./FirstUseGuide";

const TARGET_USER_ID = "81294832-0880-45c9-8b9e-6ae4de58ac42";
let authStateChangeListener:
  | ((event: string, session: ReturnType<typeof authSession> | null) => void)
  | null = null;

function authSession(email: string, id = TARGET_USER_ID) {
  return {
    user: { email, id },
  };
}

function rect(
  top: number,
  left: number,
  width: number,
  height: number,
): DOMRect {
  return {
    bottom: top + height,
    height,
    left,
    right: left + width,
    top,
    width,
    x: left,
    y: top,
    toJSON: () => ({}),
  };
}

function addHomeFixture(onUserPick: () => void): void {
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <section class="mhs-phone">
        <div class="mhs-page">
          <div class="mhs-body">
            <p class="mhs-asset-total">100,000,000원</p>
            <div class="mhs-pie-wrap">자산 구성</div>
            <button class="mhs-summary-cta-button" type="button">내 구성 진단받기</button>
            <h2 class="mhs-section-title">세액공제</h2>
            <div class="mhs-tax-card">세액공제</div>
            <button class="mhs-promo-dot" type="button" aria-label="1번째 카드 보기"></button>
            <div class="mhs-strategy-scroll">전략별 계획수익률</div>
            <button class="mhs-userpick-card-button" type="button">지금 둘러보기</button>
          </div>
        </div>
      </section>
    `,
  );
  const phone = document.querySelector(".mhs-phone") as HTMLElement;
  const total = document.querySelector(".mhs-asset-total") as HTMLElement;
  const pie = document.querySelector(".mhs-pie-wrap") as HTMLElement;
  const diagnosis = document.querySelector(".mhs-summary-cta-button") as HTMLElement;
  const tax = document.querySelector(".mhs-tax-card") as HTMLElement;
  const strategy = document.querySelector(".mhs-strategy-scroll") as HTMLElement;
  const userPick = document.querySelector(".mhs-userpick-card-button") as HTMLElement;
  phone.getBoundingClientRect = () => rect(0, 0, 390, 844);
  total.getBoundingClientRect = () => rect(160, 24, 220, 44);
  pie.getBoundingClientRect = () => rect(240, 24, 342, 180);
  diagnosis.getBoundingClientRect = () => rect(590, 130, 220, 44);
  tax.getBoundingClientRect = () => rect(680, 24, 342, 150);
  strategy.getBoundingClientRect = () => rect(860, 24, 342, 190);
  userPick.getBoundingClientRect = () => rect(1080, 24, 342, 180);
  total.scrollIntoView = vi.fn();
  pie.scrollIntoView = vi.fn();
  diagnosis.scrollIntoView = vi.fn();
  tax.scrollIntoView = vi.fn();
  strategy.scrollIntoView = vi.fn();
  userPick.scrollIntoView = vi.fn();
  userPick.addEventListener("click", onUserPick);
}

function addStrategyDetailFixture(): void {
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <section class="sd-phone">
        <header class="sd-header">연금 도우미</header>
        <div class="sd-scroll">
          <div class="sd-hero">팩터 전략</div>
          <section class="sd-allocation-example">연금계좌 자산배분 예시</section>
          <section class="sd-card sd-operation-guide">전략의 운용 방식</section>
          <section class="sd-card sd-account-guide">연금계좌에는 이렇게 나눠요</section>
          <section class="sd-card sd-words">핵심 용어 풀이</section>
        </div>
      </section>
    `,
  );
  const phone = document.querySelector(".sd-phone") as HTMLElement;
  const hero = document.querySelector(".sd-hero") as HTMLElement;
  const allocation = document.querySelector(".sd-allocation-example") as HTMLElement;
  const operation = document.querySelector(".sd-operation-guide") as HTMLElement;
  const account = document.querySelector(".sd-account-guide") as HTMLElement;
  const words = document.querySelector(".sd-words") as HTMLElement;
  phone.getBoundingClientRect = () => rect(0, 0, 390, 844);
  hero.getBoundingClientRect = () => rect(110, 22, 346, 150);
  allocation.getBoundingClientRect = () => rect(280, 22, 346, 260);
  operation.getBoundingClientRect = () => rect(560, 22, 346, 150);
  account.getBoundingClientRect = () => rect(730, 22, 346, 180);
  words.getBoundingClientRect = () => rect(930, 22, 346, 210);
  hero.scrollIntoView = vi.fn();
  allocation.scrollIntoView = vi.fn();
  operation.scrollIntoView = vi.fn();
  account.scrollIntoView = vi.fn();
  words.scrollIntoView = vi.fn();
}

function addChatFixture(): void {
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <section class="guide-phone">
        <div class="ios-statusbar">9:41</div>
        <div class="app-shell">
          <main class="chat-main">
            <div class="conversation">
              <div class="welcome design-welcome">
                <div class="design-brand">
                  <img class="design-brand-avatar" alt="" />
                  <strong>연그미</strong>
                </div>
                <div class="welcome-intro-cards">
                  <section class="rebalancing-reminder-card">리밸런싱 점검</section>
                </div>
                <section class="chat-home-card-section">추천 질문</section>
                <section class="chat-home-card-section etf-theme-section">ETF 테마</section>
              </div>
            </div>
            <div class="composer-wrap">연금에 대해 무엇이든 물어보세요</div>
          </main>
        </div>
      </section>
    `,
  );
  const phone = document.querySelector(".guide-phone") as HTMLElement;
  const appShell = document.querySelector(".app-shell") as HTMLElement;
  const brand = document.querySelector(".design-brand") as HTMLElement;
  const reminder = document.querySelector(".rebalancing-reminder-card") as HTMLElement;
  const recommendations = document.querySelector(
    ".chat-home-card-section:not(.etf-theme-section)",
  ) as HTMLElement;
  const themes = document.querySelector(".etf-theme-section") as HTMLElement;
  const composer = document.querySelector(".composer-wrap") as HTMLElement;
  phone.getBoundingClientRect = () => rect(0, 0, 390, 844);
  appShell.getBoundingClientRect = () => rect(54, 0, 390, 790);
  brand.getBoundingClientRect = () => rect(140, 22, 346, 48);
  reminder.getBoundingClientRect = () => rect(205, 22, 346, 150);
  recommendations.getBoundingClientRect = () => rect(530, 22, 346, 210);
  themes.getBoundingClientRect = () => rect(760, 22, 346, 240);
  composer.getBoundingClientRect = () => rect(770, 18, 354, 68);
  brand.scrollIntoView = vi.fn();
  reminder.scrollIntoView = vi.fn();
  recommendations.scrollIntoView = vi.fn();
  themes.scrollIntoView = vi.fn();
  composer.scrollIntoView = vi.fn();
}

function addPensionPlannerFixture(onTaxTab: () => void): void {
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <section class="pension-planner-frame">
        <iframe title="예상 연금 계산 및 세액공제 확인"></iframe>
      </section>
    `,
  );
  const frame = document.querySelector("iframe") as HTMLIFrameElement;
  const frameDocument = frame.contentDocument;
  if (!frameDocument) throw new Error("iframe document is unavailable");
  frameDocument.body.innerHTML = `
    <div id="pension-phone">
      <div class="scrolly">
        <div>예상 연금 계산 및 세액공제 확인</div>
        <div>
          <div>예상 연금</div>
          <div data-tax-tab>세액공제</div>
        </div>
        <div data-pension-savings-card>
          <input class="brand-range" type="range" max="600" />
        </div>
        <div data-irp-card>
          <input class="brand-range tax-range-irp" type="range" max="900" />
        </div>
        <div data-isa-card>
          <input class="brand-range" type="range" max="3000" />
        </div>
      </div>
    </div>
  `;
  const phone = frameDocument.querySelector("#pension-phone") as HTMLElement;
  const taxTab = frameDocument.querySelector("[data-tax-tab]") as HTMLElement;
  const pensionSavings = frameDocument.querySelector(
    ".brand-range[max=\"600\"]",
  ) as HTMLElement;
  const irp = frameDocument.querySelector(".tax-range-irp") as HTMLElement;
  const isa = frameDocument.querySelector(
    ".brand-range[max=\"3000\"]",
  ) as HTMLElement;
  const pensionSavingsCard = pensionSavings.parentElement as HTMLElement;
  const irpCard = irp.parentElement as HTMLElement;
  const isaCard = isa.parentElement as HTMLElement;
  phone.getBoundingClientRect = () => rect(0, 0, 390, 844);
  taxTab.getBoundingClientRect = () => rect(110, 195, 170, 48);
  pensionSavingsCard.getBoundingClientRect = () => rect(260, 16, 358, 220);
  irpCard.getBoundingClientRect = () => rect(496, 16, 358, 240);
  isaCard.getBoundingClientRect = () => rect(752, 16, 358, 260);
  taxTab.scrollIntoView = vi.fn();
  pensionSavingsCard.scrollIntoView = vi.fn();
  irpCard.scrollIntoView = vi.fn();
  isaCard.scrollIntoView = vi.fn();
  taxTab.addEventListener("click", onTaxTab);
}

function addUserPickFixture(
  onPortfolioOpen: () => void,
  onDetailOpen: () => void,
): void {
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <section class="benchmark-html-frame-wrap">
        <iframe title="투자 벤치마킹하기"></iframe>
      </section>
    `,
  );
  const frame = document.querySelector("iframe") as HTMLIFrameElement;
  const frameDocument = frame.contentDocument;
  if (!frameDocument) throw new Error("iframe document is unavailable");
  frameDocument.body.innerHTML = `
    <x-dc style="display:none">
      <div style="cursor:pointer"><span>꾸준한거북이</span></div>
      <div style="cursor:pointer">상세히 보기</div>
      <div>내 포트폴리오와 비교</div>
      <div>운용근거</div>
    </x-dc>
    <div id="benchmark-phone"></div>
  `;
  const phone = frameDocument.querySelector("#benchmark-phone") as HTMLElement;
  phone.getBoundingClientRect = () => rect(0, 0, 390, 844);

  const renderDetail = () => {
    phone.innerHTML = `
      <div style="position: absolute; inset: 0; z-index: 30">
        <header><svg data-close-detail style="cursor: pointer"></svg></header>
        <div class="scrolly">
          <section data-rationale style="background: #fff; border:1.5px solid #C9EBD4; border-radius: 18px">
            <div>운용근거</div>
            <div>이 전략을 고른 이유</div>
            <div>언제 다시 맞추냐면요</div>
          </section>
          <div
            data-review-heading
            style="display: flex; align-items: center; gap: 7px"
          >
            따라하기 후기
          </div>
          <section data-review style="background: #fff; border-radius: 18px">
            <div>장기러버</div>
            <div>8개월째 따라하는 중</div>
          </section>
        </div>
      </div>
    `;
    const rationale = frameDocument.querySelector(
      "[data-rationale]",
    ) as HTMLElement;
    const review = frameDocument.querySelector(
      "[data-review]",
    ) as HTMLElement;
    const reviewHeading = frameDocument.querySelector(
      "[data-review-heading]",
    ) as HTMLElement;
    rationale.getBoundingClientRect = () => rect(140, 16, 358, 410);
    reviewHeading.getBoundingClientRect = () => rect(570, 20, 180, 28);
    review.getBoundingClientRect = () => rect(590, 16, 358, 180);
    rationale.scrollIntoView = vi.fn();
    reviewHeading.scrollIntoView = vi.fn();
    review.scrollIntoView = vi.fn();
    frameDocument.querySelector("[data-close-detail]")?.addEventListener(
      "click",
      renderComparison,
    );
  };

  const renderComparison = () => {
    phone.innerHTML = `
      <div data-sheet-backdrop style="position: absolute; inset: 0; z-index: 20"></div>
      <div style="position: absolute; inset: 0; top: 320px; z-index: 21">
        <div class="scrolly">
          <div
            data-sheet-heading
            style="display: flex; align-items: flex-start; justify-content: space-between"
          >
            <div><span>꾸준한거북이</span>님</div>
          </div>
          <div data-comparison>내 포트폴리오와 구성 일치도</div>
          <div
            data-comparison-table
            style="border: 1px solid #EDEFF1; border-radius: 16px"
          >
            <span>구성종목</span>
            <div>국내주식형</div>
          </div>
          <div
            data-open-detail
            style="background: #22A94D; border-radius: 14px; cursor: pointer"
          >
            상세히 보기
          </div>
        </div>
      </div>
    `;
    const comparison = frameDocument.querySelector(
      "[data-comparison]",
    ) as HTMLElement;
    const detailButton = frameDocument.querySelector(
      "[data-open-detail]",
    ) as HTMLElement;
    const sheetHeading = frameDocument.querySelector(
      "[data-sheet-heading]",
    ) as HTMLElement;
    const comparisonTable = frameDocument.querySelector(
      "[data-comparison-table]",
    ) as HTMLElement;
    sheetHeading.getBoundingClientRect = () => rect(350, 22, 346, 64);
    comparison.getBoundingClientRect = () => rect(440, 22, 346, 28);
    comparisonTable.getBoundingClientRect = () => rect(470, 22, 346, 250);
    detailButton.getBoundingClientRect = () => rect(760, 22, 346, 52);
    sheetHeading.scrollIntoView = vi.fn();
    comparison.scrollIntoView = vi.fn();
    comparisonTable.scrollIntoView = vi.fn();
    detailButton.scrollIntoView = vi.fn();
    frameDocument.querySelector("[data-sheet-backdrop]")?.addEventListener(
      "click",
      renderList,
    );
    detailButton.addEventListener("click", () => {
      onDetailOpen();
      renderDetail();
    });
  };

  function renderList(): void {
    phone.innerHTML = `
      <div class="scrolly">
        <section data-current-portfolio style="background: #fff; border-radius: 20px">
          <span>현재 포트폴리오</span>
        </section>
        <div data-recommendation-heading>추천 벤치마킹 포트폴리오</div>
        <section data-recommended-portfolio style="background: #fff; border-radius: 20px; cursor: pointer">
          <span>꾸준한거북이</span>
        </section>
        <section style="background: #fff; border-radius: 20px; cursor: pointer">
          <span>배당모으미</span>
        </section>
      </div>
    `;
    const currentPortfolio = frameDocument!.querySelector(
      "[data-current-portfolio]",
    ) as HTMLElement;
    const recommendationHeading = frameDocument!.querySelector(
      "[data-recommendation-heading]",
    ) as HTMLElement;
    const listScroller = frameDocument!.querySelector(
      ".scrolly",
    ) as HTMLElement;
    const recommendedPortfolio = Array.from(
      frameDocument!.querySelectorAll<HTMLElement>(
        "[data-recommended-portfolio]",
      ),
    ).find((element) => element.textContent?.includes("꾸준한거북이"))!;
    currentPortfolio.getBoundingClientRect = () => rect(130, 16, 358, 352);
    recommendationHeading.getBoundingClientRect = () => rect(500, 18, 240, 28);
    recommendedPortfolio.getBoundingClientRect = () => rect(540, 16, 358, 280);
    listScroller.getBoundingClientRect = () => rect(105, 0, 390, 739);
    listScroller.scrollTo = vi.fn();
    currentPortfolio.scrollIntoView = vi.fn();
    recommendationHeading.scrollIntoView = vi.fn();
    recommendedPortfolio.scrollIntoView = vi.fn();
    recommendedPortfolio.addEventListener("click", () => {
      onPortfolioOpen();
      renderComparison();
    });
  }

  renderList();
}

describe("FirstUseGuide", () => {
  beforeEach(() => {
    document.body.replaceChildren();
    window.history.replaceState(null, "", "/#/main-home");
    window.localStorage.clear();
    window.sessionStorage.clear();
    authMocks.getSession.mockResolvedValue({
      data: { session: authSession("jeongsu33@kda-demo.invalid") },
      error: null,
    });
    authMocks.onAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: authMocks.unsubscribe } },
    });
    authMocks.onAuthStateChange.mockImplementation((listener) => {
      authStateChangeListener = listener;
      return {
        data: { subscription: { unsubscribe: authMocks.unsubscribe } },
      };
    });
  });

  afterEach(() => {
    cleanup();
    document.body.replaceChildren();
    vi.restoreAllMocks();
  });

  it("starts from an optional one-minute introduction on the home route", async () => {
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    expect(
      await screen.findByRole("heading", { name: "처음이신가요?" }),
    ).toBeInTheDocument();
    expect(document.querySelector(".fug-title-accent")).toHaveTextContent("처음");
    expect(screen.getByRole("button", { name: "1분 안내 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "나중에 볼게요" })).toBeInTheDocument();
  });

  it("walks through six home anchors and finishes through the real User Pick CTA", async () => {
    let inertWhenUserPickOpened: boolean | null = null;
    const onUserPick = vi.fn(() => {
      inertWhenUserPickOpened = (
        document.querySelector(".mhs-body") as HTMLElement
      ).inert;
    });
    addHomeFixture(onUserPick);
    render(<FirstUseGuide />);
    const firstPromoClick = vi.spyOn(
      screen.getByRole("button", { name: "1번째 카드 보기" }),
      "click",
    );

    fireEvent.click(await screen.findByRole("button", { name: "1분 안내 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "내 연금을 한곳에서 볼 수 있어요 !",
      }),
    ).toBeInTheDocument();
    expect(
      Array.from(document.querySelectorAll(".fug-title-accent"))
        .map((element) => element.textContent),
    ).toEqual(expect.arrayContaining(["내 연금", "DC형·IRP·연금저축", "정보 기준일"]));

    fireEvent.click(screen.getByRole("button", { name: "자산 구성 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "자산 구성부터 천천히 살펴보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "진단 기능 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "궁금한 부분은 우리의 연그미에게 바로 진단 받아보세요 !",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "세액공제도 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "놓치고 있는 세액공제 금액 및 연금 수령액을 계산해볼 수 있어요 !",
      }),
    ).toBeInTheDocument();
    expect(firstPromoClick).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "전략 설명 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "전략은 운용 방식부터 비교해 보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "이용자 Pick 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "다른 이용자들의 PICK과 PICK에 대한 근거도 참고할 수 있어요 !",
      }),
    ).toBeInTheDocument();

    expect(
      (document.querySelector(".mhs-body") as HTMLElement).inert,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "이용자 Pick 둘러보기" }));
    await waitFor(() => expect(onUserPick).toHaveBeenCalledOnce());
    expect(inertWhenUserPickOpened).not.toBe(true);
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBe("true");
  });

  it("does not reopen again during the same login session", async () => {
    window.sessionStorage.setItem(firstUseGuideStorageKey(TARGET_USER_ID), "true");
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    await waitFor(() => {
      expect(screen.queryByText("처음이신가요?")).not.toBeInTheDocument();
    });
  });

  it("opens again after the target user logs out and signs in", async () => {
    window.sessionStorage.setItem(firstUseGuideStorageKey(TARGET_USER_ID), "true");
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    await waitFor(() => expect(authStateChangeListener).not.toBeNull());
    await act(async () => {
      authStateChangeListener?.("SIGNED_OUT", null);
      await Promise.resolve();
    });
    act(() => {
      authStateChangeListener?.(
        "SIGNED_IN",
        authSession("jeongsu33@kda-demo.invalid"),
      );
    });

    expect(
      await screen.findByRole("heading", { name: "처음이신가요?" }),
    ).toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
  });

  it("clears stale chatbot completion when sign-in wins the initial session race", async () => {
    window.history.replaceState(null, "", "/#/guide");
    window.sessionStorage.setItem(
      chatGuideStorageKey(TARGET_USER_ID),
      "true",
    );
    let resolveSession: ((value: unknown) => void) | null = null;
    authMocks.getSession.mockReturnValue(new Promise((resolve) => {
      resolveSession = resolve;
    }));
    addChatFixture();
    render(<FirstUseGuide />);

    await waitFor(() => expect(authStateChangeListener).not.toBeNull());
    act(() => {
      authStateChangeListener?.(
        "SIGNED_IN",
        authSession("jeongsu33@kda-demo.invalid"),
      );
    });

    expect(
      await screen.findByRole("heading", {
        name: "연그미와 대화를 시작해 볼까요?",
      }),
    ).toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(chatGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();

    await act(async () => {
      resolveSession?.({
        data: { session: authSession("jeongsu33@kda-demo.invalid") },
        error: null,
      });
      await Promise.resolve();
    });
  });

  it("does not open for any other authenticated user", async () => {
    authMocks.getSession.mockResolvedValue({
      data: {
        session: authSession(
          "another-user@kda-demo.invalid",
          "92b0ac69-a30c-4a4b-94ca-530ed9b43f6c",
        ),
      },
      error: null,
    });
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    await waitFor(() => {
      expect(screen.queryByText("처음이신가요?")).not.toBeInTheDocument();
    });
  });

  it("previews the combined tax credit and pension payout section name", async () => {
    window.history.replaceState(
      null,
      "",
      "/?tour-preview=1#/main-home",
    );
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    await waitFor(() => {
      expect(document.querySelector(".mhs-section-title")).toHaveTextContent(
        "세액공제 / 연금수령액 계산",
      );
    });
  });

  it("walks through the strategy detail guide and stores completion separately", async () => {
    window.history.replaceState(
      null,
      "",
      "/#/strategy-detail?strategy=factor",
    );
    addStrategyDetailFixture();
    render(<FirstUseGuide />);

    expect(
      await screen.findByRole("heading", {
        name: "전략 상세 화면을 살펴볼까요?",
      }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "1분 안내 보기" }));

    expect(
      await screen.findByRole("heading", {
        name: "전략의 역할부터 확인해요",
      }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "자산배분 예시 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "자산배분 예시는 구조를 이해하는 참고예요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "운용 방식 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "전략이 작동하는 방식을 읽어보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "연금계좌 적용 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "연금계좌에서 맡을 역할을 확인해요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "핵심 용어 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "낯선 용어는 여기서 풀어볼 수 있어요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "안내 마치기" }));
    expect(
      window.sessionStorage.getItem(
        strategyDetailGuideStorageKey(TARGET_USER_ID),
      ),
    ).toBe("true");
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
  });

  it("opens the strategy detail preview without an authenticated session", async () => {
    window.history.replaceState(
      null,
      "",
      "/?tour-preview=1#/strategy-detail?strategy=factor",
    );
    authMocks.getSession.mockResolvedValue({
      data: { session: null },
      error: null,
    });
    addStrategyDetailFixture();
    render(<FirstUseGuide />);

    expect(
      await screen.findByRole("heading", {
        name: "전략 상세 화면을 살펴볼까요?",
      }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "나중에 볼게요" }));
    await waitFor(() => {
      expect(
        screen.queryByText("전략 상세 화면을 살펴볼까요?"),
      ).not.toBeInTheDocument();
    });
  });

  it("walks through the complete chatbot guide and stores completion separately", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    window.history.replaceState(null, "", "/#/guide");
    addChatFixture();
    render(<FirstUseGuide />);

    expect(
      await screen.findByRole("heading", {
        name: "연그미와 대화를 시작해 볼까요?",
      }),
    ).toBeInTheDocument();
    expect(document.querySelector(".fug-root-chat")).toBeInTheDocument();
    expect(
      document.querySelector(".fug-root-chat")?.parentElement,
    ).toHaveClass("app-shell");
    fireEvent.click(screen.getByRole("button", { name: "1분 안내 보기" }));

    expect(
      await screen.findByRole("heading", {
        name: "연그미에게 편하게 물어보세요",
      }),
    ).toBeInTheDocument();
    expect(
      document.querySelector(".fug-title-accent"),
    ).toHaveTextContent("연그미");
    expect(
      screen.getByText(/예를 들어 “IRP와 연금저축은 뭐가 달라\?”처럼 시작해 보세요\./),
    ).toBeInTheDocument();
    expect(
      Array.from(document.querySelectorAll(".fug-title-accent"))
        .map((element) => element.textContent),
    ).toEqual(expect.arrayContaining([
      "연금계좌 운용",
      "세액공제",
      "리밸런싱",
      "ETF 테마",
    ]));

    fireEvent.click(screen.getByRole("button", { name: "점검 알림 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "리밸런싱 점검 알림을 확인해요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "추천 질문 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "추천 질문으로 바로 시작해 보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "ETF 테마 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "관심 있는 ETF 테마를 둘러보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "질문 입력창 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "궁금한 내용을 직접 입력해 보세요",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "챗봇 안내 마치기" }));
    expect(
      window.sessionStorage.getItem(chatGuideStorageKey(TARGET_USER_ID)),
    ).toBe("true");
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
  });

  it("walks through the pension calculator guide inside its iframe", async () => {
    window.history.replaceState(null, "", "/#/planner");
    const onTaxTab = vi.fn();
    addPensionPlannerFixture(onTaxTab);
    render(<FirstUseGuide />);

    const plannerFrame = document.querySelector(
      'iframe[title="예상 연금 계산 및 세액공제 확인"]',
    ) as HTMLIFrameElement;
    const plannerGuide = within(plannerFrame.contentDocument!.body);
    expect(
      await plannerGuide.findByText("세액공제 계산기를 살펴볼까요?"),
    ).toBeInTheDocument();
    expect(
      plannerFrame.contentDocument?.querySelector("#pension-phone > .fug-root"),
    ).toBeInTheDocument();
    expect(
      plannerFrame.contentDocument?.head.querySelector(
        "style[data-first-use-guide-styles]",
      ),
    ).toBeInTheDocument();
    expect(
      document.querySelector(".pension-planner-frame > .fug-root"),
    ).not.toBeInTheDocument();
    fireEvent.click(plannerGuide.getByRole("button", { name: "1분 안내 보기" }));

    expect(
      await plannerGuide.findByText("세액공제 탭에서 남은 한도를 확인해요"),
    ).toBeInTheDocument();
    expect(onTaxTab).toHaveBeenCalled();

    fireEvent.click(plannerGuide.getByRole("button", { name: "연금저축 한도 보기" }));
    expect(
      await plannerGuide.findByText("연금저축 납입액을 조절해 보세요"),
    ).toBeInTheDocument();

    fireEvent.click(plannerGuide.getByRole("button", { name: "IRP·DC 한도 보기" }));
    expect(
      await plannerGuide.findByText("IRP·DC 본인 추가납입도 함께 살펴봐요"),
    ).toBeInTheDocument();

    fireEvent.click(plannerGuide.getByRole("button", { name: "ISA 전환 혜택 보기" }));
    expect(
      await plannerGuide.findByText("ISA 만기 전환 혜택도 비교할 수 있어요"),
    ).toBeInTheDocument();

    fireEvent.click(plannerGuide.getByRole("button", { name: "안내 마치기" }));
    expect(
      window.sessionStorage.getItem(
        pensionPlannerGuideStorageKey(TARGET_USER_ID),
      ),
    ).toBe("true");
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
  });

  it("continues from User Pick into comparison, rationale, and reviews", async () => {
    window.history.replaceState(null, "", "/#/user-pick-benchmark");
    const onPortfolioOpen = vi.fn();
    const onDetailOpen = vi.fn();
    addUserPickFixture(onPortfolioOpen, onDetailOpen);
    render(<FirstUseGuide />);

    const userPickFrame = document.querySelector(
      'iframe[title="투자 벤치마킹하기"]',
    ) as HTMLIFrameElement;
    const userPickGuide = within(userPickFrame.contentDocument!.body);
    expect(
      await userPickGuide.findByRole("heading", {
        name: "이용자 Pick을 함께 살펴볼까요?",
      }),
    ).toBeInTheDocument();
    expect(
      userPickFrame.contentDocument?.querySelector(
        "body > .fug-root-user-pick",
      ),
    ).toBeInTheDocument();
    fireEvent.click(userPickGuide.getByRole("button", {
      name: "1분 안내 보기",
    }));

    expect(
      await userPickGuide.findByRole("heading", {
        name: "내 포트폴리오를 기준으로 비교해요",
      }),
    ).toBeInTheDocument();
    expect(
      Array.from(
        userPickFrame.contentDocument!.querySelectorAll(".fug-title-accent"),
      )
        .map((element) => element.textContent),
    ).toEqual(expect.arrayContaining(["내 포트폴리오", "비교"]));
    const currentPortfolio = Array.from(
      userPickFrame.contentDocument!.querySelectorAll<HTMLElement>("section"),
    ).find((element) => element.textContent?.includes("현재 포트폴리오"));
    expect(currentPortfolio?.scrollIntoView).toHaveBeenCalledWith({
      block: "start",
      behavior: "smooth",
    });

    fireEvent.click(userPickGuide.getByRole("button", {
      name: "추천 포트폴리오 보기",
    }));
    expect(
      await userPickGuide.findByRole("heading", {
        name: "추천 포트폴리오를 하나씩 둘러보세요",
      }),
    ).toBeInTheDocument();
    const recommendedPortfolio = userPickFrame.contentDocument!.querySelector(
      "[data-recommended-portfolio]",
    ) as HTMLElement;
    expect(recommendedPortfolio.scrollIntoView).toHaveBeenCalledWith({
      block: "start",
      behavior: "smooth",
    });

    fireEvent.click(userPickGuide.getByRole("button", {
      name: "내 비중과 비교하기",
    }));
    expect(onPortfolioOpen).toHaveBeenCalledTimes(1);
    expect(
      await userPickGuide.findByRole("heading", {
        name: "비중 변화를 비교하고 상세히 보기를 눌러요",
      }),
    ).toBeInTheDocument();
    expect(
      userPickFrame.contentDocument?.querySelector<HTMLElement>(
        "[data-open-detail]",
      )?.scrollIntoView,
    ).toHaveBeenCalledWith({
      block: "center",
      behavior: "smooth",
    });
    expect(
      userPickGuide.getByRole("heading", {
        name: "비중 변화를 비교하고 상세히 보기를 눌러요",
      }).closest("section"),
    ).toHaveClass("is-top");
    expect(
      userPickFrame.contentDocument?.querySelector(".fug-root-user-pick"),
    ).toHaveClass("is-awaiting-user-pick-detail");

    fireEvent.click(
      userPickFrame.contentDocument!.querySelector(
        "[data-open-detail]",
      ) as HTMLElement,
    );
    expect(onDetailOpen).toHaveBeenCalledTimes(1);
    expect(
      await userPickGuide.findByRole("heading", {
        name: "운용 근거를 확인하고 판단해요",
      }),
    ).toBeInTheDocument();
    const rationale = Array.from(
      userPickFrame.contentDocument!.querySelectorAll<HTMLElement>("section"),
    ).find((element) => element.textContent?.includes("운용근거"));
    expect(rationale?.scrollIntoView).toHaveBeenCalledWith({
      block: "start",
      behavior: "smooth",
    });

    fireEvent.click(userPickGuide.getByRole("button", {
      name: "이용자 후기 보기",
    }));
    expect(
      await userPickGuide.findByRole("heading", {
        name: "따라한 이용자의 후기를 살펴봐요",
      }),
    ).toBeInTheDocument();
    const reviewHeading = userPickFrame.contentDocument?.querySelector<HTMLElement>(
      "[data-review-heading]",
    );
    expect(reviewHeading?.scrollIntoView).toHaveBeenCalledWith({
      block: "center",
      behavior: "smooth",
    });
    expect(
      userPickGuide.getByRole("heading", {
        name: "따라한 이용자의 후기를 살펴봐요",
      }).closest("section"),
    ).toHaveClass("is-top");
    expect(
      userPickFrame.contentDocument?.querySelector(".fug-spotlight"),
    ).toHaveStyle({
      height: "216px",
      left: "8px",
      top: "562px",
      width: "374px",
    });

    fireEvent.click(userPickGuide.getByRole("button", {
      name: "이용자 Pick 안내 마치기",
    }));
    expect(
      window.sessionStorage.getItem(
        userPickGuideStorageKey(TARGET_USER_ID),
      ),
    ).toBe("true");
  });

  it("restores the matching User Pick screen when moving backward", async () => {
    window.history.replaceState(null, "", "/#/user-pick-benchmark");
    addUserPickFixture(vi.fn(), vi.fn());
    render(<FirstUseGuide />);

    const userPickFrame = document.querySelector(
      'iframe[title="투자 벤치마킹하기"]',
    ) as HTMLIFrameElement;
    const userPickGuide = within(userPickFrame.contentDocument!.body);
    fireEvent.click(await userPickGuide.findByRole("button", {
      name: "1분 안내 보기",
    }));
    fireEvent.click(userPickGuide.getByRole("button", {
      name: "추천 포트폴리오 보기",
    }));
    fireEvent.click(userPickGuide.getByRole("button", {
      name: "내 비중과 비교하기",
    }));
    expect(
      await userPickGuide.findByRole("heading", {
        name: "비중 변화를 비교하고 상세히 보기를 눌러요",
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      userPickFrame.contentDocument!.querySelector(
        "[data-open-detail]",
      ) as HTMLElement,
    );

    expect(
      await userPickGuide.findByRole("heading", {
        name: "운용 근거를 확인하고 판단해요",
      }),
    ).toBeInTheDocument();
    expect(
      userPickFrame.contentDocument?.querySelector("[data-review-heading]"),
    ).toBeInTheDocument();

    fireEvent.click(userPickGuide.getByRole("button", { name: "이전" }));

    expect(
      await userPickGuide.findByRole("heading", {
        name: "비중 변화를 비교하고 상세히 보기를 눌러요",
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        userPickFrame.contentDocument?.querySelector("[data-sheet-heading]"),
      ).toBeInTheDocument();
    });

    fireEvent.click(userPickGuide.getByRole("button", { name: "이전" }));

    expect(
      await userPickGuide.findByRole("heading", {
        name: "추천 포트폴리오를 하나씩 둘러보세요",
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        userPickFrame.contentDocument?.querySelector(
          "[data-recommendation-heading]",
        ),
      ).toBeInTheDocument();
    });
  });

  it("waits for the calculator runtime and ignores its hidden source template", async () => {
    window.history.replaceState(null, "", "/#/planner");
    document.body.insertAdjacentHTML(
      "beforeend",
      `
        <section class="pension-planner-frame">
          <iframe title="예상 연금 계산 및 세액공제 확인"></iframe>
        </section>
      `,
    );
    const plannerFrame = document.querySelector(
      'iframe[title="예상 연금 계산 및 세액공제 확인"]',
    ) as HTMLIFrameElement;
    const frameDocument = plannerFrame.contentDocument!;
    frameDocument.body.innerHTML = `
      <x-dc style="display:none">
        <div id="pension-phone"></div>
      </x-dc>
    `;
    render(<FirstUseGuide />);

    expect(
      frameDocument.querySelector("x-dc .fug-root"),
    ).not.toBeInTheDocument();

    frameDocument.body.insertAdjacentHTML(
      "beforeend",
      `
        <div id="pension-phone">
          <div class="scrolly"></div>
        </div>
      `,
    );
    const plannerGuide = within(frameDocument.body);
    expect(
      await plannerGuide.findByText("세액공제 계산기를 살펴볼까요?"),
    ).toBeInTheDocument();
    expect(
      frameDocument.querySelector("x-dc .fug-root"),
    ).not.toBeInTheDocument();
    expect(
      frameDocument.querySelector(
        "body > #pension-phone > .fug-root",
      ),
    ).toBeInTheDocument();
  });

  it("does not open the chatbot guide for another authenticated user", async () => {
    window.history.replaceState(null, "", "/#/guide");
    authMocks.getSession.mockResolvedValue({
      data: {
        session: authSession(
          "another-user@kda-demo.invalid",
          "92b0ac69-a30c-4a4b-94ca-530ed9b43f6c",
        ),
      },
      error: null,
    });
    addChatFixture();
    render(<FirstUseGuide />);

    await waitFor(() => {
      expect(
        screen.queryByText("연그미와 대화를 시작해 볼까요?"),
      ).not.toBeInTheDocument();
    });
  });

  it("opens the chatbot guide after the same login finishes the home guide", async () => {
    addHomeFixture(vi.fn());
    render(<FirstUseGuide />);

    expect(
      await screen.findByRole("heading", { name: "처음이신가요?" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "나중에 볼게요" }));
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBe("true");

    addChatFixture();
    act(() => {
      window.history.replaceState(null, "", "/#/guide");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(
      await screen.findByRole("heading", {
        name: "연그미와 대화를 시작해 볼까요?",
      }),
    ).toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(chatGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
  });

  it("opens when the chatbot app is entered and closes on both optional exits", async () => {
    window.history.replaceState(null, "", "/#/user-pick-benchmark");
    render(<FirstUseGuide />);
    addChatFixture();

    act(() => {
      window.history.replaceState(null, "", "/#/guide");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(
      await screen.findByRole("heading", {
        name: "연그미와 대화를 시작해 볼까요?",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "나중에 볼게요" }));
    await waitFor(() => {
      expect(document.querySelector(".fug-root-chat")).not.toBeInTheDocument();
    });

    window.sessionStorage.removeItem(chatGuideStorageKey(TARGET_USER_ID));
    act(() => {
      window.history.replaceState(null, "", "/#/user-pick-benchmark");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
      window.history.replaceState(null, "", "/#/guide");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(
      await screen.findByRole("heading", {
        name: "연그미와 대화를 시작해 볼까요?",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "1분 안내 보기" }));
    fireEvent.click(screen.getByRole("button", { name: "건너뛰기" }));
    await waitFor(() => {
      expect(document.querySelector(".fug-root-chat")).not.toBeInTheDocument();
    });
  });
});
