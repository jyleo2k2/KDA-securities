# RAG Corpus Management Implementation Plan

> 상태: 구현·원격 반영·PR 병합 완료(2026-07-18, PR #56). 승인 문서 10개·활성 청크 41개·검색 품질 18/18·CI 통과를 확인했다. 세션 전용 기록이 남아 있어 전용 worktree 정리만 보류한다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 연금 지식 문서를 사람 검토와 자동 만료 차단으로 관리하고, 공식 문서 5종을 추가해 로컬·원격 RAG 검색에 반영한다.

**Architecture:** 도메인 Markdown은 기존 허용 루트에 유지하고 JSON 매니페스트 v2를 단일 승인 장부로 사용한다. 로더는 출처·기한·무결성·오염을 fail-closed로 검증하고 운영 메타데이터를 모든 청크에 전파한다. GitHub CI와 검색 품질 벤치마크가 변경을 차단하며 승인 후 Supabase에 증분 적재·임베딩한다.

**Tech Stack:** Python 3.13, FastAPI 프로젝트 모듈, JSON, Markdown, pytest, GitHub Actions, Supabase PostgreSQL/pgvector, BGE-M3

## Global Constraints

- 공식기관 원문에 없는 금융·세제·수익률 사실을 만들지 않는다.
- Python은 `uv run python`, 테스트는 `uv run pytest`를 사용한다.
- 한국어 Markdown과 JSON은 UTF-8 패치로만 편집한다.
- 원래 작업트리 WIP는 건드리지 않고 `C:\dev\kda-rag-corpus`에서만 작업한다.
- 규제·세제 문서는 90일, 리서치 문서는 180일 이내에 사람이 재검토한다.
- 검토기한이 지나면 로더와 CI가 적재를 차단한다.

---

### Task 1: 매니페스트 v2 거버넌스 계약

**Files:**
- Modify: `tests/test_knowledge_ingestion.py`
- Modify: `backend/app/retrieval/knowledge_policy.py`
- Modify: `backend/app/ingestion/knowledge.py`
- Modify: `data/knowledge/approved_documents.json`

**Interfaces:**
- Produces: `load_approved_documents(..., today: date | None = None)` and chunk metadata containing governance fields.

- [x] **Step 1: Write failing tests** for schema v2 required fields, official HTTPS host allowlist, 90/180-day review windows, expired document rejection, hidden control characters, prompt-injection markers, and governance metadata propagation.
- [x] **Step 2: Run RED** with `uv run pytest tests/test_knowledge_ingestion.py -q`; expect failures because schema v1 accepts no governance fields.
- [x] **Step 3: Implement minimal v2 validation** with deterministic Python/date/regex helpers and no new dependency.
- [x] **Step 4: Upgrade the existing five manifest entries** with stable IDs, official sources, topics, question families, verification dates, due dates, owner, and chunking version.
- [x] **Step 5: Run GREEN** with `uv run pytest tests/test_knowledge_ingestion.py -q`.
- [x] **Step 6: Commit** as `feat(rag): enforce corpus provenance and review lifecycle`.

### Task 2: 운영 감사와 문서화

**Files:**
- Create: `data/knowledge/README.md`
- Modify: `scripts/ingest_knowledge.py`
- Modify: `tests/test_knowledge_ingestion.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: v2 loader from Task 1.
- Produces: `--validate-only` output with document/chunk count and nearest review deadline.

- [x] **Step 1: Write a failing CLI test** asserting the audit output includes the nearest `review_due_date` and document ID.
- [x] **Step 2: Run RED** for that test and confirm the missing audit detail.
- [x] **Step 3: Add audit output and README workflow** covering candidate, approval, update, expiry, retirement, remote sync, and rollback.
- [x] **Step 4: Add a CI step** running `uv run python scripts/ingest_knowledge.py --validate-only` before tests.
- [x] **Step 5: Run GREEN** for ingestion tests and Ruff on changed Python files.
- [x] **Step 6: Commit** as `docs(rag): document and automate corpus review workflow`.

### Task 3: 공식 지식 문서 5종과 매니페스트 등록

**Files:**
- Create: `docs/20_리서치/ETF_비교지표_읽기.md`
- Create: `docs/20_리서치/퇴직연금_2025_운용현황.md`
- Create: `docs/40_규제/연금수령_과세.md`
- Create: `docs/40_규제/퇴직연금_실물이전.md`
- Create: `docs/40_규제/연금계좌_예금자보호.md`
- Modify: `data/knowledge/approved_documents.json`
- Modify: `tests/test_knowledge_ingestion.py`

**Interfaces:**
- Produces: ten approved documents that pass v2 governance and SHA validation.

- [x] **Step 1: Write a failing test** expecting ten documents and the five stable document IDs.
- [x] **Step 2: Run RED** and confirm only five documents load.
- [x] **Step 3: Write five concise documents** from KRX, MOEL, NTS, and FSC official pages with explicit scope, basis date, limitations, and source links.
- [x] **Step 4: Compute stripped UTF-8 SHA-256** using `uv run python` and register five entries.
- [x] **Step 5: Run GREEN** for ingestion tests and `uv run python scripts/ingest_knowledge.py --validate-only`.
- [x] **Step 6: Commit** as `docs(rag): add five official pension knowledge guides`.

### Task 4: 문서별 검색 품질 게이트

**Files:**
- Modify: `data/search_quality/knowledge_v1.json`
- Modify: `tests/test_search_quality.py`

**Interfaces:**
- Consumes: ten approved source URLs.
- Produces: at least one deterministic retrieval case per approved document.

- [x] **Step 1: Write a failing coverage test** asserting every approved source URL appears in the benchmark.
- [x] **Step 2: Run RED** and confirm the five new URLs are uncovered.
- [x] **Step 3: Add five Korean representative queries** with required content terms and critical top-1 only where ambiguity is low.
- [x] **Step 4: Tune headings/phrasing, not ranking code**, until local Markdown retrieval reaches Hit@5=1, Hit@1=1, MRR@5=1.
- [x] **Step 5: Run GREEN** with `uv run pytest tests/test_search_quality.py -q`.
- [x] **Step 6: Commit** as `test(rag): cover every approved knowledge document`.

### Task 5: 로컬 최종 검증과 원격 반영

**Files:**
- Verify only; no source edits unless a failing test exposes an in-scope defect.

**Interfaces:**
- Consumes: validated ten-document corpus.
- Produces: remote documents, chunks, BGE-M3 embeddings, and search-quality evidence.

- [x] **Step 1: Run local validation** with `uv run python scripts/ingest_knowledge.py --validate-only`.
- [x] **Step 2: Run lint and full tests** with `uv run ruff check .` and `uv run pytest`.
- [x] **Step 3: Inspect diff and commit graph**, ensuring original WIP paths are absent.
- [x] **Step 4: Ingest to Supabase** with `uv run python scripts/ingest_knowledge.py`.
- [x] **Step 5: Install/use the existing embeddings group** and run `uv run --group embeddings python scripts/embed_knowledge_chunks.py`.
- [x] **Step 6: Measure remote quality** with `uv run --group embeddings python scripts/measure_search_quality.py`.
- [x] **Step 7: Push and create PR** with candidate decisions, governance policy, test evidence, remote counts, and rollback note.
- [ ] **Step 8: Remove the clean worktree** with `git worktree remove C:\dev\kda-rag-corpus` after session-only 상태·handoff 문서가 더 이상 필요하지 않을 때 수행한다.
