# 연금 코파일럿 챗봇 세션 진입점

> 적용 범위: `backend/app/chat/` 하위 + `backend/app/api/chat.py`(챗봇 엔드포인트).
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-19

## 임무

질의 계획(query_planner) → 규칙 엔진 응답(service) → Claude 내레이션(narrator) → SSE 스트림(api/chat.py) 파이프라인의 정확성·안전 가드·응답 성능을 책임진다. LLM은 서술만 하고 수치 계산은 절대 하지 않는다(Explainable by Design).

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- `git fetch origin main` 후 뒤처졌으면 리베이스한다(트리가 더티면 소유자 확인 → 본인 것만 커밋/스태시).
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다.
- 작업은 `chat/` 접두사 브랜치에서 하고 PR로 낸다. `main` 직접 push 금지.

## 소유·금지 경계

| 구분 | 경로 |
|---|---|
| 소유(수정 가능) | `backend/app/chat/**` (아래 예외 제외), `backend/app/api/chat.py`, `tests/test_chat_*.py`, `tests/test_pension_tax_chat.py`, `tests/test_query_planner.py` |
| DB 세션 소유(읽기만) | `backend/app/chat/repository.py`, `backend/app/chat/user_context.py`, `backend/app/database.py`, `supabase/**` |
| RAG 세션 소유(읽기만) | `backend/app/chat/knowledge.py`, `backend/app/retrieval/**` |
| 엔진 담당 합의 필요 | `backend/app/engine/**` (오너: 김태형) |
| 공유 파일(최소 diff + PR 명시) | `backend/app/api/deps.py`, `backend/app/settings.py`, `backend/app/main.py`, `backend/app/chat/models.py`, `.env.example` |

## 핫존 (별도 승인 없이 수정 금지)

- `narrator.py`의 검증 가드: `_number_tokens`, `_korean_number_tokens`, `_unsafe_claim_instances`, `_adds_unverified_content`, `_NEGATION` 및 관련 정규식 — 가드 보강 전용 태스크에서만 수정한다.
- 내레이터 프리워밍: 반드시 버리는(throwaway) Agent로 호출한다. `self.agent`를 부팅 스레드 이벤트루프에서 `run_sync`하면 이후 요청이 무한 행에 빠진다(실측 재현). 회귀 테스트 `test_narrator_prewarm_uses_throwaway_agent`를 절대 깨지 않는다.
- 성능 구성 고정(2026-07-18 실측): Haiku + thinking OFF(Haiku는 adaptive 미지원, enabled는 오히려 느림), 결정론 내레이션 LRU 캐시, 서버측 프롬프트 캐싱.

## 세션 간 계약 (변경 시 PR에 `계약 변경` 표시 + 상대 세션·이재용 합의)

- **프론트와**: SSE 이벤트(`phase`/`answer_delta`/`response`/`error`), `ChatResponse` 스키마(`models.py`) ↔ `frontend/src/api/types.ts`.
- **DB와**: 대화 저장 포맷(`schema_version=1` JSON), `ChatRepository`·`DemoUserContextRepository` 인터페이스.
- **RAG와**: `KnowledgeRepository` 검색 인터페이스와 청크·출처 스키마.

## 검증 명령

```powershell
uv run pytest tests/test_chat_api.py tests/test_chat_mvp.py tests/test_chat_tools.py tests/test_chat_routing_and_privacy.py tests/test_chat_educational_portfolio.py tests/test_chat_scenarios_repository.py tests/test_pension_tax_chat.py tests/test_query_planner.py   # 빠른 루프
uv run pytest        # 세션 종료 전 전체 1회
uv run ruff check .
```

챗봇 동작 검증 절차는 [docs/30_스펙/챗봇_테스트_가이드.md](../../../docs/30_스펙/챗봇_테스트_가이드.md).

## 핸드오프

- PR 본문에: 변경 요약 / 계약 변경 여부 / 실행한 테스트와 결과 / 금지 경로 미수정 확인.
- 성능 수치는 실측만 기록한다. 추정치는 추정임을 명시한다.
