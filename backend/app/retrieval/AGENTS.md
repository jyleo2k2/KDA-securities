# 연금 코파일럿 RAG 세션 진입점

> 적용 범위: `backend/app/retrieval/` 하위 + `backend/app/chat/knowledge.py` + 임베딩·지식 적재 스크립트.
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-19

## 임무

검증된 공식 문서의 적재 → BGE-M3 임베딩 → pgvector 검색 → 챗봇 지식 공급 품질을 책임진다. RAG에는 검증된 공식 문서만 들어간다 — **개인 계좌·성향·대화 데이터 반입 절대 금지**.

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- `git fetch origin main` 후 뒤처졌으면 리베이스한다(트리가 더티면 소유자 확인 → 본인 것만 커밋/스태시).
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다.
- 작업은 `rag/` 접두사 브랜치에서 하고 PR로 낸다. `main` 직접 push 금지.

## 소유·금지 경계

| 구분 | 경로 |
|---|---|
| 소유(수정 가능) | `backend/app/retrieval/**`, `backend/app/chat/knowledge.py`, `backend/app/ingestion/embeddings.py`, `scripts/embed_knowledge_chunks.py`, `scripts/ingest_knowledge.py`, `tests/test_knowledge_ingestion.py`, `tests/test_embeddings.py`, `tests/test_news_retrieval.py`, `tests/test_search_quality.py`, `tests/test_search_ranking.py` |
| 챗봇 세션 소유(읽기만) | `backend/app/chat/**`(knowledge.py 제외), `backend/app/api/chat.py` |
| DB 세션 소유(읽기만) | `supabase/**`, `backend/app/database.py`, `backend/app/chat/repository.py` — pgvector 스키마·마이그레이션 변경은 DB 세션과 계약 절차로 |
| 공유 파일(최소 diff + PR 명시) | `backend/app/api/deps.py`, `backend/app/settings.py`, `backend/app/main.py`, `.env.example` |

## 세션 간 계약 (변경 시 PR에 `계약 변경` 표시 + 상대 세션·이재용 합의)

- **챗봇과**: `KnowledgeRepository` 검색 인터페이스, 청크·출처(source chip) 스키마, 검색 결과 랭킹 계약.
- **DB와**: `knowledge_*` 테이블·pgvector 인덱스·임베딩 차원(BGE-M3 1024) — 스키마 변경은 DB 세션이 마이그레이션 작성.
- 임베딩 모델·차원 변경은 원격 재적재를 수반하므로 이재용 승인 필수.

## 검증 명령

```powershell
uv run pytest tests/test_knowledge_ingestion.py tests/test_embeddings.py tests/test_news_retrieval.py tests/test_search_quality.py tests/test_search_ranking.py   # 빠른 루프
uv run pytest        # 세션 종료 전 전체 1회
uv run ruff check .
uv run python scripts/measure_search_quality.py   # 검색 품질 회귀 확인(변경이 검색 결과에 닿을 때)
```

임베딩 그룹 설치: `uv sync --group embeddings`.

## 핸드오프

- PR 본문에: 변경 요약 / 계약 변경 여부 / 실행한 테스트·품질 측정 결과 / 금지 경로 미수정 확인.
- 원격 적재·스키마 적용 상태는 추측으로 기록하지 않는다. 조회로 확인한 것만 기록한다.
