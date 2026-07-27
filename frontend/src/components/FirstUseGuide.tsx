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
import { pickChatPromptCandidate } from "../chatPromptCandidates";
import firstUseGuideStyles from "./FirstUseGuide.css?inline";
import "./FirstUseGuide.css";

const HOME_GUIDE_VERSION = "v3";
const STRATEGY_DETAIL_GUIDE_VERSION = "v2";
const CHAT_GUIDE_VERSION = "v5";
const PENSION_PLANNER_GUIDE_VERSION = "v2";
const USER_PICK_GUIDE_VERSION = "v4";
const COMPLETE_KEY =
  `pension-first-use-guide:${HOME_GUIDE_VERSION}:complete`;
const STRATEGY_DETAIL_COMPLETE_KEY =
  `pension-first-use-guide:${STRATEGY_DETAIL_GUIDE_VERSION}:strategy-detail:complete`;
const CHAT_COMPLETE_KEY =
  `pension-first-use-guide:${CHAT_GUIDE_VERSION}:chat:complete`;
const PENSION_PLANNER_COMPLETE_KEY =
  `pension-first-use-guide:${PENSION_PLANNER_GUIDE_VERSION}:pension-planner:complete`;
const USER_PICK_COMPLETE_KEY =
  `pension-first-use-guide:${USER_PICK_GUIDE_VERSION}:user-pick:complete`;
const PREVIEW_QUERY = "tour-preview";
const TARGET_GUIDE_EMAIL = "jeongsu33@kda-demo.invalid";
const GUIDE_STYLE_ATTRIBUTE = "data-first-use-guide-styles";

interface GuideStep {
  accent?: string;
  activateClosestSelector?: string;
  activateSelector?: string;
  activateText?: string;
  accents?: string[];
  bodyAccents?: string[];
  coachPosition?: "top" | "bottom";
  closestSelector?: string;
  focusBlock?: ScrollLogicalPosition;
  selector?: string;
  spotlightPadding?: number;
  targetEndClosestSelector?: string;
  targetEndText?: string;
  targetText?: string;
  title: string;
  body: string;
  cta: string;
}

interface GuideConfig {
  activateSelector?: string;
  backgroundSelector: string;
  completeKey: string;
  finalTargetSelector?: string;
  focusBlock?: ScrollLogicalPosition;
  frameSelector?: string;
  id: "chat" | "home" | "strategy-detail" | "pension-planner" | "user-pick";
  introBody: string;
  introBodyAccents?: string[];
  introTitle: string;
  introTitleAccents?: string[];
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
    accents: ["내 연금"],
    body: "DC형·IRP·연금저축을 합친 금액이에요. 금액과 함께 정보 기준일도 확인해 주세요.",
    bodyAccents: ["DC형·IRP·연금저축", "정보 기준일"],
    cta: "자산 구성 보기",
  },
  {
    selector: ".mhs-pie-wrap",
    title: "자산 구성부터 천천히 살펴보세요",
    accents: ["자산 구성"],
    body: "도넛의 자산군을 누르면 주식·채권·현금성 자산 등이 어느 정도인지 쉽게 볼 수 있어요.",
    bodyAccents: ["주식·채권·현금성 자산"],
    cta: "진단 기능 보기",
  },
  {
    selector: ".mhs-summary-cta-button",
    title: "궁금한 부분은 우리의 연그미에게 바로 진단 받아보세요 !",
    accents: ["연그미", "진단"],
    body: "자산 집중도와 계좌별 운용 규칙을 근거와 함께 쉽게 설명해 드려요.",
    bodyAccents: ["자산 집중도", "계좌별 운용 규칙"],
    cta: "세액공제도 보기",
  },
  {
    selector: ".mhs-tax-card",
    title: "놓치고 있는 세액공제 금액 및 연금 수령액을 계산해볼 수 있어요 !",
    accents: ["세액공제 금액", "연금 수령액"],
    body: "연금저축·IRP 납입 현황과 수령 조건을 바탕으로 세액공제 금액과 연금 수령액을 함께 확인할 수 있어요.",
    bodyAccents: ["연금저축·IRP", "세액공제 금액", "연금 수령액"],
    cta: "전략 설명 보기",
  },
  {
    selector: ".mhs-strategy-scroll",
    title: "전략은 운용 방식부터 비교해 보세요",
    accents: ["운용 방식"],
    body: "계획수익률은 같은 기준으로 전략을 비교하기 위한 운용 가정이며, 미래 수익을 보장하지 않아요.",
    bodyAccents: ["계획수익률", "미래 수익을 보장하지 않아요"],
    cta: "이용자 Pick 보기",
  },
  {
    selector: ".mhs-userpick-card-button",
    title: "다른 이용자들의 PICK과 PICK에 대한 근거도 참고할 수 있어요 !",
    accents: ["PICK", "근거"],
    body: "수익률 순위보다 자산 구성·위험·운용 이유를 살펴보세요.",
    bodyAccents: ["자산 구성·위험·운용 이유"],
    cta: "이용자 Pick 둘러보기",
  },
];

const STRATEGY_DETAIL_STEPS: GuideStep[] = [
  {
    selector: ".sd-hero",
    title: "전략의 역할부터 확인해요",
    accents: ["전략의 역할"],
    body: "전략 이름과 설명을 읽고 내 연금 포트폴리오에서 어떤 역할을 맡을 수 있는지 먼저 살펴보세요.",
    cta: "자산배분 예시 보기",
  },
  {
    selector: ".sd-allocation-example",
    title: "자산배분 예시는 구조를 이해하는 참고예요",
    accents: ["자산배분 예시"],
    body: "막대 크기는 확정 비중이 아니에요. 주식·채권·현금성 자산과 주식 ETF 분야를 나누는 방식을 확인해 보세요.",
    cta: "운용 방식 보기",
  },
  {
    selector: ".sd-operation-guide",
    title: "전략이 작동하는 방식을 읽어보세요",
    accents: ["작동하는 방식"],
    body: "언제나 유리한 전략은 없어요. 어떤 기준으로 자산을 고르고 비중을 점검하는지 확인해 보세요.",
    cta: "연금계좌 적용 보기",
  },
  {
    selector: ".sd-account-guide",
    title: "연금계좌에서 맡을 역할을 확인해요",
    accents: ["연금계좌"],
    body: "포트폴리오 내 역할과 구현 난이도를 함께 보고, 계좌 규칙과 투자성향에 맞는지 살펴보세요.",
    cta: "핵심 용어 보기",
  },
  {
    selector: ".sd-words",
    title: "낯선 용어는 여기서 풀어볼 수 있어요",
    accents: ["낯선 용어"],
    body: "전략을 이해하는 데 필요한 핵심 용어를 쉬운 설명과 함께 확인할 수 있어요.",
    cta: "안내 마치기",
  },
];

const CHAT_STEPS: GuideStep[] = [
  {
    selector: ".design-welcome h1",
    title: "연금 운용 질문을 쉽게 물어보세요",
    accents: ["연금 운용 질문"],
    body: "연금계좌 운용, 세액공제, 리밸런싱, ETF 테마처럼 궁금한 내용을 대화로 쉽게 확인할 수 있어요.",
    bodyAccents: ["연금계좌 운용", "세액공제", "리밸런싱", "ETF 테마"],
    cta: "내 정보 카드 보기",
  },
  {
    selector: ".welcome-intro-cards",
    title: "내 연금 상황과 점검 알림을 확인해요",
    accents: ["내 연금 상황", "점검 알림"],
    body: "고객 카드에서 연결된 계좌 상황을 보고, 리밸런싱 카드에서 점검 주기와 필요한 행동을 확인할 수 있어요.",
    bodyAccents: ["연결된 계좌 상황", "점검 주기"],
    cta: "추천 질문 보기",
  },
  {
    selector: ".chat-home-card-section:not(.etf-theme-section)",
    title: "추천 질문으로 바로 시작해 보세요",
    accents: ["추천 질문"],
    body: "질문을 어떻게 써야 할지 어렵다면 카드를 누르세요. 선택한 질문을 연그미에게 바로 전달해요.",
    bodyAccents: ["카드를 누르세요", "연그미"],
    cta: "ETF 테마 보기",
  },
  {
    selector: ".etf-theme-section",
    title: "관심 있는 ETF 테마를 둘러보세요",
    accents: ["ETF 테마"],
    body: "테마 카드를 누르면 구성과 유의점을 확인할 수 있어요. 미래 수익을 보장하는 추천은 아니에요.",
    bodyAccents: ["구성과 유의점", "미래 수익을 보장하는 추천은 아니에요"],
    cta: "질문 입력창 보기",
  },
  {
    selector: ".composer-wrap",
    title: "궁금한 내용을 직접 입력해 보세요",
    accents: ["직접 입력"],
    body: "하단 입력창에 질문을 적고 전송 버튼을 누르세요. 지난 대화는 위쪽 버튼에서 다시 확인할 수 있어요.",
    bodyAccents: ["하단 입력창", "전송 버튼", "지난 대화"],
    cta: "챗봇 안내 마치기",
  },
];

const PENSION_PLANNER_STEPS: GuideStep[] = [
  {
    selector: ".scrolly > div:nth-child(2) > div:nth-child(2)",
    title: "세액공제 탭에서 남은 한도를 확인해요",
    body: "연금저축·IRP·DC형 본인 추가납입액을 합산한 세액공제 한도와 예상 공제액을 확인할 수 있어요.",
    cta: "연금저축 한도 보기",
  },
  {
    closestSelector: "div",
    selector: ".brand-range[max=\"600\"]:not(.tax-range-irp)",
    title: "연금저축 납입액을 조절해 보세요",
    body: "현재 납입액을 기준으로 연금저축 600만원 한도까지 남은 금액과 추가 공제액을 비교해 볼 수 있어요.",
    cta: "IRP·DC 한도 보기",
  },
  {
    closestSelector: "div",
    selector: ".brand-range.tax-range-irp",
    title: "IRP·DC 본인 추가납입도 함께 살펴봐요",
    body: "연금저축과 합산한 900만원 한도 안에서 추가로 공제받을 수 있는 금액을 확인해 보세요.",
    cta: "ISA 전환 혜택 보기",
  },
  {
    closestSelector: "div",
    selector: ".brand-range[max=\"3000\"]",
    title: "ISA 만기 전환 혜택도 비교할 수 있어요",
    body: "ISA 만기 자금을 연금계좌로 전환할 때 적용되는 추가 세액공제 한도를 입력값에 따라 확인할 수 있어요.",
    cta: "안내 마치기",
  },
];

const USER_PICK_STEPS: GuideStep[] = [
  {
    closestSelector: "[style*=\"border-radius:20px\"], [style*=\"border-radius: 20px\"]",
    targetText: "현재 포트폴리오",
    title: "내 포트폴리오를 기준으로 비교해요",
    accents: ["내 포트폴리오", "비교"],
    body: "현재 자산 구성 비율과 투자전략을 먼저 확인하면 다른 이용자와 무엇이 다른지 더 쉽게 볼 수 있어요.",
    bodyAccents: ["자산 구성 비율", "투자전략", "다른 이용자"],
    cta: "추천 포트폴리오 보기",
  },
  {
    closestSelector: "[style*=\"cursor\"]",
    targetText: "꾸준한거북이",
    title: "추천 포트폴리오를 하나씩 둘러보세요",
    accents: ["추천 포트폴리오"],
    body: "수익률뿐 아니라 운용기간, 직업군, 자산 구성과 투자전략을 함께 살펴보고 비교할 이용자를 선택하세요.",
    bodyAccents: ["운용기간", "직업군", "자산 구성", "투자전략"],
    cta: "내 비중과 비교하기",
  },
  {
    activateClosestSelector: "[style*=\"cursor\"]",
    activateText: "꾸준한거북이",
    coachPosition: "top",
    closestSelector: "[style*=\"border-radius:16px\"], [style*=\"border-radius: 16px\"]",
    focusBlock: "center",
    spotlightPadding: 8,
    targetText: "구성종목",
    title: "내 비중과 달라지는 부분을 비교해요",
    accents: ["내 비중", "비교"],
    body: "국내주식·해외주식·채권·현금성 자산별로 현재 비중과 이 이용자의 비중, 따라갈 때의 변화를 확인할 수 있어요.",
    bodyAccents: ["현재 비중", "이 이용자의 비중", "따라갈 때의 변화"],
    cta: "운용 근거 보기",
  },
  {
    activateClosestSelector: "[style*=\"cursor\"]",
    activateText: "상세히 보기",
    closestSelector: "[style*=\"border-radius:20px\"], [style*=\"border-radius: 20px\"]",
    targetText: "왜 이렇게 나눴냐면요",
    title: "운용 근거를 읽고 판단해요",
    accents: ["운용 근거"],
    body: "왜 이 비중으로 나눴는지, 전략을 고른 이유와 언제 다시 맞추는지를 읽고 내 상황에 맞는지 판단하세요.",
    bodyAccents: ["전략을 고른 이유", "언제 다시 맞추는지", "내 상황"],
    cta: "따라하기 후기 보기",
  },
  {
    coachPosition: "top",
    closestSelector: "[style*=\"align-items\"][style*=\"gap\"]",
    focusBlock: "center",
    spotlightPadding: 8,
    targetEndClosestSelector: "[style*=\"border-radius:18px\"], [style*=\"border-radius: 18px\"]",
    targetEndText: "장기러버",
    targetText: "따라하기 후기",
    title: "따라한 이용자의 후기도 확인해요",
    accents: ["이용자의 후기"],
    body: "실제로 따라한 기간과 경험을 읽고 좋아요·댓글로 다른 이용자의 의견까지 확인할 수 있어요.",
    bodyAccents: ["따라한 기간과 경험", "좋아요·댓글"],
    cta: "이용자 Pick 안내 마치기",
  },
];

const GUIDES: GuideConfig[] = [
  {
    backgroundSelector: ".mhs-header, .mhs-body, .mhs-tab-toggle",
    completeKey: COMPLETE_KEY,
    finalTargetSelector: ".mhs-userpick-card-button",
    id: "home",
    introBody: "홈의 주요 기능을 확인하는 방법을 1분 안에 알려드릴게요.",
    introBodyAccents: ["주요 기능", "1분"],
    introTitle: "처음이신가요?",
    introTitleAccents: ["처음"],
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
    introBodyAccents: ["전략의 역할", "자산배분 예시", "1분"],
    introTitle: "전략 상세 화면을 살펴볼까요?",
    introTitleAccents: ["전략 상세"],
    route: "/strategy-detail",
    scrollSelector: ".sd-scroll",
    shellSelector: ".sd-phone",
    steps: STRATEGY_DETAIL_STEPS,
  },
  {
    backgroundSelector: ".sidebar, .chat-main",
    completeKey: CHAT_COMPLETE_KEY,
    id: "chat",
    introBody: "추천 질문을 고르고 직접 질문하는 방법을 화면 끝까지 차례대로 알려드릴게요.",
    introBodyAccents: ["추천 질문", "직접 질문"],
    introTitle: "연그미와 대화를 시작해 볼까요?",
    introTitleAccents: ["연그미"],
    route: "/guide",
    scrollSelector: ".conversation",
    shellSelector: ".guide-phone .app-shell",
    steps: CHAT_STEPS,
  },
  {
    activateSelector: ".scrolly > div:nth-child(2) > div:nth-child(2)",
    backgroundSelector: ".scrolly",
    completeKey: PENSION_PLANNER_COMPLETE_KEY,
    frameSelector: "iframe[title=\"예상 연금 계산 및 세액공제 확인\"]",
    id: "pension-planner",
    introBody: "납입액을 바꿔 세액공제 한도와 예상 공제액을 확인하는 방법을 1분 안에 알려드릴게요.",
    introTitle: "세액공제 계산기를 살펴볼까요?",
    route: "/planner",
    scrollSelector: ".scrolly",
    shellSelector: "#pension-phone",
    steps: PENSION_PLANNER_STEPS,
  },
  {
    backgroundSelector: ".scrolly",
    completeKey: USER_PICK_COMPLETE_KEY,
    focusBlock: "start",
    frameSelector: "iframe[title=\"투자 벤치마킹하기\"]",
    id: "user-pick",
    introBody: "내 포트폴리오와 다른 이용자의 자산 구성·운용 근거·후기를 비교하는 방법을 화면 끝까지 알려드릴게요.",
    introBodyAccents: ["내 포트폴리오", "자산 구성", "운용 근거", "후기"],
    introTitle: "이용자 Pick을 함께 살펴볼까요?",
    introTitleAccents: ["이용자 Pick"],
    portalSelector: "body",
    route: "/user-pick-benchmark",
    scrollSelector: ".scrolly",
    shellSelector: "#benchmark-phone",
    steps: USER_PICK_STEPS,
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

function contentDocumentForGuide(guide: GuideConfig): Document | null {
  if (!guide.frameSelector) return document;
  return document.querySelector<HTMLIFrameElement>(
    guide.frameSelector,
  )?.contentDocument ?? null;
}

function normalizedText(value: string | null): string {
  return value?.replace(/\s+/g, " ").trim() ?? "";
}

function elementByText(
  contentDocument: Document,
  text: string,
): HTMLElement | null {
  const expected = normalizedText(text);
  const matches = Array.from(
    contentDocument.querySelectorAll<HTMLElement>("*"),
  ).filter((element) => (
    !element.closest("x-dc")
    && normalizedText(element.textContent) === expected
  ));
  return matches.find((element) => (
    !Array.from(element.children).some(
      (child) => normalizedText(child.textContent) === expected,
    )
  )) ?? matches[0] ?? null;
}

function guideElement(
  contentDocument: Document,
  selector?: string,
  text?: string,
): HTMLElement | null {
  if (selector) {
    return contentDocument.querySelector<HTMLElement>(selector);
  }
  return text ? elementByText(contentDocument, text) : null;
}

function ensureGuideStyles(contentDocument: Document): void {
  if (
    contentDocument === document
    || contentDocument.head.querySelector(`[${GUIDE_STYLE_ATTRIBUTE}]`)
  ) return;
  const style = contentDocument.createElement("style");
  style.setAttribute(GUIDE_STYLE_ATTRIBUTE, "");
  style.textContent = firstUseGuideStyles;
  contentDocument.head.appendChild(style);
}

function guideShell(
  contentDocument: Document,
  selector: string,
): HTMLElement | null {
  return Array.from(
    contentDocument.querySelectorAll<HTMLElement>(selector),
  ).find((element) => !element.closest("x-dc")) ?? null;
}

function targetForStep(
  contentDocument: Document,
  step: GuideStep,
): HTMLElement | null {
  const target = guideElement(
    contentDocument,
    step.selector,
    step.targetText,
  );
  if (!target || !step.closestSelector) return target;
  return target.closest<HTMLElement>(step.closestSelector);
}

function targetRectForStep(
  contentDocument: Document,
  step: GuideStep,
): Rect | null {
  const target = targetForStep(contentDocument, step);
  if (!target) return null;
  const targetRect = elementRect(target);
  if (!step.targetEndText) return targetRect;

  const endTarget = guideElement(
    contentDocument,
    undefined,
    step.targetEndText,
  );
  const resolvedEndTarget = endTarget && step.targetEndClosestSelector
    ? endTarget.closest<HTMLElement>(step.targetEndClosestSelector)
    : endTarget;
  if (!resolvedEndTarget) return targetRect;

  const endRect = elementRect(resolvedEndTarget);
  const top = Math.min(targetRect.top, endRect.top);
  const left = Math.min(targetRect.left, endRect.left);
  const right = Math.max(
    targetRect.left + targetRect.width,
    endRect.left + endRect.width,
  );
  const bottom = Math.max(
    targetRect.top + targetRect.height,
    endRect.top + endRect.height,
  );
  return {
    height: bottom - top,
    left,
    top,
    width: right - left,
  };
}

function activateStep(
  contentDocument: Document,
  step: GuideStep,
): void {
  const activationTarget = guideElement(
    contentDocument,
    step.activateSelector,
    step.activateText,
  );
  const clickableTarget = activationTarget && step.activateClosestSelector
    ? activationTarget.closest<HTMLElement>(step.activateClosestSelector)
      ?? activationTarget
    : activationTarget;
  clickableTarget?.click();
}

function userPickDetailRoot(contentDocument: Document): HTMLElement | null {
  return elementByText(contentDocument, "이 회원의 운용 근거")
    ?.closest<HTMLElement>(
      "[style*=\"z-index:30\"], [style*=\"z-index: 30\"]",
    ) ?? null;
}

function userPickSheetRoot(contentDocument: Document): HTMLElement | null {
  return elementByText(contentDocument, "내 포트폴리오와 비교")
    ?.closest<HTMLElement>(
      "[style*=\"z-index:21\"], [style*=\"z-index: 21\"]",
    ) ?? null;
}

function ensureUserPickView(
  contentDocument: Document,
  stepIndex: number,
): void {
  const detailRoot = userPickDetailRoot(contentDocument);
  const sheetRoot = userPickSheetRoot(contentDocument);

  if (stepIndex <= 1) {
    if (detailRoot) {
      detailRoot.querySelector<HTMLElement>(
        "svg[style*=\"cursor\"]",
      )?.dispatchEvent(new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: contentDocument.defaultView,
      }));
      return;
    }
    if (sheetRoot) {
      (sheetRoot.previousElementSibling as HTMLElement | null)?.click();
    }
    return;
  }

  if (stepIndex === 2) {
    if (detailRoot) {
      detailRoot.querySelector<HTMLElement>(
        "svg[style*=\"cursor\"]",
      )?.dispatchEvent(new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: contentDocument.defaultView,
      }));
      return;
    }
    if (!sheetRoot) {
      activateStep(contentDocument, USER_PICK_STEPS[2]);
    }
    return;
  }

  if (detailRoot) return;
  if (!sheetRoot) {
    activateStep(contentDocument, USER_PICK_STEPS[2]);
    return;
  }
  activateStep(contentDocument, USER_PICK_STEPS[3]);
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

function guideText(text: string, accents: string[] = []): ReactNode {
  const uniqueAccents = [...new Set(accents)]
    .filter((accent) => text.includes(accent))
    .sort((left, right) => right.length - left.length);
  if (uniqueAccents.length === 0) return text;
  const escaped = uniqueAccents.map((accent) => (
    accent.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  ));
  const accentPattern = new RegExp(`(${escaped.join("|")})`, "g");
  const accentSet = new Set(uniqueAccents);
  return text.split(accentPattern).map((part, index) => (
    accentSet.has(part)
      ? <span className="fug-title-accent" key={`${part}-${index}`}>{part}</span>
      : part
  ));
}

export function FirstUseGuide(): JSX.Element | null {
  const [chatPromptCandidate] = useState(pickChatPromptCandidate);
  const [phone, setPhone] = useState<HTMLElement | null>(null);
  const [contentDocument, setContentDocument] = useState<Document | null>(null);
  const [guide, setGuide] = useState<GuideConfig | null>(null);
  const [mode, setMode] = useState<"intro" | "steps" | "closed">("closed");
  const [stepIndex, setStepIndex] = useState(0);
  const [phoneRect, setPhoneRect] = useState<Rect | null>(null);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const [eligibleUserId, setEligibleUserId] = useState<string | null>(null);
  const activeGuideId = useRef<GuideConfig["id"] | null>(null);
  const activatedStepKey = useRef<string | null>(null);
  const dismissedPreviewGuideId = useRef<GuideConfig["id"] | null>(null);

  useEffect(() => {
    if (previewRequested() || !supabase) return;
    let active = true;
    let currentAuthUserId: string | null = null;
    let currentEligibleUserId: string | null = null;
    const updateEligibility = (session: Session | null) => {
      currentAuthUserId = session?.user.id ?? null;
      currentEligibleUserId = eligibleGuideUserId(session);
      if (active) setEligibleUserId(currentEligibleUserId);
    };
    void supabase.auth.getSession()
      .then(({ data }) => {
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
        updateEligibility(null);
        return;
      }
      const nextEligibleUserId = eligibleGuideUserId(session);
      if (
        event === "SIGNED_IN"
        && nextEligibleUserId
        && currentAuthUserId !== session?.user.id
      ) {
        COMPLETE_KEYS.forEach((key) => {
          window.sessionStorage.removeItem(
            guideStorageKey(key, nextEligibleUserId),
          );
        });
      }
      updateEligibility(session);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const findGuide = useCallback(() => {
    const nextGuide = activeGuide();
    const nextContentDocument = nextGuide
      ? contentDocumentForGuide(nextGuide)
      : null;
    if (nextContentDocument) ensureGuideStyles(nextContentDocument);
    const nextPhone = nextGuide && nextContentDocument
      ? guideShell(nextContentDocument, nextGuide.shellSelector)
      : null;
    if (activeGuideId.current !== nextGuide?.id) {
      activeGuideId.current = nextGuide?.id ?? null;
      dismissedPreviewGuideId.current = null;
      activatedStepKey.current = null;
      setStepIndex(0);
      setTargetRect(null);
      setMode("closed");
    }
    setGuide(nextGuide);
    setContentDocument(nextContentDocument);
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

  useEffect(() => {
    if (!guide?.frameSelector) return;
    const frame = document.querySelector<HTMLIFrameElement>(
      guide.frameSelector,
    );
    if (!frame) return;
    let frameObserver: MutationObserver | null = null;
    const observeFrame = () => {
      frameObserver?.disconnect();
      const frameDocument = frame.contentDocument;
      if (frameDocument?.documentElement) {
        frameObserver = new MutationObserver(findGuide);
        frameObserver.observe(frameDocument.documentElement, {
          childList: true,
          subtree: true,
        });
      }
      findGuide();
    };
    frame.addEventListener("load", observeFrame);
    observeFrame();
    return () => {
      frame.removeEventListener("load", observeFrame);
      frameObserver?.disconnect();
    };
  }, [findGuide, guide]);

  const measure = useCallback(() => {
    if (!guide || !phone || !contentDocument || mode === "closed") return;
    const nextPhoneRect = elementRect(phone);
    setPhoneRect(nextPhoneRect);
    if (mode === "intro") {
      setTargetRect(null);
      return;
    }
    setTargetRect(targetRectForStep(
      contentDocument,
      guide.steps[stepIndex],
    ));
  }, [contentDocument, guide, mode, phone, stepIndex]);

  useLayoutEffect(() => {
    if (!guide || !phone || !contentDocument || mode === "closed") return;
    if (mode === "steps" && guide.activateSelector) {
      contentDocument.querySelector<HTMLElement>(
        guide.activateSelector,
      )?.click();
    }
    const currentStepKey = `${guide.id}:${stepIndex}`;
    if (
      mode === "steps"
      && activatedStepKey.current !== currentStepKey
    ) {
      activatedStepKey.current = currentStepKey;
      if (guide.id === "user-pick") {
        ensureUserPickView(contentDocument, stepIndex);
      } else {
        activateStep(contentDocument, guide.steps[stepIndex]);
      }
    }
    const scrollArea = phone.querySelector<HTMLElement>(guide.scrollSelector);
    const alignTarget = () => {
      if (mode === "steps" && guide.id === "user-pick") {
        ensureUserPickView(contentDocument, stepIndex);
      }
      const step = guide.steps[stepIndex];
      const target = mode === "steps"
        ? targetForStep(contentDocument, step)
        : null;
      target?.scrollIntoView({
        block: step.focusBlock ?? guide.focusBlock ?? "center",
        behavior: "smooth",
      });
      measure();
    };
    alignTarget();
    const frame = window.requestAnimationFrame(alignTarget);
    const timers = [140, 360].map((delay) => (
      window.setTimeout(alignTarget, delay)
    ));
    window.addEventListener("resize", measure);
    scrollArea?.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      timers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("resize", measure);
      scrollArea?.removeEventListener("scroll", measure);
    };
  }, [contentDocument, guide, measure, mode, phone, stepIndex]);

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

  if (
    !guide
    || !phone
    || !contentDocument
    || !phoneRect
    || mode === "closed"
  ) return null;
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
      ? contentDocument?.querySelector<HTMLElement>(
          visibleGuide.finalTargetSelector,
        )
      : null;
    completeGuide();
    if (finalTarget) {
      finalTarget.ownerDocument.defaultView?.setTimeout(() => {
        finalTarget.click();
      }, 0);
    }
  }

  const baseStep = guide.steps[stepIndex];
  const currentStep = guide.id === "chat" && stepIndex === 0
    ? {
        ...baseStep,
        body: `${baseStep.body} 예를 들어 “${chatPromptCandidate}”처럼 시작해 보세요.`,
      }
    : baseStep;
  const spotlightPadding = currentStep.spotlightPadding ?? 0;
  const relativeTarget = targetRect && {
    height: targetRect.height + spotlightPadding * 2,
    left: targetRect.left - phoneRect.left - spotlightPadding,
    top: targetRect.top - phoneRect.top - spotlightPadding,
    width: targetRect.width + spotlightPadding * 2,
  };
  const coachAtTop = currentStep.coachPosition
    ? currentStep.coachPosition === "top"
    : relativeTarget
      ? relativeTarget.top + relativeTarget.height / 2 > phoneRect.height / 2
      : false;
  const portalHost = guide.portalSelector
    ? contentDocument.querySelector<HTMLElement>(guide.portalSelector)
      ?? document.querySelector<HTMLElement>(guide.portalSelector)
      ?? phone.querySelector<HTMLElement>(guide.portalSelector)
      ?? phone
    : phone;

  return createPortal(
    <div className={`fug-root fug-root-${visibleGuide.id}`} aria-live="polite">
      {mode === "intro" ? (
        <>
          <div className="fug-intro-backdrop" />
          <section className="fug-panel fug-intro-panel" aria-labelledby="fug-intro-title">
            <span className="fug-eyebrow">처음 이용 안내</span>
            <h2 id="fug-intro-title">
              {guideText(guide.introTitle, guide.introTitleAccents)}
            </h2>
            <p>{guideText(guide.introBody, guide.introBodyAccents)}</p>
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
              {guideText(currentStep.title, currentStep.accents)}
            </h2>
            <p>{guideText(currentStep.body, currentStep.bodyAccents)}</p>
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

export function chatGuideStorageKey(userId: string): string {
  return guideStorageKey(CHAT_COMPLETE_KEY, userId);
}

export function pensionPlannerGuideStorageKey(userId: string): string {
  return guideStorageKey(PENSION_PLANNER_COMPLETE_KEY, userId);
}

export function userPickGuideStorageKey(userId: string): string {
  return guideStorageKey(USER_PICK_COMPLETE_KEY, userId);
}
