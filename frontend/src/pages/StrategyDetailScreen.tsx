import type { JSX } from "react";

import { STRATEGIES, type StrategyExploreItem } from "./strategyExplore/strategies";
import { StatusBar } from "../components/StatusBar";
import "./StrategyDetailScreen.css";

interface StrategyDetailScreenProps {
  onBack: () => void;
}

const EXAMPLE_ASSET_BARS = [
  { label: "주식 ETF", weight: 6, color: "#4f8a70" },
  { label: "채권 ETF", weight: 3, color: "#7183b1" },
  { label: "현금성 자산", weight: 1, color: "#d8a45e" },
] as const;

const EXAMPLE_EQUITY_SECTOR_BARS = [
  { label: "넓은 시장", weight: 3, color: "#4f8a70" },
  { label: "반도체", weight: 2, color: "#82ad67" },
  { label: "바이오·헬스케어", weight: 2, color: "#d8a45e" },
  { label: "은행·금융", weight: 2, color: "#7183b1" },
  { label: "전력·에너지", weight: 1, color: "#bf7d70" },
] as const;

function selectedStrategy(): StrategyExploreItem {
  const hash = typeof window !== "undefined" ? window.location.hash : "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const id = new URLSearchParams(query).get("strategy");
  return STRATEGIES.find((item) => item.id === id) ?? STRATEGIES[0];
}

export function StrategyDetailScreen({ onBack }: StrategyDetailScreenProps): JSX.Element {
  const strategy = selectedStrategy();

  return (
    <main className="app-phone-stage sd-stage" style={{ "--sd-accent": strategy.accent } as React.CSSProperties}>
      <section className="app-phone-frame sd-phone" aria-label={`${strategy.name} 상세`}>
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

          <section className="sd-allocation-example" aria-labelledby="strategy-allocation-example-title">
            <span className="sd-allocation-kicker">자산배분 예시</span>
            <h2 className="sd-card-title" id="strategy-allocation-example-title">연금계좌 <span>자산배분 예시</span></h2>
            <p className="sd-card-body">주식·채권·현금성 자산을 함께 두고, 주식 안에서도 ETF 섹터를 분산하는 예시입니다.</p>

            <div className="sd-bar" role="img" aria-label="주식 ETF, 채권 ETF, 현금성 자산의 자산배분 예시 바">
              {EXAMPLE_ASSET_BARS.map((item) => (
                <span key={item.label} style={{ flexGrow: item.weight, backgroundColor: item.color }} />
              ))}
            </div>
            <ul className="sd-bar-legend" aria-label="큰 자산군 예시">
              {EXAMPLE_ASSET_BARS.map((item) => (
                <li key={item.label}>
                  <i style={{ backgroundColor: item.color }} />
                  {item.label}
                </li>
              ))}
            </ul>

            <div className="sd-sector-example">
              <strong>주식 안에서는 ETF 분야도 나눠 봐요</strong>
              <div className="sd-bar sd-sector-bar" role="img" aria-label="넓은 시장, 반도체, 바이오 헬스케어, 은행 금융, 전력 에너지 ETF 분야 예시 바">
                {EXAMPLE_EQUITY_SECTOR_BARS.map((item) => (
                  <span key={item.label} style={{ flexGrow: item.weight, backgroundColor: item.color }} />
                ))}
              </div>
              <ul className="sd-bar-legend sd-sector-legend" aria-label="주식 ETF 분야 예시">
                {EXAMPLE_EQUITY_SECTOR_BARS.map((item) => (
                  <li key={item.label}>
                    <i style={{ backgroundColor: item.color }} />
                    {item.label}
                  </li>
                ))}
              </ul>
            </div>

            <p className="sd-allocation-note">막대 크기는 이해를 돕기 위한 예시예요. 실제 비중과 ETF 분야는 투자성향·계좌 규칙·엔진 결과를 확인해 직접 결정해요.</p>
          </section>

          <section className="sd-card sd-operation-guide">
            <h2 className="sd-card-title">전략의 <span>운용 방식</span></h2>
            <p className="sd-card-body">{strategy.howItWorks}</p>
          </section>

          <section className="sd-card sd-account-guide">
            <h2 className="sd-card-title">연금계좌에는 <span>이렇게 나눠요</span></h2>
            <p className="sd-card-body">{strategy.accountApplication}</p>
            <dl className="sd-facts">
              <div className="sd-fact">
                <dt>포트폴리오 내 역할</dt>
                <dd>{strategy.bucket}</dd>
              </div>
              <div className="sd-fact">
                <dt>구현 난이도</dt>
                <dd>{strategy.directness}</dd>
              </div>
            </dl>
          </section>

          <section className="sd-card sd-words" aria-labelledby="strategy-easy-words-title">
            <h2 className="sd-card-title" id="strategy-easy-words-title">핵심 <span>용어 풀이</span></h2>
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
            <p>전략 설명입니다. 미래 수익률을 예측하거나 특정 상품을 추천하지 않으며, 실제 운용·주문은 이용자가 직접 결정합니다.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
