import { conicGradient } from "../charts";
import type { ChatVisualization as ChatVisualizationData } from "../api/types";

function numericText(value: string | number, unit: string): string {
  if (unit.toUpperCase() === "KRW") {
    return `${Number(value).toLocaleString("ko-KR")}원`;
  }
  return `${value}${unit}`;
}

export function ChatVisualization({ visualization }: { visualization: ChatVisualizationData }) {
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

  const colors = ["#4f8a70", "#84ad67", "#d8a45e", "#7183b1", "#bf7d70"];
  const gradientStops = conicGradient(
    visualization.items.map((item) => Number(item.value)),
    colors,
  );
  return (
    <section className="allocation-chart" aria-label={visualization.title}>
      <h3>{visualization.title}</h3>
      <p className="visualization-description">{visualization.description}</p>
      <div className="allocation-pie-layout">
        <div
          aria-label={visualization.items.map((item) => `${item.label} ${item.value}%`).join(", ")}
          className="allocation-donut"
          role="img"
          style={{ background: `conic-gradient(${gradientStops})` }}
        >
          <span>전체<br /><strong>100%</strong></span>
        </div>
        <ul className="allocation-legend">
          {visualization.items.map((item, index) => (
            <li key={item.label}>
              <i style={{ backgroundColor: colors[index % colors.length] }} />
              <span>{item.label}</span>
              <strong>{item.value}%</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
