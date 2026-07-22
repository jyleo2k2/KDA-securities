import type { JSX } from "react";

import type { InvestmentProfileAssessment, RiskProfile } from "../api/types";
import "./InvestorResultScreen.css";

interface InvestorResultScreenProps {
  assessment: InvestmentProfileAssessment | null;
  displayName?: string;
  onBack: () => void;
  onStart: () => void;
}

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형", stable_seeking: "안정추구형", risk_neutral: "위험중립형", active: "적극투자형", aggressive: "공격투자형",
};

const PROFILE_DESCRIPTIONS: Record<RiskProfile, string> = {
  stable: "원금 보존을 우선하고 제한적인 가격 변동을 감수하는 안정형입니다.",
  stable_seeking: "안정성을 우선하되 일부 가격 변동을 감수할 수 있는 안정추구형입니다.",
  risk_neutral: "안정성과 수익의 균형을 고려하며 보통 수준의 위험을 감수하는 위험중립형입니다.",
  active: "더 높은 수익 기회를 위해 비교적 큰 가격 변동을 감수하는 적극투자형입니다.",
  aggressive: "높은 수익을 추구하며 큰 가격 변동과 손실 가능성을 감수하는 공격투자형입니다.",
};

const GRADE_ROWS: Array<{ label: string; flexFilled: number; flexEmpty: number; width: string; barColor: string; labelColor: string; highlight?: boolean }> = [
  { label: "안정형", flexFilled: 1, flexEmpty: 5, width: "16%", barColor: "#22A94D", labelColor: "#166F39" },
  { label: "안정추구형", flexFilled: 2, flexEmpty: 4, width: "80%", barColor: "#7FC24A", labelColor: "#5E9A2E" },
  { label: "위험중립형", flexFilled: 3, flexEmpty: 3, width: "87%", barColor: "#FDC526", labelColor: "#B7791F" },
  { label: "적극투자형", flexFilled: 5, flexEmpty: 1, width: "92%", barColor: "#F08A3C", labelColor: "#C4661E" },
  { label: "공격투자형", flexFilled: 6, flexEmpty: 0, width: "96%", barColor: "#E0453A", labelColor: "#C0392B", highlight: true },
];

const CHART_BARS: Array<{ heightPct: number; dotColor: string; barBg: string; final?: boolean }> = [
  { heightPct: 46, dotColor: "#22A94D", barBg: "#EAF7F0" },
  { heightPct: 58, dotColor: "#7FC24A", barBg: "#F3F8E8" },
  { heightPct: 70, dotColor: "#FDC526", barBg: "#FFF6DE" },
  { heightPct: 84, dotColor: "#F08A3C", barBg: "#FDECD9" },
  { heightPct: 100, dotColor: "#E0453A", barBg: "#FCE6E4", final: true },
];

const CHART_LABELS = [
  { text: "안정형", color: "#3E8B5D", size: "10.5px", weight: 700 },
  { text: "안정추구형", color: "#5E9A2E", size: "10.5px", weight: 700 },
  { text: "위험중립형", color: "#B7791F", size: "10.5px", weight: 700 },
  { text: "적극투자형", color: "#C4661E", size: "10.5px", weight: 700 },
  { text: "공격투자형", color: "#C0392B", size: "11px", weight: 800 },
];

export function InvestorResultScreen({ assessment, displayName, onBack, onStart }: InvestorResultScreenProps): JSX.Element {
  const profileLabel = assessment ? PROFILE_LABELS[assessment.risk_profile] : "결과 확인 중";
  const assessedOn = assessment?.assessed_on ?? "-";
  const validUntil = assessment?.valid_until ?? "-";
  const profileIndex = assessment ? Object.keys(PROFILE_LABELS).indexOf(assessment.risk_profile) : -1;
  const profileDescription = assessment ? PROFILE_DESCRIPTIONS[assessment.risk_profile] : "설문 결과를 확인하고 있습니다.";
  const customerName = displayName?.trim() || "고객";
  return (
    <div className="irs-page">
      <div className="irs-header">
        <button type="button" className="irs-header-back" onClick={onBack} aria-label="이전 화면">
          <svg width="11" height="20" viewBox="0 0 11 20" fill="none">
            <path d="M9.5 1L1.5 10L9.5 19" stroke="#1E2124" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span className="irs-header-title">투자자정보 확인서</span>
      </div>

      <div className="irs-scroll">
        <div className="irs-card">
          <div className="irs-share-row">
            <div className="irs-share-btn">
              <span>저장/공유하기</span>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
                <path d="M18 13v6a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h6" stroke="#4A5058" strokeWidth="2" strokeLinecap="round" />
                <path d="M14 3h7v7M21 3l-9 9" stroke="#4A5058" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div className="irs-tags">
            <span className="irs-tag">투자권유희망</span>
            <span className="irs-tag">투자자정보제공</span>
          </div>

          <div className="irs-lead">{customerName}님의 투자성향은</div>
          <div className="irs-type">
            {profileLabel} <span className="irs-type-suffix">입니다.</span>
          </div>

          <div className="irs-divider" />
          <div className="irs-meta">
            <span>최근 진단일 : {assessedOn}</span>
            <span>성향 만료일 : {validUntil}</span>
          </div>
        </div>

        <div className="irs-card irs-card-spaced">
          <div className="irs-card-title">투자자성향 분석 결과</div>

          <div className="irs-chart">
            {CHART_BARS.map((bar, i) => (
              <div className="irs-chart-col" key={i} style={{ height: `${bar.heightPct}%` }}>
                {i === profileIndex ? (
                  <div className="irs-chart-dot irs-chart-dot-final">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                      <path d="M7 12.5l3 3 7-7" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                ) : (
                  <div className="irs-chart-dot" style={{ borderColor: bar.dotColor }} />
                )}
                <div className="irs-chart-bar" style={{ background: bar.barBg }} />
              </div>
            ))}
          </div>
          <div className="irs-chart-labels">
            {CHART_LABELS.map((label) => (
              <div key={label.text} className="irs-chart-label" style={{ color: label.color, fontSize: label.size, fontWeight: label.weight }}>
                {label.text}
              </div>
            ))}
          </div>

          <div className="irs-desc">
            {profileDescription} 신한 개인 일반투자자정보 확인서의 배점 기준으로 산출한 결과이며, ETF 교육용 안내는 이 성향과 보유 연금계좌 규칙 안에서만 제공합니다.
          </div>
        </div>

        <div className="irs-card irs-card-spaced">
          <div className="irs-card-title">투자자성향별 적합한 투자성 상품</div>

          <div className="irs-grade-header">
            <div className="irs-grade-header-spacer" />
            <div className="irs-grade-header-col">
              6등급
              <div className="irs-grade-header-sub">매우낮은<br />위험</div>
            </div>
            <div className="irs-grade-header-col">
              5등급
              <div className="irs-grade-header-sub">낮은위험</div>
            </div>
            <div className="irs-grade-header-col">
              4등급
              <div className="irs-grade-header-sub">보통위험</div>
            </div>
            <div className="irs-grade-header-col">
              3등급
              <div className="irs-grade-header-sub">다소높은<br />위험</div>
            </div>
            <div className="irs-grade-header-col">
              2등급
              <div className="irs-grade-header-sub">높은위험</div>
            </div>
            <div className="irs-grade-header-col">
              1등급
              <div className="irs-grade-header-sub">매우높은<br />위험</div>
            </div>
          </div>

          <div className="irs-grade-rows">
            {GRADE_ROWS.map((row) => {
              const highlighted = row.label === profileLabel;
              return <div className={highlighted ? "irs-grade-row irs-grade-row-highlight" : "irs-grade-row"} key={row.label}>
                <div className="irs-grade-row-label" style={{ color: row.labelColor, fontWeight: highlighted ? 800 : 700 }}>
                  {row.label}
                </div>
                <div className="irs-grade-row-bar-wrap" style={{ flex: row.flexFilled }}>
                  <div className="irs-grade-row-bar" style={{ background: row.barColor, width: row.width }} />
                </div>
                {row.flexEmpty > 0 && <div style={{ flex: row.flexEmpty }} />}
              </div>;
            })}
          </div>
        </div>

        <div className="irs-scroll-spacer" />
      </div>

      <div className="irs-footer">
        <div className="irs-start" onClick={onStart}>
          서비스 시작하기
        </div>
      </div>
    </div>
  );
}
