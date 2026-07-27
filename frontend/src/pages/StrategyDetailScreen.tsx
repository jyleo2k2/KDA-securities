import { useEffect, useState, type JSX } from "react";

import { STRATEGIES, type StrategyExploreItem } from "./strategyExplore/strategies";
import { StatusBar } from "../components/StatusBar";
import "./StrategyDetailScreen.css";

interface StrategyDetailScreenProps {
  onBack: () => void;
  onPartnerBrokerClick?: () => void;
}

const EXAMPLE_ASSET_BARS = [
  { label: "주식 ETF", percent: 60, color: "#4f8a70", description: "성장 기회를 담당하지만 가격 변동이 큰 자산이에요." },
  { label: "채권 ETF", percent: 30, color: "#7183b1", description: "주식의 변동을 완충하고 비교적 안정적인 흐름을 더해요." },
  { label: "현금성 자산", percent: 10, color: "#d8a45e", description: "시장 변동에 대응할 여유와 리밸런싱 재원을 남겨요." },
] as const;

const EXAMPLE_EQUITY_SECTOR_BARS = [
  { label: "시장 전체", percent: 30, color: "#4f8a70", description: "여러 업종에 넓게 분산하는 중심 자산이에요." },
  { label: "반도체", percent: 20, color: "#82ad67", description: "반도체 산업의 성장 흐름을 담는 분야예요." },
  { label: "바이오·헬스케어", percent: 20, color: "#d8a45e", description: "의료와 건강 관련 기업을 담는 분야예요." },
  { label: "은행·금융", percent: 20, color: "#7183b1", description: "은행과 보험 등 금융 기업을 담는 분야예요." },
  { label: "전력·에너지", percent: 10, color: "#bf7d70", description: "전력과 에너지 관련 기업을 담는 분야예요." },
] as const;

type AllocationSelection =
  | { group: "asset"; label: (typeof EXAMPLE_ASSET_BARS)[number]["label"] }
  | { group: "sector"; label: (typeof EXAMPLE_EQUITY_SECTOR_BARS)[number]["label"] }
  | null;

function selectedStrategy(): StrategyExploreItem {
  const hash = typeof window !== "undefined" ? window.location.hash : "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const id = new URLSearchParams(query).get("strategy");
  return STRATEGIES.find((item) => item.id === id) ?? STRATEGIES[0];
}

export function StrategyDetailScreen({
  onBack,
  onPartnerBrokerClick,
}: StrategyDetailScreenProps): JSX.Element {
  const strategy = selectedStrategy();
  const [allocationSelection, setAllocationSelection] = useState<AllocationSelection>(null);
  const selectedAsset = allocationSelection?.group === "asset"
    ? EXAMPLE_ASSET_BARS.find((item) => item.label === allocationSelection.label)
    : undefined;
  const selectedSector = allocationSelection?.group === "sector"
    ? EXAMPLE_EQUITY_SECTOR_BARS.find((item) => item.label === allocationSelection.label)
    : undefined;

  function selectAllocation(selection: Exclude<AllocationSelection, null>): void {
    setAllocationSelection((current) => (
      current?.group === selection.group && current.label === selection.label ? null : selection
    ));
  }

  useEffect(() => {
    if (allocationSelection === null) return;
    const clear = () => setAllocationSelection(null);
    document.addEventListener("click", clear);
    return () => document.removeEventListener("click", clear);
  }, [allocationSelection]);

  return (
    <main className="app-phone-stage sd-stage" style={{ "--sd-accent": strategy.accent } as React.CSSProperties}>
      <section className="app-phone-frame sd-phone" aria-label={`${strategy.name} 상세`}>
        <StatusBar />

        <header className="sd-header">
          <button type="button" className="sd-back" data-strategy-detail-back onClick={onBack} aria-label="뒤로 가기">‹</button>
          <span className="sd-brand">연금 <em>KDA</em></span>
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

            <div className="sd-bar" role="group" aria-label="큰 자산군 비중 예시">
              {EXAMPLE_ASSET_BARS.map((item) => (
                <button
                  type="button"
                  key={item.label}
                  className={`sd-bar-segment${selectedAsset?.label === item.label ? " is-selected" : ""}${selectedAsset && selectedAsset.label !== item.label ? " is-dimmed" : ""}`}
                  style={{ flexGrow: item.percent }}
                  aria-label={`${item.label} ${item.percent}% 자세히 보기`}
                  aria-pressed={selectedAsset?.label === item.label}
                  onClick={(event) => {
                    event.stopPropagation();
                    selectAllocation({ group: "asset", label: item.label });
                  }}
                >
                  <span style={{ backgroundColor: item.color }} />
                </button>
              ))}
            </div>
            <ul className="sd-bar-legend" aria-label="큰 자산군 예시">
              {EXAMPLE_ASSET_BARS.map((item) => (
                <li key={item.label}>
                  <button
                    type="button"
                    className={selectedAsset?.label === item.label ? "is-selected" : ""}
                    aria-pressed={selectedAsset?.label === item.label}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectAllocation({ group: "asset", label: item.label });
                    }}
                  >
                    <i style={{ backgroundColor: item.color }} />
                    {item.label} <span>{item.percent}%</span>
                  </button>
                </li>
              ))}
            </ul>
            {selectedAsset && (
              <div className="sd-allocation-detail" role="status" aria-live="polite">
                <strong>
                  <i style={{ backgroundColor: selectedAsset.color }} />
                  {selectedAsset.label} <span>{selectedAsset.percent}%</span>
                </strong>
                <p>{selectedAsset.description}</p>
              </div>
            )}

            <div className="sd-sector-example">
              <strong>주식 안에서는 ETF 분야도 나눠 봐요</strong>
              <div className="sd-bar sd-sector-bar" role="group" aria-label="주식 ETF 분야 비중 예시">
                {EXAMPLE_EQUITY_SECTOR_BARS.map((item) => (
                  <button
                    type="button"
                    key={item.label}
                    className={`sd-bar-segment${selectedSector?.label === item.label ? " is-selected" : ""}${selectedSector && selectedSector.label !== item.label ? " is-dimmed" : ""}`}
                    style={{ flexGrow: item.percent }}
                    aria-label={`${item.label} 주식 ETF 안에서 ${item.percent}% 자세히 보기`}
                    aria-pressed={selectedSector?.label === item.label}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectAllocation({ group: "sector", label: item.label });
                    }}
                  >
                    <span style={{ backgroundColor: item.color }} />
                  </button>
                ))}
              </div>
              <ul className="sd-bar-legend sd-sector-legend" aria-label="주식 ETF 분야 예시">
                {EXAMPLE_EQUITY_SECTOR_BARS.map((item) => (
                  <li key={item.label}>
                    <button
                      type="button"
                      className={selectedSector?.label === item.label ? "is-selected" : ""}
                      aria-pressed={selectedSector?.label === item.label}
                      onClick={(event) => {
                        event.stopPropagation();
                        selectAllocation({ group: "sector", label: item.label });
                      }}
                    >
                      <i style={{ backgroundColor: item.color }} />
                      {item.label} <span>{item.percent}%</span>
                    </button>
                  </li>
                ))}
              </ul>
              {selectedSector && (
                <div className="sd-allocation-detail sd-sector-detail" role="status" aria-live="polite">
                  <strong>
                    <i style={{ backgroundColor: selectedSector.color }} />
                    {selectedSector.label}
                  </strong>
                  <p>
                    주식 ETF 안에서 <b>{selectedSector.percent}%</b>
                    <span aria-hidden="true"> · </span>
                    전체 자산 기준 <b>{Math.round(selectedSector.percent * EXAMPLE_ASSET_BARS[0].percent / 100)}%</b>
                  </p>
                  <p>{selectedSector.description}</p>
                </div>
              )}
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

          <button
            type="button"
            className="sd-partner-cta"
            onClick={onPartnerBrokerClick}
          >
            제휴 증권사로 이동
          </button>
        </div>
      </section>
    </main>
  );
}
