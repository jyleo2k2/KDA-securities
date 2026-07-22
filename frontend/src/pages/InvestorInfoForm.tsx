import { useRef, useState, type JSX } from "react";

import type { InvestmentProfileSubmission } from "../api/types";
import "./InvestorInfoForm.css";

interface QuestionOption {
  value: string;
  label: string;
}

interface QuestionDef {
  id: string;
  num: string;
  title: string;
  grid?: boolean;
  multi?: boolean;
  note?: string;
  options: QuestionOption[];
}

const options = (...items: Array<[string, string]>): QuestionOption[] => items.map(([value, label]) => ({ value, label }));

// The backend is the scoring authority. These values only identify the answer
// selected in the login form, including the existing non-scored context fields.
const QDEFS: QuestionDef[] = [
  { id: "age_band", num: "01", title: "고객님의 연령대는 어떻게 되시나요?", grid: true, options: options(["under_19", "만19세 미만"], ["19_to_40", "만19세~만40세"], ["41_to_50", "만41세~만50세"], ["51_to_64", "만51세~만64세"], ["65_to_79", "만65세~만79세"], ["80_plus", "만80세 이상"]) },
  { id: "total_net_assets", num: "02", title: "고객님의 총 자산규모(순자산)는 어느 정도 되시나요?", options: options(["under_100m", "1억원 미만"], ["100m_to_500m", "1억원 이상~5억원 미만"], ["500m_to_1b", "5억원 이상~10억원 미만"], ["1b_to_2b", "10억원 이상~20억원 미만"], ["over_2b", "20억원 이상"]) },
  { id: "annual_income", num: "03", title: "고객님의 연간 소득 현황은 어느 정도 되시나요?", options: options(["under_20m", "2천만원 미만"], ["20m_to_50m", "2천만원 이상~5천만원 미만"], ["50m_to_70m", "5천만원 이상~7천만원 미만"], ["70m_to_100m", "7천만원 이상~1억원 미만"], ["over_100m", "1억원 이상"]) },
  { id: "financial_asset_share", num: "04", title: "고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?", options: options(["under_10", "10% 미만"], ["10_to_20", "10% ~ 20% 미만"], ["20_to_30", "20% ~ 30% 미만"], ["30_to_50", "30% ~ 50% 미만"], ["over_50", "50% 이상"]) },
  { id: "investment_product_share", num: "05", title: "고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?", options: options(["under_10", "0~9%"], ["10_to_20", "10~19%"], ["20_to_30", "20~29%"], ["30_to_50", "30~49%"], ["over_50", "50% 이상"]) },
  { id: "loan_product_share", num: "06", title: "고객님의 총자산 중 대출성 상품의 비중은 어느 정도 되시나요?", options: options(["under_10", "0~9%"], ["10_to_20", "10~19%"], ["20_to_30", "20~29%"], ["30_to_50", "30~49%"], ["over_50", "50% 이상"]) },
  { id: "investment_experience_product", num: "07", title: "고객님께서 투자경험이 있는 금융상품을 모두 선택해주세요.", multi: true, options: options(["very_low", "예금, CMA, MMF, RP, 국공채 등"], ["low", "채권형펀드, 원금보장형 ELB/DLB, 금융채 등"], ["medium", "혼합형펀드, 원금부분보장형 ELS/DLS, 일반회사채"], ["high", "주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채"], ["very_high", "파생상품펀드, ELW, 선물·옵션, 주식신용거래 등"]) },
  { id: "investment_experience_period", num: "08", title: "금융투자상품 투자경험 기간은 얼마나 되시나요?", options: options(["none", "투자경험 없음"], ["under_1y", "1년 미만"], ["1_to_3y", "1년 이상~3년 미만"], ["over_3y", "3년 이상"]) },
  { id: "investment_purpose", num: "09", title: "고객님께서 금융상품을 투자하는 목적을 모두 선택해주세요.", multi: true, options: options(["education", "교육비"], ["living", "생활비"], ["marriage", "결혼자금"], ["debt", "채무상환"], ["housing", "주택마련자금"], ["growth", "자산증식자금"]) },
  { id: "financial_knowledge", num: "10", title: "금융상품에 대한 지식·이해도는 어느 정도라고 생각하시나요?", options: options(["basic", "금융투자상품에 투자해 본 경험이 없음"], ["partial", "주식, 채권, 펀드 등의 구조와 위험을 일정 부분 이해하고 있음"], ["deep", "주식, 채권, 펀드 등의 구조와 위험을 깊이 있게 이해하고 있음"], ["derivatives", "파생상품을 포함한 대부분의 금융상품 구조와 위험을 이해하고 있음"]) },
  { id: "investment_horizon", num: "11", title: "고객님의 투자 자금의 투자 예정 기간은 얼마나 되시나요?", options: options(["under_1y", "1년 미만"], ["1_to_2y", "1년 이상~2년 미만"], ["2_to_3y", "2년 이상~3년 미만"], ["3_to_5y", "3년 이상~5년 미만"], ["over_5y", "5년 이상"]) },
  { id: "risk_attitude", num: "12", title: "고객님께서 금융상품 투자를 통해 기대하는 수익과 감내할 수 있는 손실의 중요도는 어떻게 되시나요?", options: options(["principal", "투자 수익을 고려하나 원금 보존이 더 중요함"], ["balanced", "원금 보존을 고려하나 투자 수익이 더 중요함"], ["return", "손실 위험이 있더라도 투자 수익이 더 중요함"]) },
  { id: "loss_tolerance", num: "13", title: "기대수익률 및 손실감내도에 가장 가까운 항목을 선택해주세요.", options: options(["limited", "제한적인 손실을 감수하여 시중금리 수준의 수익을 기대"], ["partial", "원금의 일부 손실을 감수하여 시중금리보다 다소 높은 수준의 수익을 기대"], ["principal_loss", "원금 손실을 감수하여 시장수익률과 비슷한 수준의 수익을 기대"], ["beyond_principal", "원금 초과 손실까지 감수하여 시장수익률을 초과하는 높은 수익을 추구"]) },
  { id: "derivative_experience", num: "14", title: "고객님의 파생상품에 대한 투자경험은 얼마나 되시나요?", note: "파생상품 경험은 일반 투자성향 점수와 별도로 기록됩니다.", options: options(["none", "투자경험 없음"], ["under_1y", "1년 미만"], ["1_to_3y", "1년 ~ 3년 미만"], ["over_3y", "3년 이상"]) },
  { id: "vulnerable_investor", num: "15", title: "고객님께서는 취약투자자에 해당되십니까?", note: "취약투자자에게는 손실 가능성과 유의사항을 우선적으로 안내합니다.", options: options(["yes", "예"], ["no", "아니오"]) },
  { id: "validity_consent", num: "16", title: "투자자정보를 24개월간 유효하게 관리하는 데 동의하시나요?", options: options(["agree", "동의"], ["disagree", "미동의"]) },
  { id: "retirement_start_age", num: "17", title: "연금 수령을 시작할 나이를 선택해주세요.", note: "연금 ETF 교육용 추천에만 사용하는 비배점 항목입니다.", options: options(["55", "만 55세"], ["56", "만 56세"], ["57", "만 57세"], ["58", "만 58세"], ["59", "만 59세"], ["60", "만 60세"]) },
];

type Answers = Record<string, number | number[] | null>;

interface InvestorInfoFormProps {
  onBack: () => void;
  onSubmit: (submission: InvestmentProfileSubmission) => Promise<void>;
}

export function InvestorInfoForm({ onBack, onSubmit }: InvestorInfoFormProps): JSX.Element {
  const [answers, setAnswers] = useState<Answers>(() => Object.fromEntries(QDEFS.map((q) => [q.id, q.multi ? [] : null])));
  const [recommend, setRecommend] = useState<"희망" | "미희망" | null>(null);
  const [provide, setProvide] = useState<"제공" | "미제공" | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  function isAnswered(id: string): boolean {
    if (id === "recommend") return recommend !== null;
    if (id === "provide") return provide !== null;
    const question = QDEFS.find((item) => item.id === id);
    const value = answers[id];
    return question?.multi ? Array.isArray(value) && value.length > 0 : value !== null;
  }

  function clearErr(id: string): void { setErrorId((previous) => (previous === id ? null : previous)); }
  function scrollToItem(id: string): void {
    const container = scrollRef.current;
    const element = itemRefs.current[id];
    if (!container || !element) return;
    container.scrollTo({ top: Math.max(0, element.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 12), behavior: "smooth" });
  }
  function toggle(id: string, index: number, multi: boolean | undefined): void {
    setAnswers((previous) => {
      const next = { ...previous };
      if (multi) {
        const current = (previous[id] as number[]) ?? [];
        next[id] = current.includes(index) ? current.filter((value) => value !== index) : [...current, index];
      } else next[id] = index;
      return next;
    });
    clearErr(id);
  }
  async function handleSubmit(): Promise<void> {
    const order = ["recommend", "provide", ...QDEFS.map((q) => q.id)];
    const missing = order.find((id) => !isAnswered(id));
    if (missing) { setErrorId(missing); scrollToItem(missing); return; }
    if (submitting) return;
    setErrorId(null); setSubmitError(null); setSubmitting(true);
    try {
      await onSubmit({
        survey: {
          answers: QDEFS.map((question) => {
            const selected = answers[question.id];
            const indexes = question.multi ? selected as number[] : [selected as number];
            return { question_code: question.id, selected_values: indexes.map((index) => question.options[index].value) };
          }),
        },
        investment_advice_desired: recommend === "희망",
        investor_information_provided: provide === "제공",
      });
    } catch {
      setSubmitError(recommend === "희망" && provide !== "제공" ? "투자권유를 희망하면 투자자정보 제공에 동의해야 합니다." : "설문 결과를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally { setSubmitting(false); }
  }
  function segClass(active: boolean): string { return active ? "iif-seg iif-seg-active" : "iif-seg"; }

  return <div className="iif-page">
    <div className="iif-header"><button type="button" className="iif-header-back" onClick={onBack} aria-label="이전 화면">‹</button><div className="iif-header-title">투자자정보 확인서</div></div>
    <div className="iif-banner">일반금융소비자 투자성향진단</div>
    <div className="iif-scroll" ref={scrollRef}>
      <div className="iif-toggles">
        <div className="iif-toggle-row" ref={(element) => { itemRefs.current.recommend = element; }}><span className="iif-toggle-label">투자권유</span><div className="iif-seg-group"><button type="button" className={segClass(recommend === "희망")} onClick={() => { setRecommend("희망"); clearErr("recommend"); }}>희망</button><button type="button" className={segClass(recommend === "미희망")} onClick={() => { setRecommend("미희망"); clearErr("recommend"); }}>미희망</button></div>{errorId === "recommend" && <div className="iif-error-ring" />}</div>
        <div className="iif-toggle-row" ref={(element) => { itemRefs.current.provide = element; }}><span className="iif-toggle-label">투자자정보</span><div className="iif-seg-group"><button type="button" className={segClass(provide === "제공")} onClick={() => { setProvide("제공"); clearErr("provide"); }}>제공</button><button type="button" className={segClass(provide === "미제공")} onClick={() => { setProvide("미제공"); clearErr("provide"); }}>미제공</button></div>{errorId === "provide" && <div className="iif-error-ring" />}</div>
      </div>
      <div className="iif-divider" />
      {QDEFS.map((question) => <div className="iif-question" key={question.id} ref={(element) => { itemRefs.current[question.id] = element; }}>
        <div className="iif-question-title"><span className="iif-question-num">{question.num}.</span> {question.title}</div><div className="iif-question-divider" />
        <div className="iif-question-body"><div className={question.grid ? "iif-options-grid" : "iif-options-list"}>{question.options.map((option, index) => {
          const selected = question.multi ? ((answers[question.id] as number[]) ?? []).includes(index) : answers[question.id] === index;
          return <button type="button" className={question.grid ? "iif-option" : "iif-option iif-option-list-item"} key={option.value} onClick={() => toggle(question.id, index, question.multi)}>
            <div className={question.multi ? (selected ? "iif-check iif-check-on" : "iif-check") : (selected ? "iif-radio iif-radio-lg iif-radio-on" : "iif-radio iif-radio-lg")}>{selected && (question.multi ? "✓" : <div className="iif-radio-dot iif-radio-dot-lg" />)}</div><span className="iif-option-label iif-option-label-list">{option.label}</span>
          </button>;
        })}</div>{question.note && <div className="iif-note">{question.note}</div>}</div>{errorId === question.id && <div className="iif-question-error" />}
      </div>)}
      {submitError && <p className="iif-note" role="alert">{submitError}</p>}<div className="iif-scroll-spacer" />
    </div>
    <div className="iif-footer"><button type="button" className="iif-cancel" onClick={onBack}>취소</button><button type="button" className="iif-submit" disabled={submitting} onClick={() => void handleSubmit()}>{submitting ? "저장 중..." : "투자자정보확인서 제출"}</button></div>
  </div>;
}
