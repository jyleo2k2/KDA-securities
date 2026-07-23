import { useState } from "react";
import { donutArcPaths } from "../charts";
import type { ChatVisualization as ChatVisualizationData, SourceEvidence } from "../api/types";

const BOUNDARY_LABELS: Record<SourceEvidence["data_boundary"], string> = {
  verified_knowledge: "검증 지식",
  official_disclosure: "공식 공시",
  official_statistics: "공식 통계",
  news_metadata: "뉴스 메타데이터",
  mock: "계좌 데이터",
  engine: "규칙 엔진",
  user_input: "사용자 입력",
  unavailable: "출처 확인 필요",
};

function numericText(value: string | number, unit: string): string {
  if (unit.toUpperCase() === "KRW") {
    return `${Number(value).toLocaleString("ko-KR")}원`;
  }
  return `${value}${unit}`;
}

export function ChatVisualization({ visualization, sources }: {
  visualization: ChatVisualizationData;
  sources: SourceEvidence[];
}) {
  if (visualization.kind === "tax_summary") {
    return (
      <section className="allocation-chart tax-visualization" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="tax-summary-grid">
          {visualization.items.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{numericText(item.value, item.unit)}</strong>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (visualization.kind === "risk_cap") {
    const current = visualization.items.find((item) => item.role === "current");
    const limit = visualization.items.find((item) => item.role === "limit");
    const displayed = current ?? limit;
    const percent = Math.min(Number(displayed?.value ?? 0), 100);
    const summary = current && limit
      ? `${numericText(current.value, current.unit)} / 기준 ${numericText(limit.value, limit.unit)}`
      : `최대 ${numericText(limit?.value ?? 0, limit?.unit ?? "%")}`;
    return (
      <section className="allocation-chart" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="allocation-row">
          <div><span>위험자산</span><strong>{summary}</strong></div>
          <div className="allocation-track" role="img" aria-label={`위험자산 ${summary}`}>
            <span style={{ width: `${percent}%` }} />
          </div>
        </div>
      </section>
    );
  }

  if (visualization.kind === "stress_scenarios" || visualization.kind === "disclosure_comparison") {
    return (
      <section className="allocation-chart" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="tax-summary-grid">
          {visualization.items.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{numericText(item.value, item.unit)}</strong>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (visualization.series?.length) {
    return (
      <section className="allocation-chart" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="projection-series">
          {visualization.series.map((series) => (
            <div className="projection-series-row" key={series.label}>
              <strong>{series.label}</strong>
              <div className="projection-points">
                {series.points.map((point) => (
                  <span key={`${series.label}-${point.position}`} title={`${point.label} ${numericText(point.value, series.unit)}`}>
                    {point.label}<b>{numericText(point.value, series.unit)}</b>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const colors = ["#4f8a70", "#84ad67", "#d8a45e", "#7183b1", "#bf7d70"];
  const selectedItem = selectedIndex === null ? null : visualization.items[selectedIndex];
  const sourceById = new Map(sources.map((source) => [source.evidence_id, source]));
  const evidenceSources = (visualization.evidence_ids ?? [])
    .map((evidenceId) => sourceById.get(evidenceId))
    .filter((source): source is SourceEvidence => Boolean(source));
  const toggle = (index: number) => setSelectedIndex((current) => (current === index ? null : index));

  return (
    <section className="allocation-chart" aria-label={visualization.title}>
      <h3>{visualization.title}</h3>
      <p className="visualization-description">{visualization.description}</p>
      <div className="allocation-pie-layout">
        <svg className="allocation-donut" viewBox="0 0 100 100" aria-label="자산군 비중을 탭해 상세 보기">
          {donutArcPaths(visualization.items.map((item) => Number(item.value))).map((d, index) => {
            const item = visualization.items[index];
            const selected = selectedIndex === index;
            return (
              <path
                key={`${item.label}-${index}`}
                d={d}
                fill={colors[index % colors.length]}
                className={selectedIndex !== null && !selected ? "is-dim" : ""}
                transform={selected ? "translate(2 0)" : undefined}
                role="button"
                tabIndex={0}
                aria-label={`${item.label} ${item.value}%`}
                onClick={() => toggle(index)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    toggle(index);
                  }
                }}
              />
            );
          })}
          <text x="50" y="48" textAnchor="middle">전체</text>
          <text x="50" y="60" textAnchor="middle" className="allocation-donut-total">100%</text>
        </svg>
        <ul className="allocation-legend">
          {visualization.items.map((item, index) => (
            <li key={item.label}>
              <button
                type="button"
                className={selectedIndex === index ? "is-selected" : ""}
                onClick={() => toggle(index)}
              >
                <i style={{ backgroundColor: colors[index % colors.length] }} />
                <span>{item.label}</span>
                <strong>{item.value}%</strong>
              </button>
            </li>
          ))}
        </ul>
      </div>
      {selectedItem && (
        <section className="allocation-detail" aria-live="polite">
          <strong>{selectedItem.label} 상세</strong>
          <p>비중 {selectedItem.value}%</p>
          {evidenceSources.length > 0 && (
            <div className="allocation-detail-sources" aria-label="출처">
              {evidenceSources.map((source) => (
                <span key={source.evidence_id}>
                  {BOUNDARY_LABELS[source.data_boundary]} · {source.label}
                  {source.publisher ? ` · ${source.publisher}` : ""}
                  {source.as_of ? ` · ${source.as_of}` : ""}
                </span>
              ))}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
