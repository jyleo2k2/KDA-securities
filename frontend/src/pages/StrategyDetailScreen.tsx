import type { JSX } from "react";

import { STRATEGIES, type StrategyExploreItem } from "./strategyExplore/strategies";
import "./StrategyDetailScreen.css";

interface StrategyDetailScreenProps {
  onBack: () => void;
}

function selectedStrategy(): StrategyExploreItem {
  const hash = typeof window !== "undefined" ? window.location.hash : "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const id = new URLSearchParams(query).get("strategy");
  return STRATEGIES.find((item) => item.id === id) ?? STRATEGIES[0];
}

export function StrategyDetailScreen({ onBack }: StrategyDetailScreenProps): JSX.Element {
  const strategy = selectedStrategy();

  return (
    <main className="sd-stage" style={{ "--sd-accent": strategy.accent } as React.CSSProperties}>
      <section className="sd-phone" aria-label={`${strategy.name} 상세`}>
        <div className="sd-statusbar">
          <span>9:41</span>
          <span aria-hidden="true">● ● ▰</span>
        </div>

        <header className="sd-header">
          <button type="button" className="sd-back" data-strategy-detail-back onClick={onBack} aria-label="뒤로 가기">‹</button>
          <span className="sd-brand">연금 <em>도우미</em></span>
        </header>

        <div className="sd-scroll">
          <div className="sd-hero">
            <div className="sd-hero-avatar">
              <img src={strategy.img} alt={strategy.name} />
            </div>
            <div className="sd-hero-text">
              <span className="sd-badge">{strategy.directness}</span>
              <h1 className="sd-title">{strategy.name}</h1>
              <p className="sd-desc">{strategy.desc}</p>
            </div>
          </div>

          <section className="sd-card">
            <h2 className="sd-card-title">어떻게 <span>운용되나요?</span></h2>
            <p className="sd-card-body">{strategy.howItWorks}</p>
          </section>

          <section className="sd-card">
            <h2 className="sd-card-title">연금계좌에 <span>이렇게 담아요</span></h2>
            <p className="sd-card-body">{strategy.accountApplication}</p>
            <dl className="sd-facts">
              <div className="sd-fact">
                <dt>포트폴리오 버킷</dt>
                <dd>{strategy.bucket}</dd>
              </div>
              <div className="sd-fact">
                <dt>구현 난이도</dt>
                <dd>{strategy.directness}</dd>
              </div>
            </dl>
          </section>

          <section className="sd-card sd-note">
            <p>전략 설명 안내예요. 미래 수익률을 예측하거나 특정 상품을 추천하지 않으며, 실제 운용·주문은 이용자가 직접 결정해요.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
