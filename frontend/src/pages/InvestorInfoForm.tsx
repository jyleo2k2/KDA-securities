import { useState, type JSX } from "react";

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
  multi?: boolean;
  note?: string;
  options: QuestionOption[];
}

const options = (...items: Array<[string, string]>): QuestionOption[] => items.map(([value, label]) => ({ value, label }));

// These values identify answers for the backend scoring engine; scoring remains server-side.
const QDEFS: QuestionDef[] = [
  { id: "age_band", num: "01", title: "고객님의 연령대는 어떻게 되시나요?", options: options(["under_19", "만 19세 미만"], ["19_to_40", "만 19세~만 40세"], ["41_to_50", "만 41세~만 50세"], ["51_to_64", "만 51세~만 64세"], ["65_to_79", "만 65세~만 79세"], ["80_plus", "만 80세 이상"]) },
  { id: "total_net_assets", num: "02", title: "고객님의 총 자산규모(순자산)는 어느 정도 되시나요?", options: options(["under_100m", "1억 원 미만"], ["100m_to_500m", "1억 원 이상~5억 원 미만"], ["500m_to_1b", "5억 원 이상~10억 원 미만"], ["1b_to_2b", "10억 원 이상~20억 원 미만"], ["over_2b", "20억 원 이상"]) },
  { id: "annual_income", num: "03", title: "고객님의 연간 소득 현황은 어느 정도 되시나요?", options: options(["under_20m", "2천만 원 미만"], ["20m_to_50m", "2천만 원 이상~5천만 원 미만"], ["50m_to_70m", "5천만 원 이상~7천만 원 미만"], ["70m_to_100m", "7천만 원 이상~1억 원 미만"], ["over_100m", "1억 원 이상"]) },
  { id: "financial_asset_share", num: "04", title: "고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?", options: options(["under_10", "10% 미만"], ["10_to_20", "10%~20% 미만"], ["20_to_30", "20%~30% 미만"], ["30_to_50", "30%~50% 미만"], ["over_50", "50% 이상"]) },
  { id: "investment_product_share", num: "05", title: "고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?", options: options(["under_10", "0~9%"], ["10_to_20", "10~19%"], ["20_to_30", "20~29%"], ["30_to_50", "30~49%"], ["over_50", "50% 이상"]) },
  { id: "loan_product_share", num: "06", title: "고객님의 총자산 중 대출성 상품의 비중은 어느 정도 되시나요?", options: options(["under_10", "0~9%"], ["10_to_20", "10~19%"], ["20_to_30", "20~29%"], ["30_to_50", "30~49%"], ["over_50", "50% 이상"]) },
  { id: "investment_experience_product", num: "07", title: "고객님께서 투자경험이 있는 금융상품을 모두 선택해 주세요.", multi: true, options: options(["very_low", "예금, CMA, MMF, RP, 국공채 등"], ["low", "채권형펀드, 원금보장형 ELB/DLB, 금융채 등"], ["medium", "혼합형펀드, 원금부분보장형 ELS/DLS, 일반회사채"], ["high", "주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채"], ["very_high", "파생상품펀드, ELW, 선물·옵션, 주식신용거래 등"]) },
  { id: "investment_experience_period", num: "08", title: "금융투자상품 투자경험 기간은 얼마나 되시나요?", options: options(["none", "투자경험 없음"], ["under_1y", "1년 미만"], ["1_to_3y", "1년 이상~3년 미만"], ["over_3y", "3년 이상"]) },
  { id: "investment_purpose", num: "09", title: "고객님께서 금융상품을 투자하는 목적을 모두 선택해 주세요.", multi: true, options: options(["education", "교육비"], ["living", "생활비"], ["marriage", "결혼자금"], ["debt", "채무상환"], ["housing", "주택마련자금"], ["growth", "자산증식자금"]) },
  { id: "financial_knowledge", num: "10", title: "금융상품에 대한 지식·이해도는 어느 정도라고 생각하시나요?", options: options(["basic", "금융투자상품에 투자해 본 경험이 없음"], ["partial", "주식, 채권, 펀드 등의 구조와 위험을 일정 부분 이해하고 있음"], ["deep", "주식, 채권, 펀드 등의 구조와 위험을 깊이 있게 이해하고 있음"], ["derivatives", "파생상품을 포함한 대부분의 금융상품 구조와 위험을 이해하고 있음"]) },
  { id: "investment_horizon", num: "11", title: "고객님의 투자 자금의 투자 예정 기간은 얼마나 되시나요?", options: options(["under_1y", "1년 미만"], ["1_to_2y", "1년 이상~2년 미만"], ["2_to_3y", "2년 이상~3년 미만"], ["3_to_5y", "3년 이상~5년 미만"], ["over_5y", "5년 이상"]) },
  { id: "risk_attitude", num: "12", title: "고객님께서 금융상품 투자를 통해 기대하는 수익과 감내할 수 있는 손실의 중요도는 어떻게 되시나요?", options: options(["principal", "투자 수익을 고려하나 원금 보존이 더 중요함"], ["balanced", "원금 보존을 고려하나 투자 수익이 더 중요함"], ["return", "손실 위험이 있더라도 투자 수익이 더 중요함"]) },
  { id: "loss_tolerance", num: "13", title: "기대수익률 및 손실감내도에 가장 가까운 항목을 선택해 주세요.", options: options(["limited", "제한적인 손실을 감수하여 시중금리 수준의 수익을 기대"], ["partial", "원금의 일부 손실을 감수하여 시중금리보다 다소 높은 수준의 수익을 기대"], ["principal_loss", "원금 손실을 감수하여 시장수익률과 비슷한 수준의 수익을 기대"], ["beyond_principal", "원금 초과 손실까지 감수하여 시장수익률을 초과하는 높은 수익을 추구"]) },
  { id: "derivative_experience", num: "14", title: "고객님의 파생상품에 대한 투자경험은 얼마나 되시나요?", note: "파생상품 경험은 일반 투자성향 점수와 별도로 기록됩니다.", options: options(["none", "투자경험 없음"], ["under_1y", "1년 미만"], ["1_to_3y", "1년~3년 미만"], ["over_3y", "3년 이상"]) },
  { id: "vulnerable_investor", num: "15", title: "고객님께서는 취약투자자에 해당되십니까?", note: "취약투자자에게는 손실 가능성과 유의사항을 우선적으로 안내합니다.", options: options(["yes", "예"], ["no", "아니오"]) },
  { id: "validity_consent", num: "16", title: "투자자정보를 24개월간 유효하게 관리하는 데 동의하시나요?", options: options(["agree", "동의"], ["disagree", "미동의"]) },
  { id: "retirement_start_age", num: "17", title: "연금 수령을 시작할 나이를 선택해 주세요.", note: "연금 ETF 추천에만 사용하는 분류 항목입니다.", options: options(["55", "만 55세"], ["56", "만 56세"], ["57", "만 57세"], ["58", "만 58세"], ["59", "만 59세"], ["60", "만 60세"]) },
];

type Answers = Record<string, number | number[] | null>;
type Recommendation = "희망" | "미희망";
type InformationProvision = "제공" | "미제공";

interface InvestorInfoFormProps {
  onBack: () => void;
  onSubmit: (submission: InvestmentProfileSubmission) => Promise<void>;
}

export function InvestorInfoForm({ onBack, onSubmit }: InvestorInfoFormProps): JSX.Element {
  const [answers, setAnswers] = useState<Answers>(() => Object.fromEntries(QDEFS.map((question) => [question.id, question.multi ? [] : null])));
  const [recommend, setRecommend] = useState<Recommendation | null>(null);
  const [provide, setProvide] = useState<InformationProvision | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const question = QDEFS[questionIndex];
  const isLastQuestion = questionIndex === QDEFS.length - 1;
  const isFirstQuestion = questionIndex === 0;
  const step = questionIndex < 6 ? 0 : questionIndex < 12 ? 1 : 2;

  function isCurrentQuestionAnswered(): boolean {
    const answer = answers[question.id];
    const hasQuestionAnswer = question.multi ? Array.isArray(answer) && answer.length > 0 : answer !== null;
    return hasQuestionAnswer && (!isFirstQuestion || (recommend !== null && provide !== null));
  }

  function selectAnswer(index: number): void {
    if (!question) return;
    setAnswers((previous) => {
      if (!question.multi) return { ...previous, [question.id]: index };
      const selected = (previous[question.id] as number[]) ?? [];
      return { ...previous, [question.id]: selected.includes(index) ? selected.filter((value) => value !== index) : [...selected, index] };
    });
    setError(null);
  }

  async function submit(): Promise<void> {
    if (recommend === "희망" && provide !== "제공") {
      setSubmitError("투자자정보 제공에 동의해야 투자권유를 받을 수 있어요.");
      setQuestionIndex(0);
      return;
    }
    if (submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit({
        survey: {
          answers: QDEFS.map((item) => {
            const selected = answers[item.id];
            const indexes = item.multi ? selected as number[] : [selected as number];
            return { question_code: item.id, selected_values: indexes.map((index) => item.options[index].value) };
          }),
        },
        investment_advice_desired: recommend === "희망",
        investor_information_provided: provide === "제공",
      });
    } catch {
      setSubmitError("설문 결과를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  function goNext(): void {
    if (!isCurrentQuestionAnswered()) {
      setError(isFirstQuestion ? "투자권유·투자자정보 제공 여부와 답변을 모두 선택해 주세요." : "답변을 하나 이상 선택해 주세요.");
      return;
    }
    if (isLastQuestion) {
      void submit();
      return;
    }
    setError(null);
    setQuestionIndex((previous) => previous + 1);
  }

  function goPrevious(): void {
    setError(null);
    setSubmitError(null);
    if (isFirstQuestion) onBack();
    else setQuestionIndex((previous) => previous - 1);
  }

  return <div className="iif-page">
    <header className="iif-header">
      <button type="button" className="iif-header-back" onClick={goPrevious} aria-label="이전 화면">‹</button>
      <h1 className="iif-header-title">투자자정보 확인서</h1>
    </header>
    <div className="iif-banner">일반금융소비자 투자성향진단</div>

    <div className="iif-progress" aria-label={`진행 상황 ${questionIndex + 1} / ${QDEFS.length}`}>
      {[0, 1, 2].map((index) => <span key={index} className={index <= step ? "iif-progress-active" : ""} />)}
      <strong>{step + 1} / 3</strong>
    </div>

    <main className="iif-content">
      {isFirstQuestion && <section className="iif-toggles" aria-label="투자자정보 선택">
        <div className="iif-toggle-row"><span>투자권유</span><div className="iif-segmented" aria-label="투자권유 여부">{(["희망", "미희망"] as const).map((value) => <button type="button" key={value} aria-pressed={recommend === value} className={recommend === value ? `iif-segmented-active ${value === "미희망" ? "iif-segmented-negative" : ""}` : ""} onClick={() => { setRecommend(value); setError(null); }}>{value}</button>)}</div></div>
        <div className="iif-toggle-row"><span>투자자정보 <i aria-hidden="true">?</i></span><div className="iif-segmented" aria-label="투자자정보 제공 여부">{(["제공", "미제공"] as const).map((value) => <button type="button" key={value} aria-pressed={provide === value} className={provide === value ? "iif-segmented-active" : ""} onClick={() => { setProvide(value); setError(null); }}>{value}</button>)}</div></div>
      </section>}
      <section className="iif-question-card" aria-labelledby="iif-question-title">
        <h2 id="iif-question-title"><em>{question.num}.</em> {question.title}</h2>
        <div className={question.id === "age_band" ? "iif-options iif-options-grid" : "iif-options"} aria-label={question.title}>
          {question.options.map((option, index) => {
            const selected = question.multi ? ((answers[question.id] as number[]) ?? []).includes(index) : answers[question.id] === index;
            return <button type="button" key={option.value} className={selected ? "iif-option iif-option-selected" : "iif-option"} aria-pressed={selected} onClick={() => selectAnswer(index)}>
              <span aria-hidden="true" className={question.multi ? "iif-check" : "iif-radio"}>{selected && (question.multi ? "✓" : "")}</span>
              <span>{option.label}</span>
            </button>;
          })}
        </div>
        {question.note && <p className="iif-note">{question.note}</p>}
      </section>
      {(error || submitError) && <p className="iif-error" role="alert">{error ?? submitError}</p>}
    </main>

    <footer className="iif-footer">
      <button type="button" className="iif-secondary" onClick={goPrevious}>{isFirstQuestion ? "취소" : "이전"}</button>
      <button type="button" className="iif-primary" disabled={submitting} onClick={goNext}>{submitting ? "저장 중..." : isLastQuestion ? "투자자정보확인서 제출" : "다음"}</button>
    </footer>
  </div>;
}
