import { useState, type JSX } from "react";

import type { DemoHeroPortfolio } from "../api/types";
import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  heroes: DemoHeroPortfolio[];
  onBack: () => void;
}

const ASSET_LABELS: Record<string, string> = {
  cash: "현금성",
  deposit: "원리금보장",
  bond: "채권",
  domestic_equity: "국내주식",
  global_equity: "글로벌주식",
  alternative: "대체자산",
  eligible_tdf: "적격 TDF",
  default_option: "디폴트옵션",
};

function formatKrw(amount: string): string {
  return `${Math.round(Number(amount)).toLocaleString("ko-KR")}원`;
}

function allocationSummary(hero: DemoHeroPortfolio): string {
  return hero.asset_allocations
    .map((allocation) => `${ASSET_LABELS[allocation.asset_class_code] ?? "기타 자산"} ${allocation.allocation_percent}%`)
    .join(" · ");
}

export function UserPickBenchmarkScreen({ heroes, onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  const [sortBy, setSortBy] = useState<"return" | "likes">("return");
  const sortedHeroes = [...heroes].sort((left, right) => sortBy === "likes"
    ? right.like_summary.count - left.like_summary.count
    : Number(right.past_performance.trailing_12m_return_pct) - Number(left.past_performance.trailing_12m_return_pct));

  return (
    <main className="upb-stage">
      <section className="upb-phone" aria-label="이용자 Pick 포트폴리오">
        <header className="upb-header">
          <button type="button" className="upb-back" aria-label="메인 홈으로 돌아가기" onClick={onBack}>‹</button>
          <div>
            <p>이용자 Pick</p>
            <h1>다른 사람의 연금 구성</h1>
          </div>
        </header>

        <p className="upb-notice">대표 고객 목데이터예요. 과거 12개월 수익률은 미래 수익을 보장하지 않아요.</p>

        <div className="upb-filters" aria-label="정렬 기준">
          <button type="button" aria-pressed={sortBy === "return"} onClick={() => setSortBy("return")}>수익률순</button>
          <button type="button" aria-pressed={sortBy === "likes"} onClick={() => setSortBy("likes")}>좋아요순</button>
        </div>

        <ul className="upb-list">
          {sortedHeroes.map((hero) => (
            <li key={hero.nickname} className="upb-card" data-testid="hero-card" data-hero-name={hero.nickname}>
              <div className="upb-card-heading">
                <div><strong>{hero.nickname}</strong><span>{hero.scenario_name}</span></div>
                <b className={Number(hero.past_performance.trailing_12m_return_pct) < 0 ? "upb-negative" : ""}>{hero.past_performance.trailing_12m_return_pct}%</b>
              </div>
              <p>{allocationSummary(hero)}</p>
              <footer><span>총 연금자산 {formatKrw(hero.total_amount_krw)}</span><span>좋아요 {hero.like_summary.count.toLocaleString("ko-KR")}</span></footer>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
