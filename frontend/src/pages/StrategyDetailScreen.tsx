import type { JSX } from "react";

import { STRATEGIES, type StrategyExploreItem } from "./strategyExplore/strategies";
import { StatusBar } from "../components/StatusBar";
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
        <StatusBar />

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
            <h2 className="sd-card-title">쉽게 말하면 <span>이렇게 해요</span></h2>
            <p className="sd-card-body">{strategy.howItWorks}</p>
          </section>

          <section className="sd-card">
            <h2 className="sd-card-title">연금계좌에는 <span>이렇게 나눠요</span></h2>
            <p className="sd-card-body">{strategy.accountApplication}</p>
            <dl className="sd-facts">
              <div className="sd-fact">
                <dt>이 전략의 자리</dt>
                <dd>{strategy.bucket}</dd>
              </div>
              <div className="sd-fact">
                <dt>구현 난이도</dt>
                <dd>{strategy.directness}</dd>
              </div>
            </dl>
          </section>

          <section className="sd-card sd-words" aria-labelledby="strategy-easy-words-title">
            <h2 className="sd-card-title" id="strategy-easy-words-title">낯선 말 <span>쉽게 보기</span></h2>
            <dl>
              {strategy.easyWords.map((item) => (
                <div key={item.word}>
                  <dt>{item.word}</dt>
                  <dd>{item.meaning}</dd>
                </div>
              ))}
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
