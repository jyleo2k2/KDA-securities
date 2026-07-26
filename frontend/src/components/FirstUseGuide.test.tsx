// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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
  firstUseGuideStorageKey,
  FirstUseGuide,
  strategyDetailGuideStorageKey,
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

    expect(await screen.findByText("처음이신가요?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1분 안내 보기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "나중에 볼게요" })).toBeInTheDocument();
  });

  it("walks through six home anchors and finishes through the real User Pick CTA", async () => {
    const onUserPick = vi.fn();
    addHomeFixture(onUserPick);
    render(<FirstUseGuide />);

    fireEvent.click(await screen.findByRole("button", { name: "1분 안내 보기" }));
    expect(await screen.findByText("내 연금을 한곳에서 볼 수 있어요 !")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "자산 구성 보기" }));
    expect(await screen.findByText("자산 구성부터 천천히 살펴보세요")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "진단 기능 보기" }));
    expect(
      await screen.findByRole("heading", {
        name: "궁금한 부분은 우리의 연그미에게 바로 진단 받아보세요 !",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "세액공제도 보기" }));
    expect(
      await screen.findByText(
        "놓치고 있는 세액공제 금액 및 연금 수령액을 계산해볼 수 있어요 !",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "전략 설명 보기" }));
    expect(await screen.findByText("전략은 운용 방식부터 비교해 보세요")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "이용자 Pick 보기" }));
    expect(
      await screen.findByText(
        "다른 이용자들의 PICK과 PICK에 대한 근거도 참고할 수 있어요 !",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "이용자 Pick 둘러보기" }));
    await waitFor(() => expect(onUserPick).toHaveBeenCalledOnce());
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

    expect(await screen.findByText("처음이신가요?")).toBeInTheDocument();
    expect(
      window.sessionStorage.getItem(firstUseGuideStorageKey(TARGET_USER_ID)),
    ).toBeNull();
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
      await screen.findByText("전략 상세 화면을 살펴볼까요?"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "1분 안내 보기" }));

    expect(
      await screen.findByText("전략의 역할부터 확인해요"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "자산배분 예시 보기" }));
    expect(
      await screen.findByText("자산배분 예시는 구조를 이해하는 참고예요"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "운용 방식 보기" }));
    expect(
      await screen.findByText("전략이 작동하는 방식을 읽어보세요"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "연금계좌 적용 보기" }));
    expect(
      await screen.findByText("연금계좌에서 맡을 역할을 확인해요"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "핵심 용어 보기" }));
    expect(
      await screen.findByText("낯선 용어는 여기서 풀어볼 수 있어요"),
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
      await screen.findByText("전략 상세 화면을 살펴볼까요?"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "나중에 볼게요" }));
    await waitFor(() => {
      expect(
        screen.queryByText("전략 상세 화면을 살펴볼까요?"),
      ).not.toBeInTheDocument();
    });
  });
});
