import { type ReactNode } from "react";

import type { ChatVisualization } from "../api/types";

export function ChatVisualizations({
  visualizations,
  renderVisualization,
}: {
  visualizations: ChatVisualization[];
  renderVisualization: (visualization: ChatVisualization, index: number) => ReactNode;
}) {
  return <>{visualizations.map(renderVisualization)}</>;
}
