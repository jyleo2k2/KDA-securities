# PR #63 Selective Rescue Implementation Plan

> **For Codex:** Execute each task with test-first changes on a fresh branch based on the newly merged `main`. Do not copy whole files from PR #63.

**Goal:** Rescue the useful chat deletion, deterministic market-news conversation, and pension-account guidance behavior from PR #63 without regressing the current narrator, RAG, streaming, or tone work.

**Architecture:** Land three small PRs in order. Each PR starts from the latest `origin/main`, adds contract tests before production code, and is merged only after backend and frontend regression checks. Existing applied migrations stay immutable; news retention uses one additive repair migration and the existing `naver-pension-news.yml` workflow only.

**Stack:** FastAPI, psycopg, pydantic-ai chat service, PostgreSQL/Supabase migrations, React/TypeScript/Vite, pytest, Ruff, Vitest.

---

## Task 1: Owner-scoped chat-session deletion

**Files:**
- Modify: `tests/test_chat_repository.py`
- Modify: `tests/test_chat_api.py`
- Modify: `frontend/src/api/client.test.ts`
- Modify: `frontend/src/pages/GuidePage.test.tsx`
- Modify: `backend/app/chat/repository.py`
- Modify: `backend/app/api/chat.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/GuidePage.tsx`
- Modify: `frontend/src/index.css`

1. Add repository tests proving the delete query contains both `id` and `owner_id`, returns the deleted id, and maps missing/foreign sessions to `ChatSessionAccessError`.
2. Run `uv run pytest tests/test_chat_repository.py -q` and confirm the new tests fail because `delete_session` does not exist.
3. Add API tests for unauthenticated `401`, owned `204` with an empty body, foreign/missing `404`, and database failure `503`.
4. Run `uv run pytest tests/test_chat_api.py -q` and confirm the new endpoint tests fail.
5. Implement the smallest repository method and FastAPI `DELETE /chat/sessions/{session_id}` endpoint. Rely on the existing database cascade; do not add a migration.
6. Add frontend client and interaction tests for the DELETE request, confirmation, disabled state, list removal, and clearing the active deleted conversation.
7. Run the new frontend tests and confirm they fail before implementing `apiDelete`, `deleteChatSession`, and the history-row delete control.
8. Implement the minimal accessible UI and CSS. Preserve the current GuidePage response rendering and auth-generation race guards.
9. Verify with `uv run pytest`, `uv run ruff check .`, `npm test`, `npm run build`, and `git diff --check`.
10. Commit, push, create PR, review the PR diff against this task, and merge after checks pass.

## Task 2: Deterministic market-news selection and follow-up context

**Files:**
- Modify: `tests/test_query_planner.py`
- Modify: `tests/test_news_retrieval.py`
- Modify: `tests/test_market_news_repository.py`
- Modify: `tests/test_market_news_migration.py`
- Modify: `tests/test_chat_repository.py`
- Modify: `tests/test_chat_api.py`
- Modify: `tests/test_chat_mvp.py`
- Modify: `backend/app/chat/models.py`
- Modify: `backend/app/chat/query_planner.py`
- Modify: `backend/app/chat/repository.py`
- Modify: `backend/app/chat/service.py`
- Modify: `backend/app/retrieval/repository.py`
- Modify: `backend/app/ingestion/naver_news_repository.py`
- Add: `supabase/migrations/20260719*_add_market_news_active_retention.sql`

1. Add planner tests for KR/US/all-market scope, requested count, ordinal selection, comparison, source request, refresh/other-news request, and short follow-ups resolved from prior server context.
2. Add retrieval tests specifying deterministic ordering: active summarized articles first, score then publication time then stable id tie-break; balance KR/US for all-market requests; exclude previously shown ids; fetch selected ids in caller order.
3. Add persistence/API tests proving authenticated session context is restored from the latest stored assistant response and client-provided context cannot override it.
4. Add migration/repository tests for `is_active`, deactivation of expired rows, and active-row filtering. Use a new additive migration only; never edit `20260717084953_add_market_news_selection.sql` or other applied migrations.
5. Run targeted tests and observe the expected failures before production changes.
6. Add the smallest typed `NewsConversationContext`, deterministic repository methods, query-plan fields, and service branches needed for first/second article, comparison, source, refresh, and region follow-ups.
7. Keep the existing `naver-pension-news.yml`; do not add `naver-market-news.yml`. Preserve current streaming/cache/guard behavior and current 해요체.
8. Verify targeted tests, then `uv run pytest`, `uv run ruff check .`, `npm test`, `npm run build`, and `git diff --check`.
9. Commit, push, create PR, review deterministic policy and migration safety, and merge after checks pass.

## Task 3: Pension-account overview from engine/RAG SSOT

**Files:**
- Modify: `tests/test_query_planner.py`
- Modify: `tests/test_chat_mvp.py`
- Modify: `tests/test_pension_tax_chat.py`
- Modify: `backend/app/chat/query_planner.py`
- Modify: `backend/app/chat/service.py`
- Modify only if required: `backend/app/chat/tools.py`

1. Add routing tests for general DC/IRP/연금저축 comparison, account-specific rules, tax-calculation requests, withdrawal/receipt topics, and ambiguous account questions.
2. Add response tests that require verified RAG sources for general/rule explanations and the existing pension-tax engine for calculations. Assert no hardcoded future-return claims and current 해요체.
3. Run targeted tests and confirm the missing overview behavior fails.
4. Implement a small orchestration path that reuses existing `KnowledgeSearch`/verified knowledge evidence and existing pension-tax engine outputs. Do not port the 507-line `pension_account_overview.py`; do not duplicate legal limits, deduction amounts, or tax formulas in chat code.
5. Keep deterministic fallback text limited to data-boundary and missing-evidence guidance. Every substantive rule/number must come from RAG evidence or engine output.
6. Verify targeted tests, then `uv run pytest`, `uv run ruff check .`, `npm test`, `npm run build`, and `git diff --check`.
7. Commit, push, create PR, review SSOT/tone/numeric provenance, and merge after checks pass.

## Task 4: Final integration and PR #63 cleanup

1. Fetch latest `main` and confirm all three merged PR commits are ancestors of `origin/main`.
2. Run the full backend and frontend regression suite from a clean latest-main worktree.
3. Compare PR #63's three commits against latest main and confirm every accepted behavior is covered by the merged PRs while duplicate workflow, rewritten migration history, and hardcoded overview remain excluded.
4. Close PR #63 with a concise supersession note linking the replacement PRs.
5. Delete remote `codex/main-work-20260716`, remove its clean local worktree/branch if present, and prune stale worktree metadata. Never delete active `db` or `rag` worktrees/branches.
6. Report PR links, merge commits, test totals, retained/excluded PR #63 slices, and remaining active worktrees.
