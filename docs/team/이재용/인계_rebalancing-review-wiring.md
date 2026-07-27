# 인계 — 챗봇 리밸런싱 점검 기능 연결 (codex/이재용/rebalancing-review-wiring)

> 작성 2026-07-27 · 기준 `origin/main` `62119d1` · 상태: **조사 완료 / 구현 미착수**
> 요청은 "어떻게 기능 붙일지 보고"였고 이 문서가 그 보고서다. 코드는 수정하지 않았다.

## 1. 증상

챗봇 웰컴 화면의 `리밸런싱 3개월 점검` 카드에서 **"챗봇에 점검 요청"** 버튼을 누르면 아래 문구만 뜨고 아무 일도 일어나지 않는다.

> 계좌 보유내역을 불러오지 못해 실제 비중 점검을 시작하지 못했어요. 잠시 후 다시 요청해 주세요.

## 2. 결론 먼저

**결함은 두 개이고 서로 독립이다. 하나만 고치면 기능은 여전히 동작하지 않는다.**

| # | 결함 | 계층 | 증상 |
|---|---|---|---|
| A | 카드 노출 조건과 점검 실행 조건이 서로 다른 데이터를 본다 | 백엔드+프론트 | 계좌가 없는 사용자에게도 버튼이 보이고, 누르면 404 → 위 오류 문구 |
| B | 토픽 가드가 첨부된 보유내역을 무시하고 용어 설명으로 재라우팅한다 | 백엔드 | 계좌가 정상인 사용자도 리밸런싱 결과 대신 "ETF는 …" 답변을 받는다 |

계정에 따라 A에서 막히거나, A를 통과해도 B에서 엉뚱한 답을 받는다. 둘 다 실측으로 재현했다.

## 3. 결함 A — 카드 노출 조건과 점검 조건의 불일치

### 실행 경로

`requestActualRebalancingReview()`(`frontend/src/pages/GuidePage.tsx:1114`)가 두 API를 동시에 호출한다.

- `GET /chat/rebalancing-profile` — 저장된 투자성향 + 연금 컨텍스트
- `GET /me/pension-accounts` — 계좌 보유내역

### 어긋난 지점

카드를 띄우는 `GET /me/rebalancing-reminder`는 `investment_profile_assessments` **한 테이블만** 본다
(`backend/app/rebalancing_reminder_repository.py` `get_state`).
반면 `GET /chat/rebalancing-profile`은 `demo_user_financial_context`까지 필요로 하고 없으면 404를 던진다
(`backend/app/api/chat.py:451`~`495`).

즉 **투자성향 설문만 마치면 버튼이 보이지만, 연금 컨텍스트·계좌가 없으면 눌러도 404**다.

### 실측 재현 (원격 Supabase, FastAPI TestClient)

| 계정 | 카드 | `/chat/rebalancing-profile` | `/me/pension-accounts` |
|---|---|---|---|
| `junho46` 박준호 | 표시 | 200 (dc) | 200 `[dc]` |
| `jihoon47` 최지훈 | 표시 | 200 (irp) | 200 `[dc, irp, pension_savings]` |
| `minjae32` 정민재 | 표시 | 200 (irp) | 200 `[dc, irp, pension_savings]` |
| `seoyeon34` 이서연 | 표시 | 200 (irp) | 200 `[irp, pension_savings]` |
| `harin29` 김하린 | 표시 | 200 (dc) | 200 `[dc, pension_savings]` |
| **`jeongsu33`** | **표시** | **404 RESOURCE_NOT_FOUND** | **200 `[]` (계좌 0건)** |

`jeongsu33@kda-demo.invalid`(`81294832-0880-45c9-8b9e-6ae4de58ac42`)는 `demo_user_financial_context`에 행이 없고
`pension_accounts`도 0건인데, `investment_profile_assessments` 4건과 리마인더 `enabled=true`라서 카드만 떠 있다.
이 계정의 마지막 로그인은 2026-07-27 00:31 UTC로 **사용자가 증상을 본 시점과 일치**한다.

### 왜 항상 저 문구인가

404는 `ApiError` 예외로 던져지므로 `review.status` 분기(`account_not_found`·`holdings_not_available`)에 도달하지 못하고
`catch` 블록으로 직행한다. 그래서 원인이 무엇이든 늘 같은 "불러오지 못해" 문구가 나온다.
**404(성향·컨텍스트 없음)·503(DB 장애)·401(세션 만료)이 한 문구로 뭉개지는 것 자체가 별도의 UX 결함**이다.

## 4. 결함 B — 토픽 가드가 첨부된 보유내역을 가로챈다

A를 통과한 정상 계정(`minjae32`, IRP 7종목)으로 실제 `/chat/stream`을 호출한 결과다.

요청은 `{"message": "리밸런싱 점검해줘", "educational_portfolio": {보유 7종목}}`인데 응답은 이랬다.

- `intent`: `glossary`
- `answer`: "ETF는 지수를 따라가도록 만든 펀드를 주식처럼 사고파는 상품이에요. …"

**첨부한 보유내역이 통째로 버려지고 ETF 용어 설명이 돌아온다.**

### 원인 사슬

1. `plan_question("리밸런싱 점검해줘")` → `out_of_scope` / `blocked_reason=unsupported`. 결정론 라우터에 이 문장 패턴이 없다.
2. `backend/app/api/chat.py:650`에서 `blocked_reason is UNSUPPORTED`이므로 `topic_guard.refine_plan()`을 호출한다.
3. `backend/app/chat/topic_guard.py`의 `refine_plan`이 LLM 분류 결과로 **plan을 GLOSSARY로 교체**한다.
4. `backend/app/chat/service.py`의 `ask()` 분기 순서가 `GLOSSARY`(278행) → `request.educational_portfolio is not None`(286행)이라
   **GLOSSARY가 먼저 걸려 보유내역 분기에 도달하지 못한다.**

### 격리 검증

`ENABLE_CLAUDE_TOPIC_GUARD=false`로 같은 요청을 보내면 정상 동작한다.

- `intent`: `educational_portfolio`
- `sections`: 위험자산비중과 핵심요약 / 목표 자산배분 / 계획 가정에 따른 수익률 범위 / ETF 후보 살펴보기

엔진은 이미 완성돼 있다. **라우팅이 엔진에 도달하지 못하는 것이 전부다.**

## 5. 제안 설계

### B-1. 첨부 우선 분기 (필수, 최소 변경)

`educational_portfolio` 첨부는 사용자가 UI 버튼으로 명시한 의도이므로 문장 분류보다 우선해야 한다.
`service.py`의 `ask()`에서 `request.educational_portfolio is not None` 분기를
`GLOSSARY`·`INVESTING_PRINCIPLE`·`HESITATION_SUPPORT`보다 **위로** 올린다.
`request.portfolio`가 이미 최상단에 있는 것과 같은 원칙이다.

변경 규모는 분기 블록 1개 이동이다. 첨부가 있는데 진짜 용어를 묻는 경우가 밀리지만, 첨부는 UI 버튼으로만 생성되므로 실사용 충돌은 없다.

더 좁은 대안으로 `chat.py:650`에서 `educational_portfolio`가 있으면 `refine_plan`을 건너뛰는 방법도 있다.
가드 호출을 아끼지만 스트림 경로에만 적용되고 `service.ask()`를 직접 쓰는 경로가 남는다. **B-1을 권장한다.**

### B-2. "리밸런싱 점검해줘"를 결정론 라우터에 등록 (권장)

`plan_question`에 리밸런싱 점검 패턴을 추가해 `EDUCATIONAL_PORTFOLIO`로 직행시킨다.
B-1만으로 버튼은 살아나지만 사용자가 같은 말을 **직접 타이핑**하면 여전히 out_of_scope로 빠진다.
LLM 가드에 의존하지 않는 결정론 경로를 두는 편이 "엔진이 판단, LLM은 서술" 원칙에도 맞다.

### A-1. 카드 노출 조건을 실행 가능 조건과 일치시키기 (필수)

`RebalancingReminderState`에 실제 점검 가능 여부를 담고 프론트가 그 값으로 버튼을 렌더한다.
`get_state` 쿼리에 연금 컨텍스트·계좌 스냅샷 존재 여부를 더해 `review_available`(가칭)을 내려주는 방식이다.
불가하면 버튼을 숨기거나 비활성화하고 계좌 연동으로 유도한다.
이렇게 하면 **누를 수 있는 버튼은 반드시 동작한다**는 성질이 생긴다.

### A-2. 오류 문구 분기 세분화 (권장)

`catch`에서 `ApiError`의 `status`·`code`를 구분한다. 세 갈래면 충분하다.

| 조건 | 문구 방향 |
|---|---|
| 404 `RESOURCE_NOT_FOUND` | 투자성향 또는 연동 계좌가 필요하다고 안내하고 해당 화면으로 유도 |
| 503 `DATA_SOURCE_UNAVAILABLE` | 일시적 장애이므로 잠시 후 재시도 안내 |
| 401 | 로그인 만료 안내 |

기존 `apiErrorMessage()`가 이미 코드별 문구를 갖고 있으므로 재사용할 수 있다.

### 우선순위

1. **B-1** — 이것만으로 정상 계정의 버튼이 즉시 살아난다. 가장 작고 효과가 크다.
2. **A-1** — 계좌 없는 계정에서 헛도는 버튼을 없앤다.
3. **B-2**·**A-2** — 타이핑 경로와 오류 안내 품질.

## 6. 검증 계획

- `tests/test_chat_api.py`: 첨부 + 토픽 가드 활성 상태에서 `intent == educational_portfolio` 단언 (B-1 회귀 방지)
- `tests/test_query_planner.py`: `"리밸런싱 점검해줘"` → `EDUCATIONAL_PORTFOLIO` (B-2)
- `tests/test_rebalancing_reminder_repository.py`: 성향은 있고 계좌가 없는 소유자에게 `review_available=false` (A-1)
- `frontend/src/pages/GuidePage.rebalancing.test.tsx`: 404 시 성향·계좌 안내, 503 시 재시도 문구 (A-2)
- 기준선: 백엔드 `1505 passed, 1 skipped`

## 7. 확인만 하고 손대지 않은 것

- 계좌마다 `etf_isu_code`가 없는 보유종목이 1~2건씩 있다(예금·현금성). 프론트가 `snapshot:<holding_id>` 대체 키를 만들어 넘기고
  엔진도 이를 받아 처리하므로 **현재 결함은 아니다.**
- 엔진 실행 중 `Historical ETF outcome evidence unavailable` 경고가 나오지만 응답 생성은 정상 완료된다. 별건이다.
- 저장소 전역 CI가 2026-07-26 09:56:44부터 러너 미배정으로 실패 중이라는 기록이 있다(PR #379 코멘트). 이 작업과 무관하다.
