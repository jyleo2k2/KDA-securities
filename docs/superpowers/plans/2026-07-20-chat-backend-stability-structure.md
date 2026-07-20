# Chat Backend Stability and Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SSE 저장 실패를 오류 이벤트로 전달하고, 내레이션 가드와 인텐트 핸들러를 행동 변경 없이 책임별 모듈로 분리한다.

**Architecture:** `ChatService.ask()`는 라우팅과 결과 조립만 담당하고 `handlers/`의 인텐트별 함수에 실제 의존성을 전달한다. 내레이션 검증은 `narration_guard.py`로 이동하되 기존 `narrator.py` import 호환성을 유지한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, uv.

## Global Constraints

- Python 실행은 `uv run python`, 테스트는 `uv run pytest`만 사용한다.
- `backend/app/chat/repository.py`, `user_context.py`, `backend/app/retrieval/**`, `supabase/**`, 루트 `CLAUDE.md`/`AGENTS.md`는 수정하지 않는다.
- 각 코드 커밋 직전에 `uv run pytest` 전체를 실행하고 909개 기준 테스트 개수를 유지한다.
- `narration_guard.py` 이동은 정규식·조건문·주석을 변경하지 않는다.
- Task 2·3의 조사 결과는 PR 본문 초안에 기록하며 파일 변경이 없으면 빈 커밋을 만들지 않는다.

---

### Task 1: Stream RuntimeError delivery

**Files:**
- Modify: `backend/app/api/chat.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**
- Consumes: `ChatRepository.find_idempotent_exchange`, `ChatRepository.save_exchange`가 던지는 `RuntimeError`.
- Produces: 헤더 전송 후에도 `event: error`와 기존 오류 payload를 보내는 SSE 스트림.

- [ ] 스트림 저장소가 `RuntimeError`를 던지는 테스트를 작성한다.
- [ ] `uv run pytest tests/test_chat_api.py -k runtime_error -v`로 error 이벤트가 없어 실패하는지 확인한다.
- [ ] `_stream_answer`와 인증 `events()`의 DB 호출 except에만 `RuntimeError`를 추가하고 `logger.exception`을 유지한다.
- [ ] 대상 테스트와 전체 `uv run pytest`를 실행한다.
- [ ] `fix(chat): emit SSE errors for invalid stored responses`로 커밋한다.

### Task 2: Narrator guard findings audit

**Files:**
- Inspect: `backend/app/chat/narrator.py`, `tests/test_chat_mvp.py`
- Conditional test change: `tests/test_chat_mvp.py`

**Interfaces:**
- Consumes: `4d542ad`, `b3375b8`, `7baeaf8`의 diff와 회귀 테스트.
- Produces: 원 결함별 해소 여부 표와 루트 문서 수정 제안 문구.

- [ ] 세 커밋의 diff와 당시 추가 테스트를 원 결함에 매핑한다.
- [ ] 현재 코드에 남은 우회만 최소 재현 테스트로 확인한다.
- [ ] 미해소 우회가 있으면 이유를 명시한 `xfail` 테스트만 추가하고 전체 테스트 후 커밋한다.
- [ ] 미해소가 없으면 코드·빈 커밋 없이 PR 본문 초안에 결과를 기록한다.

### Task 3: New module duplication audit

**Files:**
- Inspect only: 지정된 신규 모듈, `backend/app/chat/service.py`, `backend/app/chat/user_context.py`, `backend/app/chat/routing.py`

**Interfaces:**
- Produces: 계좌/성향, 목데이터, 뉴스, 카드/후속질문별 파일:라인·중복 요약·blame 위험도 표.

- [ ] 호출 그래프와 동일 데이터 접근 경로를 검색한다.
- [ ] 겹침 후보 각 줄의 `git blame`과 도입 커밋을 확인한다.
- [ ] 서로 다른 입력·출력·실/목 경계 때문에 의도적으로 분리된 후보를 배제한다.
- [ ] 코드와 빈 커밋 없이 PR 본문 초안에 기록한다.

### Task 4: Narration guard extraction

**Files:**
- Create: `backend/app/chat/narration_guard.py`
- Modify: `backend/app/chat/narrator.py`
- Modify: `backend/app/chat/CLAUDE.md`
- Modify: `backend/app/chat/AGENTS.md`

**Interfaces:**
- Produces: 기존 가드 함수·상수를 같은 이름으로 제공하는 `narration_guard.py`.
- Compatibility: `narrator.py`는 기존 외부·테스트 import를 재노출한다.

- [ ] 가드 블록과 필수 내부 의존 심볼을 원문 그대로 이동한다.
- [ ] `narrator.py`에서 가드 함수를 import해 기존 호출과 import 경로를 유지한다.
- [ ] 두 세션 진입점의 핫존 파일명만 동기 변경한다.
- [ ] `git diff --color-moved`와 기존 내레이터 테스트로 이동만인지 확인한다.
- [ ] 전체 `uv run pytest` 후 `refactor(chat): extract narration guard module`로 커밋한다.

### Task 5: Intent handler extraction

**Files:**
- Create: `backend/app/chat/handlers/__init__.py`, `handlers/_shared.py`, `handlers/account_rules.py`, `handlers/portfolio.py`, `handlers/pension_tax.py`, `handlers/disclosures_news.py`, 필요 시 `handlers/capabilities.py`
- Modify: `backend/app/chat/service.py`, `backend/app/api/chat.py`
- Test: existing `tests/test_chat_*.py`, `tests/test_pension_tax_chat.py`, `tests/test_query_planner.py`

**Interfaces:**
- Consumes: `ChatIntent`과 `ChatService.__init__`에 저장된 실제 repository/engine callable.
- Produces: `ChatRequest`/`QueryPlan`과 명시적 의존성을 받는 인텐트별 함수. 네트워크 응답 계약은 변경하지 않는다.

- [ ] 공유 순수 헬퍼를 `_shared.py`로 이동하고 기존 테스트 import 호환성을 유지한다.
- [ ] 카드/후속질문과 계좌 안내처럼 독립적인 그룹부터 이동한다.
- [ ] 포트폴리오, 세금, 공시·뉴스 그룹을 차례로 이동한다.
- [ ] 각 그룹은 `self` 대신 실제 repository/callable/요청 값만 keyword 인자로 받는다.
- [ ] 각 그룹 이동 후 빠른 챗 테스트와 전체 `uv run pytest`를 실행한 다음 독립 커밋한다.
- [ ] 최종 `service.py`에는 생성자·계획·질문 위임 중심의 오케스트레이션만 남긴다.

### Final verification and PR handoff

- [ ] `uv run pytest`에서 기준 테스트 개수와 실패 0을 확인한다.
- [ ] `uv run ruff check .`를 실행한다.
- [ ] 금지 경로·루트 진입점 미수정과 Task별 커밋 경계를 확인한다.
- [ ] PR 본문에 Task 2·3 표, 문서 제안, 이동 체크리스트, diff stat, 계약 변경 여부를 기록한다.

---

## Task 2 감사 결과 (2026-07-20)

| 원래 결함군 | 재현/회귀 케이스 | 근거 커밋 | 판정 |
|---|---|---|---|
| 부정어 창 우회 | H1 `보장되지 않는 게 아니라 보장됩니다` | `b3375b8` | 해소: 이중부정 꼬리를 양성 주장으로 처리 |
| 직접 권유·보장 어휘 우회 | H2 `담으시면 돼요`, `원금이 줄지 않아요` | `b3375b8` | 해소: 권유·원금 비감소 패턴 차단 |
| 수식어가 낀 확정 표현 | H3 `사실상 확정` | `b3375b8` | 해소: 위험 주장 창을 40자로 확장 |
| 부정문·수치·날짜 표기 오탐 | H4~H7 부정 수식, 15%, 900만 원, 날짜 표기 | `7baeaf8` | 해소: 부정문·한글 수치·점 날짜 정규화 |

`uv run pytest tests/test_chat_mvp.py`: 121 passed. 현재 재현 가능한 미해소 우회가 없어 `xfail`은 추가하지 않았다.

### 문서에 반영할 내용

루트 `CLAUDE.md`와 `AGENTS.md`의 “가드 잔여 결함 … Codex 보강 작업 대기” 문구는 다음으로 교체 제안한다.

> 내레이터 가드 잔여 결함은 2026-07-20 적대적 회귀 코퍼스(H1~H7)로 보강 완료했다. 이중부정·직접 권유·원금 비감소·수식어가 낀 확정 표현은 차단하고, 동치 한글 수치·점 날짜·부정문은 허용한다. 새 표현은 재현 케이스가 확인될 때만 확장한다.

## Task 3 중복 감사

| 영역 | 확인 경로 | 판정 | blame 근거 |
|---|---|---|---|
| 사용자 계좌·성향 | `user_context.py:232` DB 인증 컨텍스트, `demo_customer_records.py:148` CSV 벤치마크 레코드, `service.py:898` 요청 소비 | 중복 아님: 인증 사용자·데모 생성·응답 조립의 데이터 경계가 다름 | `d44b0c01`, 기존 DB 세션 소유 |
| 계좌 안내 | `pension_account_overview.py:47,389`, `service.py:2356` | 중복 후보(낮음): 둘 다 제도 안내이나 전자는 고정 카드, 후자는 RAG/질의별 응답 | `ce46a8f0` 대 `17077f04` |
| 뉴스 선택·표시 | `live_news.py:55`, `service.py:3576,3974`, `routing.py:64` | 중복 아님: 실시간 수집·저장뉴스 표시·후속질문 해석을 분리 | `0199b2c4`, `db884300` |
| 카드·후속질문 | `cards.py:77`, `service.py:3700,3974`, `routing.py:64` | 중복 아님: 카드는 다음 질문 UI, service는 컨텍스트 생성, router는 입력 해석 | `99e7aa31`, `db884300` |
| 거시 레짐 | `engine/macro_regime.py:113`, `engine/macro_regime_outcomes.py:213` | 중복 아님: 유사 레짐 탐색과 사후 ETF 성과 산출의 순수 엔진 분리 | 엔진 모듈 경계 |

조치: 코드 변경 없음. 유일한 낮은 위험 후보는 Task 5 분리 시에도 고정 계좌 안내와 RAG 질의 응답을 합치지 않고 입력·근거 계약을 유지한다.
