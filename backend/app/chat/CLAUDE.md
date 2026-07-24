# 연금 코파일럿 챗봇 세션 진입점

> 적용 범위: `backend/app/chat/` 하위 + `backend/app/api/chat.py`(챗봇 엔드포인트).
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-24

## 임무

질의 계획(query_planner) → 서비스 오케스트레이션(service) → 인텐트 핸들러·표시 조립(handlers/) → Claude 내레이션(narrator) → SSE 스트림(api/chat.py) 파이프라인의 정확성·안전 가드·응답 성능을 책임진다. LLM은 서술만 하고 수치 계산은 절대 하지 않는다(Explainable by Design).

## 사용자 노출 문구 정책

- API `message`·`detail`, 결정론 답변, SSE 텍스트, 카드 제목·설명, 후속 질문, Claude 내레이션에 `교육용`, `목데이터`·`목 데이터`, `Mock`·`mock`, `가상`을 사용하지 않는다.
- `샘플 데이터`, `테스트용`, `데모용`, `시연용`처럼 같은 의미의 내부 구현 표식으로 바꾸는 것도 금지한다. 고객·계좌·포트폴리오·투자 사례를 서비스 문맥 그대로 설명한다.
- 내부 클래스명·fixture·시나리오 코드·DB 테이블명은 호환성을 위해 유지할 수 있지만, 이를 응답 조립이나 LLM 프롬프트를 통해 사용자에게 노출하지 않는다.
- 사용자 응답 문구를 수정하면 완료 전에 변경한 응답 경로에서 금지 표현을 검색하고, 결정론 응답과 내레이션 교체 경로 모두에 회귀 테스트를 추가하거나 기존 단언을 확인한다.

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- 파일 수정 전에 `git-session-manager`로 담당자와 예상 수정 경로를 claim한다. 루트 `main` 관제 워크트리에서는 수정하지 않는다.
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다.
- 작업은 최신 `origin/main`에서 만든 `chat/<owner>/<task>` 브랜치·전용 워크트리에서 하고 첫 커밋 후 Draft PR을 연다. 병합 브랜치 재사용과 `main` 직접 push는 금지한다.
- `models.py`·`service.py`·`query_planner.py`·`backend/app/api/deps.py`는 공유 핫스팟이다. 다른 active claim/PR과 겹치면 이재용이 단일 작성자를 지정하기 전까지 수정하지 않는다.

## 소유·금지 경계

| 구분 | 경로 |
|---|---|
| 소유(수정 가능) | `backend/app/chat/**` (아래 예외 제외), `backend/app/api/chat.py`, `tests/test_chat_*.py`, `tests/test_pension_tax_chat.py`, `tests/test_query_planner.py` |
| DB 세션 소유(읽기만) | `backend/app/chat/repository.py`, `backend/app/chat/user_context.py`, `backend/app/database.py`, `supabase/**` |
| RAG 세션 소유(읽기만) | `backend/app/chat/knowledge.py`, `backend/app/retrieval/**` |
| 엔진 담당 합의 필요 | `backend/app/engine/**` (오너: 김태형) |
| 공유 파일(최소 diff + PR 명시) | `backend/app/api/deps.py`, `backend/app/settings.py`, `backend/app/main.py`, `backend/app/chat/models.py`, `.env.example` |

## 핫존 (별도 승인 없이 수정 금지)

- `narration_guard.py`의 검증 가드: `_number_tokens`, `_korean_number_tokens`, `_unsafe_claim_instances`, `_adds_unverified_content`, `_NEGATION` 및 관련 정규식 — 가드 보강 전용 태스크에서만 수정한다.
- 내레이터 프리워밍: 반드시 버리는(throwaway) Agent로 호출한다. `self.agent`를 부팅 스레드 이벤트루프에서 `run_sync`하면 이후 요청이 무한 행에 빠진다(실측 재현). 회귀 테스트 `test_narrator_prewarm_uses_throwaway_agent`를 절대 깨지 않는다.
- 성능 구성 고정(2026-07-18 실측): Haiku + thinking OFF(Haiku는 adaptive 미지원, enabled는 오히려 느림), 결정론 내레이션 LRU 캐시, 서버측 프롬프트 캐싱.

## 세션 간 계약 (변경 시 PR에 `계약 변경` 표시 + 상대 세션·이재용 합의)

- **프론트와**: SSE 이벤트(`phase`/`answer_delta`/`narration_update`/`response`/`error`), `ChatResponse` 스키마(`models.py`) ↔ `frontend/src/api/types.ts`. `answer_delta`는 결정론 답변 선전송, `narration_update`는 가드 통과 내레이션의 전문 교체다.
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

## 임시물 / 제거 대상 (디버깅 끝나면 삭제)

아래는 개발 디버깅용으로 넣은 한시적 코드다. 목적을 다하면 제거한다. 새 임시물을 추가하면 이 목록에 같이 적는다.

- **챗 디버그 JSONL 로거** (PR #202, 2026-07-23 추가): 챗 폴백·내레이션·지연을 파일로 관찰하기 위한 개발자 도구. 마이데이터 실계좌 연동 시 흐를 질문·답변 데이터를 개발 중에 디버깅하는 용도다.
  - 파일: `backend/app/chat/_debug_log.py`(로거 본체), `scripts/chat_debug_viewer.html`(뷰어).
  - 삽입 지점: `backend/app/api/chat.py`의 `_debug_log` import 1줄 + `log_chat_exchange(...)` 호출 2곳(out_of_scope 비저장 경로, 일반 저장 경로).
  - 켜기: 루트 `.env`에 `CHAT_DEBUG_LOG=1`. 기본 OFF라 미설정 시 아무 파일도 만들지 않는다. 출력은 `data/cache/chat_debug.jsonl`(gitignore).
  - **제거 방법**: 위 두 파일을 삭제하고 `api/chat.py`의 삽입 4줄(import 1 + 호출 2곳 블록)을 제거한다. `data/cache/chat_debug.jsonl`도 지운다. 기존 로직은 순수 추가라 그 4줄만 빼면 원상복구된다.
  - **제거 시점**: 폴백 디버깅이 끝났거나, 실계좌 연동 단계에서 개인정보 보존기간·마스킹 정책을 갖춘 정식 로깅으로 대체할 때.
