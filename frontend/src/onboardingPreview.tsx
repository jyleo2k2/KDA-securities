import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { MainHomeScreen } from "./pages/MainHomeScreen";
import "./index.css";

// dev 전용 프리뷰: 실제 MainHomeScreen을 계좌 미연동(aggregation=null) 상태로 렌더한다.
// 도넛차트가 나오지 않는 자리에 연그미 마스코트가 들어가는지 확인용. 실제 연결/백엔드는 없음.
const container = document.getElementById("mainhome-preview-root");
if (!container) {
  throw new Error("#mainhome-preview-root element is missing");
}

const noop = () => {};

createRoot(container).render(
  <StrictMode>
    <MainHomeScreen
      aggregation={null}
      displayName="정민재"
      error="이 계정에는 연동된 연금 데이터가 없습니다."
      investmentProfile={null}
      loading={false}
      portfolio={null}
      onOpenChat={noop}
      onOpenSlangi={noop}
      onOpenPlanner={noop}
      onOpenProfile={noop}
      onOpenStrategyExplore={noop}
      onOpenUserPick={noop}
    />
  </StrictMode>,
);
