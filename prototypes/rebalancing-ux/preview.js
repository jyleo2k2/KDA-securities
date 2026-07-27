const frameBefore = document.querySelector("#frame-before");
const frameAfter = document.querySelector("#frame-after");
const afterCaption = document.querySelector("#after-caption");
const footBefore = document.querySelector("#foot-before");
const footAfter = document.querySelector("#foot-after");
const metricScroll = document.querySelector("#metric-scroll");
const metricHscroll = document.querySelector("#metric-hscroll");
const metricHeight = document.querySelector("#metric-height");
const resetButton = document.querySelector("#reset-btn");
const allButton = document.querySelector("#all-btn");
const widthButtons = [...document.querySelectorAll(".seg-btn[data-width]")];
const fixInputs = [...document.querySelectorAll("#toggle-list input[type='checkbox'][data-fix]")];

const portfolioRows = [
  { name: "핵심 주식", current: 19.6, target: 38.6, status: "조금 더 채우기", statusClass: "status-underweight_after_contribution" },
  { name: "실물자산(금·리츠 등)", current: 0.0, target: 4.8, status: "조금 더 채우기", statusClass: "status-underweight_after_contribution" },
  { name: "전술 자산", current: 28.4, target: 22.0, status: "계획 안", statusClass: "status-within_drift_band" },
  { name: "채권", current: 32.0, target: 28.0, status: "계획 안", statusClass: "status-within_drift_band" },
  { name: "현금성 자산", current: 20.0, target: 6.6, status: "계획 안", statusClass: "status-within_drift_band" },
];

const driftRows = [
  { name: "핵심 주식", drift: -19.0, amount: "부족 약 916만원" },
  { name: "실물자산", drift: -4.8, amount: "부족 약 231만원" },
];

const sectors = [
  { name: "채권", value: 25, color: "#4f8a70" },
  { name: "반도체", value: 17, color: "#84ad67" },
  { name: "바이오·헬스케어", value: 14, color: "#d8a45e" },
  { name: "소비재·음식료", value: 12, color: "#7183b1" },
  { name: "은행·금융", value: 12, color: "#bf7d70" },
  { name: "원자력·전력", value: 10, color: "#8b76ad" },
  { name: "리츠·부동산", value: 10, color: "#5f9c9c" },
];

const fixNames = {
  lead: "결론 우선",
  bars: "드리프트 바",
  nest: "중첩 해소",
  defer: "일반 예시 접기",
  hedge: "단서 압축",
  type: "글자·금액 보강",
};

let selectedWidth = 390;

function getFixes() {
  return Object.fromEntries(fixInputs.map((input) => [input.dataset.fix, input.checked]));
}

function statusBarMarkup() {
  return `
    <div class="ios-statusbar" aria-label="상태 표시줄">
      <span class="ios-statusbar-time">9:41</span>
      <span class="ios-statusbar-island" aria-hidden="true"><span class="ios-statusbar-lens"></span></span>
      <span class="ios-statusbar-icons" aria-hidden="true">
        <svg width="18" height="12" viewBox="0 0 18 12" fill="none" style="stroke:none">
          <path fill="currentColor" d="M10 3c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v8c0 .552-.448 1-1 1h-1c-.552 0-1-.448-1-1V3Z"/>
          <path fill="currentColor" d="M15 1c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v10c0 .552-.448 1-1 1h-1c-.552 0-1-.448-1-1V1Z"/>
          <path fill="currentColor" d="M5 6.5c0-.552.448-1 1-1h1c.552 0 1 .448 1 1V11c0 .552-.448 1-1 1H6c-.552 0-1-.448-1-1V6.5Z"/>
          <path fill="currentColor" d="M0 9c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v2c0 .552-.448 1-1 1H1c-.552 0-1-.448-1-1V9Z"/>
        </svg>
        <svg width="17" height="11.834" viewBox="0 0 17 11.834" fill="none" style="stroke:none">
          <path fill="currentColor" fill-rule="evenodd" clip-rule="evenodd" d="M8.5 2.588c2.467 0 4.839.967 6.627 2.702.134.134.35.132.482-.004l1.287-1.326a.352.352 0 0 0-.003-.518c-4.692-4.589-12.094-4.589-16.786 0a.352.352 0 0 0-.004.518L1.39 5.286c.132.136.348.138.482.004C3.66 3.555 6.034 2.588 8.5 2.588Zm.036 4.001c1.355 0 2.662.514 3.667 1.443.135.132.349.129.482-.006l1.285-1.326a.353.353 0 0 0-.006-.522c-3.059-2.904-7.796-2.904-10.856 0a.353.353 0 0 0-.009.522L4.39 8.026c.132.135.346.138.482.006 1.004-.928 2.31-1.442 3.664-1.443Zm2.614 2.588a.35.35 0 0 1-.105.262l-2.223 2.29a.353.353 0 0 1-.494 0l-2.223-2.29a.35.35 0 0 1-.105-.262.353.353 0 0 1 .115-.258c1.42-1.225 3.5-1.225 4.92 0a.353.353 0 0 1 .115.258Z"/>
        </svg>
        <svg width="27.4" height="13" viewBox="0 0 28 13" fill="none" style="stroke:none">
          <rect x=".5" y=".5" width="24" height="12" rx="3.8" stroke="currentColor" stroke-width="1" stroke-opacity=".35" vector-effect="non-scaling-stroke"/>
          <rect x="2" y="2" width="17" height="9" rx="2.2" fill="currentColor"/>
          <path d="M26.5 4.5v4c.8-.34 1.3-1.1 1.3-2s-.5-1.66-1.3-2Z" fill="currentColor" fill-opacity=".4"/>
        </svg>
      </span>
    </div>`;
}

function chatHeaderMarkup() {
  return `
    <header class="chat-topbar">
      <div class="chat-top-left">
        <button type="button" class="back-button" aria-label="뒤로">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <button type="button" class="history-button">지난 대화</button>
      </div>
      <div class="chat-top-right">
        <span class="logout-label">로그아웃</span>
        <span class="profile-avatar" aria-label="프로필">
          <svg width="27" height="27" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <circle cx="16" cy="16" r="15"/>
            <circle cx="16" cy="11" r="5"/>
            <path d="M7.5 27c.8-6 4-9 8.5-9s7.7 3 8.5 9"/>
          </svg>
        </span>
      </div>
    </header>`;
}

function tableMarkup() {
  const rows = portfolioRows.map((row) => `
    <tr>
      <td>${row.name}</td>
      <td>${row.current.toFixed(1)}%</td>
      <td>${row.target.toFixed(1)}%</td>
      <td><span class="rebalance-status ${row.statusClass}">${row.status}</span></td>
    </tr>`).join("");

  return `
    <div class="portfolio-review-table-wrap">
      <table class="portfolio-review-table">
        <thead><tr><th>자산군</th><th>현재</th><th>목표</th><th>상태</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function driftMarkup(showAmounts) {
  const rows = driftRows.map((row) => {
    const directionClass = row.drift < 0 ? "is-negative" : "is-positive";
    const width = Math.min(Math.abs(row.drift) / 20 * 100, 100).toFixed(1);
    const sign = row.drift > 0 ? "+" : "";
    const amount = showAmounts ? `<span class="drift-amount">${row.amount}</span>` : "";
    return `
      <li class="drift-row">
        <div class="drift-row-head">
          <strong>${row.name}</strong>
          <span>${sign}${row.drift.toFixed(1)}%p ${amount}</span>
        </div>
        <div class="drift-track" aria-label="${row.name} 목표 대비 ${Math.abs(row.drift).toFixed(1)}퍼센트포인트 부족">
          <span class="drift-bar ${directionClass}" style="width:${width}%"></span>
        </div>
      </li>`;
  }).join("");

  return `
    <section class="drift-panel" aria-label="목표 대비 비중 차이">
      <div class="drift-heading"><strong>목표에서 벗어난 자산군</strong><span>0을 기준으로 비교</span></div>
      <div class="drift-scale" aria-hidden="true"><i></i></div>
      <ul class="drift-list">${rows}</ul>
      <div class="within-band-summary"><span>나머지 자산군</span><strong>점검 범위 안 3개</strong></div>
      <details class="numeric-table-details">
        <summary><span>숫자로 보기</span><em class="details-action" aria-hidden="true"></em></summary>
        ${tableMarkup()}
      </details>
    </section>`;
}

function overlapMarkup(compact) {
  if (!compact) {
    return `
      <section class="overlap-check">
        <strong>ETF 쏠림 확인</strong>
        <p>보유 ETF가 비슷한 역할에 몰렸는지 목표 비중과 비교했어요.</p>
        <p>후보 ETF가 과거에 같이 움직인 정도는 최대 47.2%예요. 구성종목 중복률과는 달라요.</p>
      </section>`;
  }

  return `
    <section class="overlap-check">
      <strong>ETF 쏠림 확인</strong>
      <p>보유 비중과 후보 ETF의 과거 동행 정도를 함께 확인했어요.</p>
      <details class="hedge-details">
        <summary><span>어떻게 계산했나요?</span><em class="details-action" aria-hidden="true"></em></summary>
        <div class="details-copy">
          <p>보유 ETF가 비슷한 역할에 몰렸는지 목표 비중과 비교했어요.</p>
          <p>후보 ETF가 과거에 같이 움직인 정도는 최대 47.2%예요. 구성종목 중복률과는 달라요.</p>
        </div>
      </details>
    </section>`;
}

function leadMarkup(promoted) {
  if (!promoted) {
    return `
      <section class="portfolio-review-lead">
        <span>먼저 볼 내용</span>
        <strong>2개 자산군의 비중을 확인해 보세요</strong>
        <p>먼저 비중이 벗어난 자산군을 확인하고, 새 납입금으로 차이를 줄이는 순서로 보면 돼요.</p>
      </section>`;
  }

  return `
    <section class="portfolio-review-lead">
      <span>먼저 볼 내용</span>
      <strong>핵심 주식이 목표보다 19%p 적어요</strong>
      <p>현재 19.6%, 목표 38.6%예요. 새 납입금으로 부족한 비중부터 줄여가는 순서로 확인해 보세요.</p>
      <div class="lead-meta"><span>IRP</span><span>위험중립형</span><span>코어·위성 전략</span></div>
    </section>`;
}

function sectorGradient() {
  let start = 0;
  const stops = sectors.map((sector) => {
    const end = start + sector.value;
    const stop = `${sector.color} ${start}% ${end}%`;
    start = end;
    return stop;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

function sectorMarkup() {
  const legend = sectors.map((sector) => `
    <li><i style="background:${sector.color}"></i><span>${sector.name}</span><strong>${sector.value}%</strong></li>`).join("");

  return `
    <section class="portfolio-sector-guide">
      <header>
        <span>ETF 섹터 분산 예시</span>
        <h4>위험중립형 ETF 분야 예시</h4>
        <p>투자성향에 따른 ETF 섹터 비중 예시입니다. 실제 계산 결과나 계좌별 한도는 변경하지 않습니다.</p>
      </header>
      <div class="portfolio-sector-donut" style="background:${sectorGradient()}">
        <span class="portfolio-sector-donut-center">전체<strong>100%</strong></span>
      </div>
      <ul class="portfolio-sector-legend">${legend}</ul>
      <p class="portfolio-sector-guide-note">여기서는 ETF가 다루는 분야만 보여드려요. "사세요"라는 추천이나 미래 수익 예측은 아니에요.</p>
    </section>`;
}

function cadenceMarkup() {
  return `
    <section class="cadence-block">
      <strong>리밸런싱 주기: 12개월마다</strong>
      <span>각 자산 유형별로 ±5.0%p만큼의 차이가 날 수 있어요.</span>
    </section>`;
}

function deferredMarkup() {
  return `
    <details class="deferred-details">
      <summary>
        <span class="details-title"><small>참고</small><strong>ETF 분야 예시와 점검 주기</strong></span>
        <em class="details-action" aria-hidden="true"></em>
      </summary>
      <div class="deferred-body">${sectorMarkup()}${cadenceMarkup()}</div>
    </details>`;
}

function summaryMarkup() {
  return `
    <section class="portfolio-review-summary" aria-label="계좌 요약">
      <div><span>현재 평가금액</span><strong>4,820만원</strong></div>
      <div><span>계좌에서 허용하는 최대 비율</span><strong>70.0%</strong></div>
      <div><span>가격이 크게 움직일 수 있는 자산</span><strong>70.0%</strong></div>
    </section>`;
}

function riskDetailsMarkup() {
  return `
    <details class="portfolio-review-details">
      <summary>
        <span class="details-title"><small>2단계</small><strong>위험과 수익률 계산 근거</strong></span>
        <em class="details-action" aria-hidden="true"></em>
      </summary>
      <div class="details-copy">
        <p>계좌 한도와 자산군별 비중, 과거 가격 변동 자료를 함께 확인했어요.</p>
        <p class="portfolio-review-warning">과거 실적은 미래 성과를 보장하지 않습니다.</p>
      </div>
    </details>`;
}

function backendDetailsMarkup() {
  const items = [
    ["위험중립형의 코어·위성 전략", "핵심 자산을 중심에 두고 일부 자산으로 분산 범위를 넓히는 구조예요."],
    ["목표 자산배분", "계좌 유형과 투자성향에 맞춘 목표 비중을 자산군별로 비교해요."],
    ["장기 계산에 쓰는 수익률 가정", "과거 장기 자료를 비교하기 위한 계산 입력값이며 미래 성과를 뜻하지 않아요."],
    ["ETF 분야 살펴보기", "ETF가 담는 분야와 비중을 확인해 특정 분야 쏠림을 살펴봐요."],
  ];

  return items.map(([title, copy]) => `
    <details class="backend-detail">
      <summary><span class="details-title"><strong>${title}</strong></span><em class="details-action" aria-hidden="true"></em></summary>
      <div class="details-copy"><p>${copy}</p></div>
    </details>`).join("");
}

function portfolioMarkup(fixes) {
  const promotedLead = fixes.lead ? leadMarkup(true) : "";
  const originalLead = fixes.lead ? "" : leadMarkup(false);
  const allocationView = fixes.bars ? driftMarkup(fixes.type) : tableMarkup();
  const examples = fixes.defer ? deferredMarkup() : `${sectorMarkup()}${cadenceMarkup()}`;

  return `
    <section class="portfolio-review">
      <header>
        <span>계산으로 비교한 결과</span>
        <h3>보유 ETF 비율 점검</h3>
        <p>IRP · 코어·위성 전략</p>
      </header>
      ${promotedLead}
      <section class="portfolio-review-priority">
        <header><small>1단계</small><h4>자산 구성과 조정 기준</h4></header>
        <div class="portfolio-review-details-body">
          ${overlapMarkup(fixes.hedge)}
          ${allocationView}
        </div>
      </section>
      ${examples}
      ${originalLead}
      ${summaryMarkup()}
      ${riskDetailsMarkup()}
      <p class="portfolio-review-disclaimer">이 서비스는 자동 매도하지 않습니다. 새 납입금으로 목표보다 부족한 자산군을 우선 보완하는 방법을 안내합니다.</p>
      ${backendDetailsMarkup()}
    </section>`;
}

function composerMarkup() {
  return `
    <footer class="composer-wrap">
      <div class="composer">
        <textarea rows="1" readonly aria-label="질문 입력" placeholder="예: 리밸런싱은 왜 해야 해?"></textarea>
        <button type="button" aria-label="질문 보내기">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21 3-7.2 18-3.7-7.1L3 10.2 21 3Z"/><path d="m10.1 13.9 4.8-4.8"/></svg>
        </button>
      </div>
      <p>AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
    </footer>`;
}

function renderPhone(frame, fixes = {}) {
  const classes = [
    fixes.nest ? "phone-fix-nest" : "",
    fixes.type ? "phone-fix-type" : "",
  ].filter(Boolean).join(" ");

  frame.className = `app-phone-frame ${classes}`.trim();
  frame.style.width = `${selectedWidth}px`;
  frame.innerHTML = `
    ${statusBarMarkup()}
    <div class="chat-app">
      ${chatHeaderMarkup()}
      <div class="conversation-viewport">
        <div class="conversation-content">
          <div class="message-row user">
            <div class="message-group"><div class="message-bubble">리밸런싱 점검해줘</div></div>
          </div>
          <div class="message-row assistant">
            <span class="assistant-avatar" aria-hidden="true">연금</span>
            <div class="message-group">
              <div class="message-bubble">
                <div class="answer-content">
                  <span class="intent-pill">연금 운용전략</span>
                  <p class="message-copy">위험중립형 기준으로 한 코어·위성 전략의 리밸런싱 결과입니다.</p>
                  ${portfolioMarkup(fixes)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      ${composerMarkup()}
    </div>`;
}

function visibleTableWraps(frame) {
  return [...frame.querySelectorAll(".portfolio-review-table-wrap")]
    .filter((tableWrap) => !tableWrap.closest("details:not([open])"))
    .filter((tableWrap) => tableWrap.getClientRects().length > 0);
}

function measureFrame(frame) {
  const viewport = frame.querySelector(".conversation-viewport");
  const lead = frame.querySelector(".portfolio-review-lead");
  const answer = frame.querySelector(".assistant .message-bubble");
  const viewportRect = viewport.getBoundingClientRect();
  const leadRect = lead.getBoundingClientRect();
  const leadTop = leadRect.top - viewportRect.top + viewport.scrollTop;
  const revealAllowance = Math.min(leadRect.height, 32);
  const scrollToLead = Math.max(0, Math.ceil(leadTop - viewport.clientHeight + revealAllowance));
  const hasHorizontalScroll = visibleTableWraps(frame)
    .some((tableWrap) => tableWrap.scrollWidth > tableWrap.clientWidth + 1);

  return {
    scroll: scrollToLead,
    horizontal: hasHorizontalScroll,
    height: Math.round(answer.getBoundingClientRect().height),
  };
}

function formatNumber(value) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

function reduction(before, after) {
  if (before <= 0 || after >= before) return 0;
  return Math.round((before - after) / before * 100);
}

function updateMetrics() {
  const before = measureFrame(frameBefore);
  const after = measureFrame(frameAfter);
  const heightReduction = reduction(before.height, after.height);

  metricScroll.textContent = `${formatNumber(after.scroll)}px`;
  metricHscroll.textContent = after.horizontal ? "있음" : "없음";
  metricHeight.textContent = `${formatNumber(after.height)}px`;

  footBefore.textContent = `결론까지 ${formatNumber(before.scroll)}px · 가로 스크롤 ${before.horizontal ? "있음" : "없음"} · 답변 ${formatNumber(before.height)}px`;
  footAfter.textContent = `결론까지 ${formatNumber(before.scroll)}px → ${formatNumber(after.scroll)}px · 가로 스크롤 ${after.horizontal ? "있음" : "없음"} · 답변 ${formatNumber(before.height)}px → ${formatNumber(after.height)}px${heightReduction ? `, ${heightReduction}% 감소` : ""}`;
}

let measureFrameRequest = 0;

function scheduleMeasure() {
  cancelAnimationFrame(measureFrameRequest);
  measureFrameRequest = requestAnimationFrame(() => {
    requestAnimationFrame(updateMetrics);
  });
}

function updateCaption(fixes) {
  const active = Object.entries(fixes).filter(([, enabled]) => enabled).map(([key]) => fixNames[key]);
  if (active.length === 0) {
    afterCaption.textContent = "토글을 켜보세요";
  } else if (active.length <= 3) {
    afterCaption.textContent = active.join(" · ");
  } else {
    afterCaption.textContent = `${active.length}개 제안 적용`;
  }
}

function render() {
  const fixes = getFixes();
  renderPhone(frameBefore, {});
  renderPhone(frameAfter, fixes);
  updateCaption(fixes);
  scheduleMeasure();
}

fixInputs.forEach((input) => input.addEventListener("change", render));

resetButton.addEventListener("click", () => {
  fixInputs.forEach((input) => { input.checked = false; });
  render();
});

allButton.addEventListener("click", () => {
  fixInputs.forEach((input) => { input.checked = true; });
  render();
});

widthButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedWidth = Number(button.dataset.width);
    widthButtons.forEach((candidate) => candidate.classList.toggle("is-on", candidate === button));
    render();
  });
});

[frameBefore, frameAfter].forEach((frame) => {
  frame.addEventListener("toggle", scheduleMeasure, true);
});

window.addEventListener("resize", scheduleMeasure);

render();
document.fonts?.ready.then(scheduleMeasure);
