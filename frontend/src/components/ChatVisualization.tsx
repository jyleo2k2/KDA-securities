import { useEffect, useState } from "react";
import { donutArcPaths, TARGET_ALLOCATION_COLORS } from "../charts";
import type { ChatVisualization as ChatVisualizationData, SourceEvidence } from "../api/types";

const BOUNDARY_LABELS: Record<SourceEvidence["data_boundary"], string> = {
  verified_knowledge: "공식 안내 근거",
  official_disclosure: "공식 공시",
  official_statistics: "공식 통계",
  news_metadata: "기사 정보",
  news_summary: "기사 요약",
  mock: "계좌 정보",
  engine: "계산 근거",
  user_input: "입력한 정보",
  unavailable: "확인 필요",
};

function numericText(value: string | number, unit: string): string {
  if (unit.toUpperCase() === "KRW") {
    return `${Number(value).toLocaleString("ko-KR")}원`;
  }
  return `${value}${unit}`;
}

function lossText(value: string | number, unit: string): string {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? `-${numericText(Math.abs(numeric), unit)}`
    : `-${numericText(value, unit)}`;
}

export function ChatVisualization({ visualization, sources }: {
  visualization: ChatVisualizationData;
  sources: SourceEvidence[];
}) {
  const isStrategyVisualization = (
    visualization.kind === "sleeve_allocation"
    || visualization.kind === "stress_scenarios"
  );
  const displayTitle = visualization.title;
  const descriptionStyle = isStrategyVisualization
    ? { marginTop: 0 }
    : undefined;

  if (visualization.kind === "tax_summary") {
    return (
      <section className="allocation-chart tax-visualization" aria-label={displayTitle}>
        <h3>{displayTitle}</h3>
        {visualization.description && (
          <p className="visualization-description" style={descriptionStyle}>{visualization.description}</p>
        )}
        <div
          className="tax-summary-grid"
          style={{
            gridTemplateColumns: "minmax(0, 1fr)",
            overflowX: "hidden",
          }}
        >
          {visualization.items.map((item) => (
            <div
              key={item.label}
              style={{
                alignItems: "center",
                columnGap: 12,
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
                minWidth: 0,
                padding: 12,
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  lineHeight: 1.4,
                  minWidth: 0,
                  textAlign: "left",
                  whiteSpace: "nowrap",
                }}
              >
                {item.label}
              </span>
              <strong
                style={{
                  fontSize: "clamp(13px, 3.4vw, 16px)",
                  lineHeight: 1.2,
                  letterSpacing: "-0.02em",
                  marginTop: 0,
                  minWidth: 0,
                  overflowWrap: "normal",
                  textAlign: "right",
                  whiteSpace: "nowrap",
                }}
              >
                {numericText(item.value, item.unit)}
              </strong>
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
      <section className="allocation-chart" aria-label={displayTitle}>
        <h3>{displayTitle}</h3>
        <p className="visualization-description" style={descriptionStyle}>{visualization.description}</p>
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
      <section className="allocation-chart" aria-label={displayTitle}>
        <h3>{displayTitle}</h3>
        <p className="visualization-description" style={descriptionStyle}>{visualization.description}</p>
        <div className="tax-summary-grid">
          {visualization.items.map((item) => (
            <div key={item.label} style={{ minWidth: 0, padding: 12 }}>
              <span style={{ fontSize: 10, lineHeight: 1.4 }}>{item.label}</span>
              <strong
                style={{
                  fontSize: "clamp(16px, 4.5vw, 19px)",
                  lineHeight: 1.2,
                  marginTop: 5,
                  overflowWrap: "anywhere",
                }}
              >
                {visualization.kind === "stress_scenarios"
                  ? lossText(item.value, item.unit)
                  : numericText(item.value, item.unit)}
              </strong>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (visualization.series?.length) {
    return (
      <section className="allocation-chart" aria-label={displayTitle}>
        <h3>{displayTitle}</h3>
        <p className="visualization-description" style={descriptionStyle}>{visualization.description}</p>
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
  const isSleeveAllocation = visualization.kind === "sleeve_allocation";
  const colors = isSleeveAllocation
    ? TARGET_ALLOCATION_COLORS
    : ["#2f8f6b", "#3f7bc4", "#c98a2e", "#d9743f", "#7b5fc0", "#2fa3a3", "#8f9aa6"];
  const selectedItem = selectedIndex === null ? null : visualization.items[selectedIndex];
  const sourceById = new Map(sources.map((source) => [source.evidence_id, source]));
  const evidenceSources = (visualization.evidence_ids ?? [])
    .map((evidenceId) => sourceById.get(evidenceId))
    .filter((source): source is SourceEvidence => Boolean(source));
  const toggle = (index: number) => setSelectedIndex((current) => (current === index ? null : index));
  useEffect(() => {
    if (selectedIndex === null) return;
    const clear = () => setSelectedIndex(null);
    document.addEventListener("click", clear);
    return () => document.removeEventListener("click", clear);
  }, [selectedIndex]);

  return (
    <section className="allocation-chart" aria-label={displayTitle}>
      <h3>{displayTitle}</h3>
      <p className="visualization-description" style={descriptionStyle}>{visualization.description}</p>
      <div className={`allocation-pie-layout${isSleeveAllocation ? " sleeve-allocation-layout" : ""}`}>
        <svg className={`allocation-donut${isSleeveAllocation ? " sleeve-allocation-donut" : ""}`} viewBox="0 0 100 100" aria-label="자산군 비중을 탭해 상세 보기">
          {donutArcPaths(
            visualization.items.map((item) => Number(item.value)),
            48,
            isSleeveAllocation ? 29 : 28,
          ).map((d, index) => {
            const item = visualization.items[index];
            const selected = selectedIndex === index;
            return (
              <path
                key={`${item.label}-${index}`}
                d={d}
                fill={colors[index % colors.length]}
                stroke={isSleeveAllocation ? "none" : undefined}
                className={selectedIndex !== null && !selected ? "is-dim" : ""}
                transform={selected ? "translate(2 0)" : undefined}
                role="button"
                tabIndex={0}
                aria-label={`${item.label} ${item.value}%`}
                onClick={(event) => { event.stopPropagation(); toggle(index); }}
                onPointerDown={(event) => {
                  if (isSleeveAllocation) {
                    event.preventDefault();
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    toggle(index);
                  }
                }}
              />
            );
          })}
          <text x="50" y="43" textAnchor="middle" className="allocation-donut-label">전체</text>
          <text x="50" y="64" textAnchor="middle" className="allocation-donut-total">100%</text>
        </svg>
        <ul className={`allocation-legend${isSleeveAllocation ? " sleeve-allocation-legend" : ""}`}>
          {visualization.items.map((item, index) => (
            <li key={item.label}>
              <button
                type="button"
                className={selectedIndex === index ? "is-selected" : ""}
                onClick={(event) => { event.stopPropagation(); toggle(index); }}
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
