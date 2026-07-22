import type { JSX } from "react";

import type { DemoHeroPortfolio } from "../api/types";
import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  currentHero: DemoHeroPortfolio | null;
  heroes: DemoHeroPortfolio[];
  onBack: () => void;
}

export function UserPickBenchmarkScreen({ onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  return (
    <main className="benchmark-html-stage">
      <section className="benchmark-html-frame-wrap" aria-label="투자 벤치마킹하기">
        <iframe
          className="benchmark-html-frame"
          src="/benchmark-html/투자 벤치마킹.dc.html"
          title="투자 벤치마킹하기"
        />
        <button
          className="benchmark-html-back-button"
          type="button"
          aria-label="메인 홈으로 돌아가기"
          onClick={onBack}
        />
      </section>
    </main>
  );
}
