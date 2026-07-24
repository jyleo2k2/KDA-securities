import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type JSX,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "../auth/supabase";
import "./FirstUseGuide.css";

const GUIDE_VERSION = "v1";
const COMPLETE_KEY = `pension-first-use-guide:${GUIDE_VERSION}:complete`;
const SESSION_DISMISS_KEY = `pension-first-use-guide:${GUIDE_VERSION}:dismissed`;
const PREVIEW_QUERY = "tour-preview";
const TARGET_GUIDE_EMAIL = "jeongsu33@kda-demo.invalid";

interface GuideStep {
  accent?: string;
  selector: string;
  title: string;
  body: string;
  cta: string;
}

interface Rect {
  height: number;
  left: number;
  top: number;
  width: number;
}

const STEPS: GuideStep[] = [
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

function isHomeRoute(): boolean {
  const route = window.location.hash.slice(1).split("?")[0];
  return route === "/main-home";
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

function guideShouldOpen(userId: string | null): boolean {
  if (previewRequested()) return true;
  if (!userId) return false;
  return window.localStorage.getItem(guideStorageKey(COMPLETE_KEY, userId)) !== "true"
    && window.sessionStorage.getItem(
      guideStorageKey(SESSION_DISMISS_KEY, userId),
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
  const [mode, setMode] = useState<"intro" | "steps" | "closed">("closed");
  const [stepIndex, setStepIndex] = useState(0);
  const [phoneRect, setPhoneRect] = useState<Rect | null>(null);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const [eligibleUserId, setEligibleUserId] = useState<string | null>(null);

  useEffect(() => {
    if (previewRequested() || !supabase) return;
    let active = true;
    const updateEligibility = (session: Session | null) => {
      if (active) setEligibleUserId(eligibleGuideUserId(session));
    };
    void supabase.auth.getSession()
      .then(({ data }) => updateEligibility(data.session))
      .catch(() => updateEligibility(null));
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      updateEligibility(session);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const findHome = useCallback(() => {
    const nextPhone = isHomeRoute()
      ? document.querySelector<HTMLElement>(".mhs-phone")
      : null;
    setPhone(nextPhone);
    if (!nextPhone) {
      setMode("closed");
      return;
    }
    if (!guideShouldOpen(eligibleUserId)) {
      setMode("closed");
      return;
    }
    setMode((current) => current === "closed" ? "intro" : current);
  }, [eligibleUserId]);

  useEffect(() => {
    findHome();
    const observer = new MutationObserver(findHome);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", findHome);
    return () => {
      observer.disconnect();
      window.removeEventListener("hashchange", findHome);
    };
  }, [findHome]);

  const measure = useCallback(() => {
    if (!phone || mode === "closed") return;
    const nextPhoneRect = elementRect(phone);
    setPhoneRect(nextPhoneRect);
    if (mode === "intro") {
      setTargetRect(null);
      return;
    }
    const target = document.querySelector<HTMLElement>(STEPS[stepIndex].selector);
    setTargetRect(target ? elementRect(target) : null);
  }, [mode, phone, stepIndex]);

  useLayoutEffect(() => {
    if (!phone || mode === "closed") return;
    const target = mode === "steps"
      ? document.querySelector<HTMLElement>(STEPS[stepIndex].selector)
      : null;
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
    const frame = window.requestAnimationFrame(measure);
    const timer = window.setTimeout(measure, 260);
    const scrollArea = phone.querySelector(".mhs-body");
    window.addEventListener("resize", measure);
    scrollArea?.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      window.removeEventListener("resize", measure);
      scrollArea?.removeEventListener("scroll", measure);
    };
  }, [measure, mode, phone, stepIndex]);

  useEffect(() => {
    if (!phone || mode === "closed") return;
    const background = Array.from(
      phone.querySelectorAll<HTMLElement>(
        ".mhs-header, .mhs-body, .mhs-tab-toggle",
      ),
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
  }, [mode, phone]);

  useEffect(() => {
    if (!phone || !previewRequested()) return;
    const taxHeading = Array.from(
      phone.querySelectorAll<HTMLElement>(".mhs-section-title"),
    ).find((element) => element.textContent?.trim() === "세액공제");
    if (!taxHeading) return;
    const originalText = taxHeading.textContent ?? "";
    taxHeading.textContent = "세액공제 / 연금수령액 계산";
    return () => {
      taxHeading.textContent = originalText;
    };
  }, [phone]);

  if (!phone || !phoneRect || mode === "closed") return null;

  function dismissForNow(): void {
    window.sessionStorage.setItem(
      guideStorageKey(SESSION_DISMISS_KEY, eligibleUserId),
      "true",
    );
    setMode("closed");
  }

  function completeGuide(): void {
    window.localStorage.setItem(
      guideStorageKey(COMPLETE_KEY, eligibleUserId),
      "true",
    );
    setMode("closed");
  }

  function handleStepCta(): void {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex((current) => current + 1);
      return;
    }
    const finalTarget = document.querySelector<HTMLElement>(
      STEPS[STEPS.length - 1].selector,
    );
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
  const currentStep = STEPS[stepIndex];
  const portalHost = phone.querySelector<HTMLElement>(".mhs-page") ?? phone;

  return createPortal(
    <div className="fug-root" aria-live="polite">
      {mode === "intro" ? (
        <>
          <div className="fug-intro-backdrop" />
          <section className="fug-panel fug-intro-panel" aria-labelledby="fug-intro-title">
            <span className="fug-eyebrow">처음 이용 안내</span>
            <h2 id="fug-intro-title">처음이신가요?</h2>
            <p>홈의 주요 기능을 확인하는 방법을 1분 안에 알려드릴게요.</p>
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
              <span>{stepIndex + 1} / {STEPS.length}</span>
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
