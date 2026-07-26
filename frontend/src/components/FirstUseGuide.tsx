import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "../auth/supabase";
import "./FirstUseGuide.css";

const GUIDE_VERSION = "v2";
const COMPLETE_KEY = `pension-first-use-guide:${GUIDE_VERSION}:complete`;
const STRATEGY_DETAIL_COMPLETE_KEY =
  `pension-first-use-guide:${GUIDE_VERSION}:strategy-detail:complete`;
const PREVIEW_QUERY = "tour-preview";
const TARGET_GUIDE_EMAIL = "jeongsu33@kda-demo.invalid";

interface GuideStep {
  accent?: string;
  selector: string;
  title: string;
  body: string;
  cta: string;
}

interface GuideConfig {
  backgroundSelector: string;
  completeKey: string;
  finalTargetSelector?: string;
  id: "home" | "strategy-detail";
  introBody: string;
  introTitle: string;
  portalSelector?: string;
  route: string;
  scrollSelector: string;
  shellSelector: string;
  steps: GuideStep[];
}

interface Rect {
  height: number;
  left: number;
  top: number;
  width: number;
}

const HOME_STEPS: GuideStep[] = [
  {
    selector: ".mhs-asset-total",
    title: "내 연금을 한곳에서 볼 수 있어요 !",
    body: "DC형·IRP·연금저축을 합친 금액이에요. 금액과 함께 정보 기준일도 확인해 주세요.",
    cta: "자산 구성 보기",
  },
  {
    selector: ".mhs-pie-wrap",
    title: "자산 구성부터 천천히 살펴보세요",
    body: "도넛의 자산군을 누르면 주식·채권·현금성 자산 등이 어느 정도인지 쉽게 볼 수 있어요.",
    cta: "진단 기능 보기",
  },
  {
    selector: ".mhs-summary-cta-button",
    title: "궁금한 부분은 우리의 연그미에게 바로 진단 받아보세요 !",
    accent: "연그미",
    body: "자산 집중도와 계좌별 운용 규칙을 근거와 함께 쉽게 설명해 드려요.",
    cta: "세액공제도 보기",
  },
  {
    selector: ".mhs-tax-card",
    title: "놓치고 있는 세액공제 금액 및 연금 수령액을 계산해볼 수 있어요 !",
    body: "연금저축·IRP 납입 현황과 수령 조건을 바탕으로 세액공제 금액과 연금 수령액을 함께 확인할 수 있어요.",
    cta: "전략 설명 보기",
  },
  {
    selector: ".mhs-strategy-scroll",
    title: "전략은 운용 방식부터 비교해 보세요",
    body: "계획수익률은 같은 기준으로 전략을 비교하기 위한 운용 가정이며, 미래 수익을 보장하지 않아요.",
    cta: "이용자 Pick 보기",
  },
  {
    selector: ".mhs-userpick-card-button",
    title: "다른 이용자들의 PICK과 PICK에 대한 근거도 참고할 수 있어요 !",
    body: "수익률 순위보다 자산 구성·위험·운용 이유를 살펴보세요.",
    cta: "이용자 Pick 둘러보기",
  },
];

const STRATEGY_DETAIL_STEPS: GuideStep[] = [
  {
    selector: ".sd-hero",
    title: "전략의 역할부터 확인해요",
    body: "전략 이름과 설명을 읽고 내 연금 포트폴리오에서 어떤 역할을 맡을 수 있는지 먼저 살펴보세요.",
    cta: "자산배분 예시 보기",
  },
  {
    selector: ".sd-allocation-example",
    title: "자산배분 예시는 구조를 이해하는 참고예요",
    body: "막대 크기는 확정 비중이 아니에요. 주식·채권·현금성 자산과 주식 ETF 분야를 나누는 방식을 확인해 보세요.",
    cta: "운용 방식 보기",
  },
  {
    selector: ".sd-operation-guide",
    title: "전략이 작동하는 방식을 읽어보세요",
    body: "언제나 유리한 전략은 없어요. 어떤 기준으로 자산을 고르고 비중을 점검하는지 확인해 보세요.",
    cta: "연금계좌 적용 보기",
  },
  {
    selector: ".sd-account-guide",
    title: "연금계좌에서 맡을 역할을 확인해요",
    body: "포트폴리오 내 역할과 구현 난이도를 함께 보고, 계좌 규칙과 투자성향에 맞는지 살펴보세요.",
    cta: "핵심 용어 보기",
  },
  {
    selector: ".sd-words",
    title: "낯선 용어는 여기서 풀어볼 수 있어요",
    body: "전략을 이해하는 데 필요한 핵심 용어를 쉬운 설명과 함께 확인할 수 있어요.",
    cta: "안내 마치기",
  },
];

const GUIDES: GuideConfig[] = [
  {
    backgroundSelector: ".mhs-header, .mhs-body, .mhs-tab-toggle",
    completeKey: COMPLETE_KEY,
    finalTargetSelector: ".mhs-userpick-card-button",
    id: "home",
    introBody: "홈의 주요 기능을 확인하는 방법을 1분 안에 알려드릴게요.",
    introTitle: "처음이신가요?",
    portalSelector: ".mhs-page",
    route: "/main-home",
    scrollSelector: ".mhs-body",
    shellSelector: ".mhs-phone",
    steps: HOME_STEPS,
  },
  {
    backgroundSelector: ".sd-header, .sd-scroll",
    completeKey: STRATEGY_DETAIL_COMPLETE_KEY,
    id: "strategy-detail",
    introBody: "전략의 역할과 자산배분 예시를 읽는 방법을 1분 안에 알려드릴게요.",
    introTitle: "전략 상세 화면을 살펴볼까요?",
    route: "/strategy-detail",
    scrollSelector: ".sd-scroll",
    shellSelector: ".sd-phone",
    steps: STRATEGY_DETAIL_STEPS,
  },
];

const COMPLETE_KEYS = GUIDES.map((guide) => guide.completeKey);

function activeGuide(): GuideConfig | null {
  const route = window.location.hash.slice(1).split("?")[0];
  return GUIDES.find((guide) => guide.route === route) ?? null;
}

function previewRequested(): boolean {
  return new URLSearchParams(window.location.search).get(PREVIEW_QUERY) === "1";
}

function elementRect(element: Element): Rect {
  const rect = element.getBoundingClientRect();
  return {
    height: rect.height,
    left: rect.left,
    top: rect.top,
    width: rect.width,
  };
}

function guideStorageKey(baseKey: string, userId: string | null): string {
  return userId ? `${baseKey}:${userId}` : baseKey;
}

function guideShouldOpen(baseKey: string, userId: string | null): boolean {
  if (previewRequested()) return true;
  if (!userId) return false;
  return window.sessionStorage.getItem(
    guideStorageKey(baseKey, userId),
  ) !== "true";
}

function eligibleGuideUserId(session: Session | null): string | null {
  const email = session?.user.email?.trim().toLowerCase();
  return email === TARGET_GUIDE_EMAIL ? session?.user.id ?? null : null;
}

function guideTitle(step: GuideStep): ReactNode {
  if (!step.accent) return step.title;
  const accentStart = step.title.indexOf(step.accent);
  if (accentStart < 0) return step.title;
  return (
    <>
      {step.title.slice(0, accentStart)}
      <span className="fug-title-accent">{step.accent}</span>
      {step.title.slice(accentStart + step.accent.length)}
    </>
  );
}

export function FirstUseGuide(): JSX.Element | null {
  const [phone, setPhone] = useState<HTMLElement | null>(null);
  const [guide, setGuide] = useState<GuideConfig | null>(null);
  const [mode, setMode] = useState<"intro" | "steps" | "closed">("closed");
  const [stepIndex, setStepIndex] = useState(0);
  const [phoneRect, setPhoneRect] = useState<Rect | null>(null);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const [eligibleUserId, setEligibleUserId] = useState<string | null>(null);
  const activeGuideId = useRef<GuideConfig["id"] | null>(null);
  const dismissedPreviewGuideId = useRef<GuideConfig["id"] | null>(null);

  useEffect(() => {
    if (previewRequested() || !supabase) return;
    let active = true;
    let currentAuthUserId: string | null = null;
    let currentEligibleUserId: string | null = null;
    let initialized = false;
    const updateEligibility = (session: Session | null) => {
      currentAuthUserId = session?.user.id ?? null;
      currentEligibleUserId = eligibleGuideUserId(session);
      if (active) setEligibleUserId(currentEligibleUserId);
    };
    void supabase.auth.getSession()
      .then(({ data }) => {
        initialized = true;
        updateEligibility(data.session);
      })
      .catch(() => updateEligibility(null));
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT") {
        if (currentEligibleUserId) {
          COMPLETE_KEYS.forEach((key) => {
            window.sessionStorage.removeItem(
              guideStorageKey(key, currentEligibleUserId),
            );
          });
        }
        initialized = true;
        updateEligibility(null);
        return;
      }
      const nextEligibleUserId = eligibleGuideUserId(session);
      if (
        event === "SIGNED_IN"
        && initialized
        && currentAuthUserId === null
        && nextEligibleUserId
      ) {
        COMPLETE_KEYS.forEach((key) => {
          window.sessionStorage.removeItem(
            guideStorageKey(key, nextEligibleUserId),
          );
        });
      }
      initialized = true;
      updateEligibility(session);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const findGuide = useCallback(() => {
    const nextGuide = activeGuide();
    const nextPhone = nextGuide
      ? document.querySelector<HTMLElement>(nextGuide.shellSelector)
      : null;
    if (activeGuideId.current !== nextGuide?.id) {
      activeGuideId.current = nextGuide?.id ?? null;
      dismissedPreviewGuideId.current = null;
      setStepIndex(0);
      setTargetRect(null);
      setMode("closed");
    }
    setGuide(nextGuide);
    setPhone(nextPhone);
    if (!nextGuide || !nextPhone) {
      setMode("closed");
      return;
    }
    if (
      previewRequested()
      && dismissedPreviewGuideId.current === nextGuide.id
    ) {
      setMode("closed");
      return;
    }
    if (!guideShouldOpen(nextGuide.completeKey, eligibleUserId)) {
      setMode("closed");
      return;
    }
    setMode((current) => current === "closed" ? "intro" : current);
  }, [eligibleUserId]);

  useEffect(() => {
    findGuide();
    const observer = new MutationObserver(findGuide);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", findGuide);
    return () => {
      observer.disconnect();
      window.removeEventListener("hashchange", findGuide);
    };
  }, [findGuide]);

  const measure = useCallback(() => {
    if (!guide || !phone || mode === "closed") return;
    const nextPhoneRect = elementRect(phone);
    setPhoneRect(nextPhoneRect);
    if (mode === "intro") {
      setTargetRect(null);
      return;
    }
    const target = document.querySelector<HTMLElement>(
      guide.steps[stepIndex].selector,
    );
    setTargetRect(target ? elementRect(target) : null);
  }, [guide, mode, phone, stepIndex]);

  useLayoutEffect(() => {
    if (!guide || !phone || mode === "closed") return;
    const target = mode === "steps"
      ? document.querySelector<HTMLElement>(guide.steps[stepIndex].selector)
      : null;
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
    const frame = window.requestAnimationFrame(measure);
    const timer = window.setTimeout(measure, 260);
    const scrollArea = phone.querySelector(guide.scrollSelector);
    window.addEventListener("resize", measure);
    scrollArea?.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      window.removeEventListener("resize", measure);
      scrollArea?.removeEventListener("scroll", measure);
    };
  }, [guide, measure, mode, phone, stepIndex]);

  useEffect(() => {
    if (!guide || !phone || mode === "closed") return;
    const background = Array.from(
      phone.querySelectorAll<HTMLElement>(guide.backgroundSelector),
    );
    const previous = background.map((element) => ({
      ariaHidden: element.getAttribute("aria-hidden"),
      element,
      inert: element.inert,
    }));
    background.forEach((element) => {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    });
    return () => {
      previous.forEach(({ ariaHidden, element, inert }) => {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
    };
  }, [guide, mode, phone]);

  useEffect(() => {
    if (guide?.id !== "home" || !phone || !previewRequested()) return;
    const taxHeading = Array.from(
      phone.querySelectorAll<HTMLElement>(".mhs-section-title"),
    ).find((element) => element.textContent?.trim() === "세액공제");
    if (!taxHeading) return;
    const originalText = taxHeading.textContent ?? "";
    taxHeading.textContent = "세액공제 / 연금수령액 계산";
    return () => {
      taxHeading.textContent = originalText;
    };
  }, [guide, phone]);

  if (!guide || !phone || !phoneRect || mode === "closed") return null;
  const visibleGuide = guide;

  function dismissForNow(): void {
    if (previewRequested()) {
      dismissedPreviewGuideId.current = visibleGuide.id;
    }
    window.sessionStorage.setItem(
      guideStorageKey(visibleGuide.completeKey, eligibleUserId),
      "true",
    );
    setMode("closed");
  }

  function completeGuide(): void {
    if (previewRequested()) {
      dismissedPreviewGuideId.current = visibleGuide.id;
    }
    window.sessionStorage.setItem(
      guideStorageKey(visibleGuide.completeKey, eligibleUserId),
      "true",
    );
    setMode("closed");
  }

  function handleStepCta(): void {
    if (stepIndex < visibleGuide.steps.length - 1) {
      setStepIndex((current) => current + 1);
      return;
    }
    const finalTarget = visibleGuide.finalTargetSelector
      ? document.querySelector<HTMLElement>(visibleGuide.finalTargetSelector)
      : null;
    completeGuide();
    finalTarget?.click();
  }

  const relativeTarget = targetRect && {
    height: targetRect.height,
    left: targetRect.left - phoneRect.left,
    top: targetRect.top - phoneRect.top,
    width: targetRect.width,
  };
  const coachAtTop = relativeTarget
    ? relativeTarget.top + relativeTarget.height / 2 > phoneRect.height / 2
    : false;
  const currentStep = guide.steps[stepIndex];
  const portalHost = guide.portalSelector
    ? phone.querySelector<HTMLElement>(guide.portalSelector) ?? phone
    : phone;

  return createPortal(
    <div className="fug-root" aria-live="polite">
      {mode === "intro" ? (
        <>
          <div className="fug-intro-backdrop" />
          <section className="fug-panel fug-intro-panel" aria-labelledby="fug-intro-title">
            <span className="fug-eyebrow">처음 이용 안내</span>
            <h2 id="fug-intro-title">{guide.introTitle}</h2>
            <p>{guide.introBody}</p>
            <div className="fug-actions">
              <button type="button" className="fug-secondary" onClick={dismissForNow}>
                나중에 볼게요
              </button>
              <button
                type="button"
                className="fug-primary"
                onClick={() => {
                  setStepIndex(0);
                  setMode("steps");
                }}
              >
                1분 안내 보기
              </button>
            </div>
          </section>
        </>
      ) : (
        <>
          {relativeTarget && (
            <div
              className="fug-spotlight"
              style={{
                height: relativeTarget.height,
                left: relativeTarget.left,
                top: relativeTarget.top,
                width: relativeTarget.width,
              }}
            />
          )}
          <section
            className={`fug-panel fug-step-panel ${coachAtTop ? "is-top" : "is-bottom"}`}
            aria-labelledby="fug-step-title"
          >
            <div className="fug-progress">
              <span>{stepIndex + 1} / {guide.steps.length}</span>
              <button type="button" onClick={completeGuide}>건너뛰기</button>
            </div>
            <h2 id="fug-step-title">
              {guideTitle(currentStep)}
            </h2>
            <p>{currentStep.body}</p>
            <div className="fug-actions">
              {stepIndex > 0 ? (
                <button
                  type="button"
                  className="fug-secondary"
                  onClick={() => setStepIndex((current) => current - 1)}
                >
                  이전
                </button>
              ) : <span />}
              <button type="button" className="fug-primary" onClick={handleStepCta}>
                {currentStep.cta}
              </button>
            </div>
          </section>
        </>
      )}
    </div>,
    portalHost,
  );
}

export const FIRST_USE_GUIDE_STORAGE_KEY = COMPLETE_KEY;
export function firstUseGuideStorageKey(userId: string): string {
  return guideStorageKey(COMPLETE_KEY, userId);
}

export function strategyDetailGuideStorageKey(userId: string): string {
  return guideStorageKey(STRATEGY_DETAIL_COMPLETE_KEY, userId);
}
