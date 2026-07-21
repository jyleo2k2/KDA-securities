import { useRef, useState, type JSX } from "react";

import "./InvestorInfoForm.css";

interface QuestionDef {
  id: string;
  num: string;
  title: string;
  grid?: boolean;
  multi?: boolean;
  note?: string;
  options: string[];
}

const QDEFS: QuestionDef[] = [
  {
    id: "q1",
    num: "01",
    title: "고객님의 연령대는 어떻게 되시나요?",
    grid: true,
    options: ["만19세 미만", "만19세~만40세", "만41세~만50세", "만51세~만64세", "만65세~만79세", "만80세 이상"],
  },
  {
    id: "q2",
    num: "02",
    title: "고객님의 연소득(급여, 금융소득 등) 금액은 어느 정도 되시나요?",
    options: ["5천만원 이하", "5천만원 초과 ~ 7천만원", "7천만원 초과 ~ 1억원", "1억원 초과"],
  },
  {
    id: "q3",
    num: "03",
    title: "고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?",
    options: ["10% 미만", "10% ~ 20% 미만", "20% ~ 30% 미만", "30% ~ 50% 미만", "50% 이상"],
  },
  {
    id: "q4",
    num: "04",
    title: "고객님의 전체 금융자산 중 투자성상품(주식, 펀드 등)의 비중은 어느 정도 되시나요?",
    options: ["10% 미만", "10% ~ 20% 미만", "20% ~ 30% 미만", "30% ~ 50% 미만", "50% 이상"],
  },
  {
    id: "q5",
    num: "05",
    title: "고객님께서 투자경험이 있는 금융상품을 모두 선택해주세요.",
    multi: true,
    options: [
      "예금, CMA, MMF, RP, 국공채 등",
      "채권형펀드, 원금보장형 ELB/DLB, 금융채 등",
      "혼합형펀드, 원금부분보장형 ELS/DLS, 일반회사채",
      "주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채",
      "파생상품펀드, ELW, 선물·옵션, 주식신용거래 등",
    ],
  },
  {
    id: "q6",
    num: "06",
    title: "고객님께서 금융상품을 투자하는 목적을 모두 선택해주세요.",
    multi: true,
    options: ["교육비", "생활비", "결혼자금", "채무상환", "주택마련자금", "자산증식자금"],
  },
  {
    id: "q7",
    num: "07",
    title: "고객님의 금융상품 투자를 위한 금융지식/이해도는 어느 정도라고 생각하시나요?",
    note: "(※ 해당 문항은 당일 투자성향 등록 이력이 있는 경우 선택되지 않습니다.)",
    options: [
      "매우낮은위험(CMA, RP 등) 금융상품의 내용만 이해하고 있음",
      "널리 알려진 금융상품(주식, 채권, 펀드 등)의 구조 및 위험 등을 일정 부분 이해하고 있음",
      "널리 알려진 금융상품(주식, 채권, 펀드 등)의 구조 및 위험 등을 깊이 있게 이해하고 있음",
      "파생상품을 포함한 대부분의 금융상품 구조 및 위험 등을 이해하고 있음",
    ],
  },
  {
    id: "q8",
    num: "08",
    title: "고객님의 투자 자금의 투자 예정 기간은 얼마나 되시나요?",
    options: ["1년 미만", "1년 ~ 3년 미만", "3년 이상", "투자기간과 상관없이 만기일까지 보유"],
  },
  {
    id: "q9",
    num: "09",
    title: "고객님께서 금융상품 투자를 통해 기대하는 수익과 감내할 수 있는 손실의 중요도는 어떻게 되시나요?",
    note: "(※ 해당 문항은 당일 투자성향 등록 이력이 있는 경우 선택되지 않습니다.)",
    options: ["투자 수익보다 원금 보존이 더 중요함", "원금 보존보다 투자 수익이 더 중요함", "손실 위험이 있더라도 투자 수익이 중요함"],
  },
  {
    id: "q10",
    num: "10",
    title: "고객님께서 금융상품 투자 시 감내할 수 있는 손실은 어느 정도 되시나요?",
    options: [
      "원금의 10%까지 손실을 감내할 수 있음",
      "원금의 30%까지 손실을 감내할 수 있음",
      "원금의 50%까지 손실을 감내할 수 있음",
      "원금 100% 손실까지 감내할 수 있음",
      "원금 초과 손실까지 감내할 수 있음",
    ],
  },
  {
    id: "q11",
    num: "11",
    title: "고객님의 파생상품(선물·옵션, ELW, ELS/DLS, 파생상품펀드 등)에 대한 투자경험은 얼마나 되시나요?",
    options: ["투자경험 없음", "1년 미만", "1년 ~ 3년 미만", "3년 이상"],
  },
  {
    id: "q12",
    num: "12",
    title: "고객님께서는 취약투자자에 해당되십니까?",
    note:
      "※ 취약투자자란?\n고령투자자/미성년자/금융상품 투자경험이 없는 분 등이 대상이며, 금융상품 투자 시 불이익에 대한 정보를 다른 정보보다 우선하여 설명 받으실 수 있습니다.",
    options: ["예", "아니오"],
  },
];

type Answers = Record<string, number | number[] | null>;

interface InvestorInfoFormProps {
  onBack: () => void;
  onSubmit: () => void;
}

export function InvestorInfoForm({ onBack, onSubmit }: InvestorInfoFormProps): JSX.Element {
  const [answers, setAnswers] = useState<Answers>(() => {
    const initial: Answers = {};
    QDEFS.forEach((q) => {
      initial[q.id] = q.multi ? [] : null;
    });
    return initial;
  });
  const [recommend, setRecommend] = useState<"희망" | "미희망" | null>(null);
  const [provide, setProvide] = useState<"제공" | "미제공" | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  function isAnswered(id: string): boolean {
    if (id === "recommend") return recommend != null;
    if (id === "provide") return provide != null;
    const q = QDEFS.find((x) => x.id === id);
    const value = answers[id];
    return q?.multi ? Array.isArray(value) && value.length > 0 : value != null;
  }

  function clearErr(id: string): void {
    setErrorId((prev) => (prev === id ? null : prev));
  }

  function scrollToItem(id: string): void {
    const container = scrollRef.current;
    const el = itemRefs.current[id];
    if (!container || !el) return;
    const top = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 12;
    container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }

  function toggle(id: string, index: number, multi: boolean | undefined): void {
    setAnswers((prev) => {
      const next = { ...prev };
      if (multi) {
        const current = (prev[id] as number[]) ?? [];
        next[id] = current.includes(index) ? current.filter((x) => x !== index) : [...current, index];
      } else {
        next[id] = index;
      }
      return next;
    });
    clearErr(id);
  }

  function handleSubmit(): void {
    const order = ["recommend", "provide", ...QDEFS.map((q) => q.id)];
    const missing = order.find((id) => !isAnswered(id));
    if (missing) {
      setErrorId(missing);
      scrollToItem(missing);
      return;
    }
    setErrorId(null);
    onSubmit();
  }

  function segClass(active: boolean): string {
    return active ? "iif-seg iif-seg-active" : "iif-seg";
  }

  return (
    <div className="iif-page">
      <div className="iif-header">
        <button type="button" className="iif-header-back" onClick={onBack} aria-label="이전 화면">
          <svg width="11" height="20" viewBox="0 0 11 20" fill="none">
            <path d="M9.5 1L1.5 10L9.5 19" stroke="#1E2124" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div className="iif-header-title">투자자정보 확인서</div>
      </div>

      <div className="iif-banner">일반금융소비자 투자성향진단</div>

      <div className="iif-scroll" ref={scrollRef}>
        <div className="iif-toggles">
          <div
            className="iif-toggle-row"
            ref={(el) => {
              itemRefs.current.recommend = el;
            }}
          >
            <span className="iif-toggle-label">투자권유</span>
            <div className="iif-seg-group">
              <div
                className={segClass(recommend === "희망")}
                onClick={() => {
                  setRecommend("희망");
                  clearErr("recommend");
                }}
              >
                희망
              </div>
              <div
                className={segClass(recommend === "미희망")}
                onClick={() => {
                  setRecommend("미희망");
                  clearErr("recommend");
                }}
              >
                미희망
              </div>
            </div>
            {errorId === "recommend" && <div className="iif-error-ring" />}
          </div>
          <div
            className="iif-toggle-row"
            ref={(el) => {
              itemRefs.current.provide = el;
            }}
          >
            <div className="iif-toggle-label-wrap">
              <span className="iif-toggle-label">투자자정보</span>
              <div className="iif-help-badge">?</div>
            </div>
            <div className="iif-seg-group">
              <div
                className={segClass(provide === "제공")}
                onClick={() => {
                  setProvide("제공");
                  clearErr("provide");
                }}
              >
                제공
              </div>
              <div
                className={segClass(provide === "미제공")}
                onClick={() => {
                  setProvide("미제공");
                  clearErr("provide");
                }}
              >
                미제공
              </div>
            </div>
            {errorId === "provide" && <div className="iif-error-ring" />}
          </div>
        </div>

        <div className="iif-divider" />

        {QDEFS.map((q) => (
          <div
            className="iif-question"
            key={q.id}
            ref={(el) => {
              itemRefs.current[q.id] = el;
            }}
          >
            <div className="iif-question-title">
              <span className="iif-question-num">{q.num}.</span> {q.title}
            </div>
            <div className="iif-question-divider" />
            <div className="iif-question-body">
              {q.grid ? (
                <div className="iif-options-grid">
                  {q.options.map((label, i) => {
                    const selected = answers[q.id] === i;
                    return (
                      <div className="iif-option" key={label} onClick={() => toggle(q.id, i, q.multi)}>
                        <div className={selected ? "iif-radio iif-radio-on" : "iif-radio"}>{selected && <div className="iif-radio-dot" />}</div>
                        <span className="iif-option-label">{label}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="iif-options-list">
                  {q.options.map((label, i) => {
                    const selected = q.multi ? ((answers[q.id] as number[]) ?? []).includes(i) : answers[q.id] === i;
                    return (
                      <div className="iif-option iif-option-list-item" key={label} onClick={() => toggle(q.id, i, q.multi)}>
                        {q.multi ? (
                          <div className={selected ? "iif-check iif-check-on" : "iif-check"}>
                            {selected && (
                              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                                <path d="M3 8.5L6.5 12L13 4.5" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                        ) : (
                          <div className={selected ? "iif-radio iif-radio-lg iif-radio-on" : "iif-radio iif-radio-lg"}>
                            {selected && <div className="iif-radio-dot iif-radio-dot-lg" />}
                          </div>
                        )}
                        <span className="iif-option-label iif-option-label-list">{label}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              {q.note && <div className="iif-note">{q.note}</div>}
            </div>
            {errorId === q.id && <div className="iif-question-error" />}
          </div>
        ))}

        <div className="iif-scroll-spacer" />
      </div>

      <div className="iif-footer">
        <div className="iif-cancel" onClick={onBack}>
          취소
        </div>
        <div className="iif-submit" onClick={handleSubmit}>
          투자자정보확인서 제출
        </div>
      </div>
    </div>
  );
}
