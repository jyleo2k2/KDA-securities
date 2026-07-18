# Chat Streaming Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream the deterministic engine answer immediately, swap in verified narration, persist narration cache locally, precompute demo narrations, and remove repeated daily-return calculations.

**Architecture:** Keep the rule engine and narration guard boundaries unchanged. Add one backward-compatible SSE event, a model-keyed local JSON cache with throwaway-agent warming, and request-scoped return memoization.

**Tech Stack:** FastAPI, Python 3.13, pydantic-ai, React 19, TypeScript, Vite, Vitest, pytest.

## Global Constraints

- Run Python only through `uv run python` and tests through `uv run pytest`.
- Do not modify narrator guard functions or regular expressions.
- Do not modify DB, migration, repository, user-context, RAG, or knowledge files listed in the task specification.
- Preserve deterministic engine calculation and use the LLM only for narration.
- Keep `ANTHROPIC_MODEL=claude-haiku-4-5`; Sonnet remains an environment override and naturally misses the model-keyed cache.
- Precompute the current six scenario codes with the three `SUGGESTED_CHAT_PROMPTS` entries (18 combinations).

---

### Task 1: Request-scoped return memoization

**Files:**
- Modify: `backend/app/engine/educational_portfolio.py`
- Modify: `tests/test_educational_portfolio.py`

**Interfaces:**
- Preserve `calculate_return_correlation(first, second) -> Decimal | None`.
- Add a private correlation helper consuming precomputed daily-return dictionaries.

- [ ] Capture a pre-change 120-scenario JSON snapshot and one-scenario duration/call count.
- [ ] Add a failing test proving candidate selection computes daily returns once per encountered ISU code.
- [ ] Run the focused test and confirm the expected duplicate-call failure.
- [ ] Add a request-local returns dictionary and private helper; do not add cross-request state.
- [ ] Run focused engine tests, compare all 120 scenario payloads with the snapshot, and measure the same scenario again.
- [ ] Commit the independently verified Task 1 change.

### Task 2: Engine-first SSE and narration replacement

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `tests/test_chat_api.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/GuidePage.tsx`
- Create: `frontend/src/api/client.test.ts`

**Interfaces:**
- Add `event: narration_update` with `data: {"answer": string}`.
- Preserve `phase`, `answer_delta`, `response`, and `error` payloads.

- [ ] Add failing backend tests for delta-before-narration, verified update, fallback omission/limitations, and authenticated update-before-save order.
- [ ] Run the focused tests and confirm order/event failures.
- [ ] Stream deterministic answer chunks before `asyncio.to_thread(narrator.narrate)` only on narration-enabled supported paths.
- [ ] Emit `narration_update` only when the final response is `claude_verified`; persist the final narrated/fallback response after the update.
- [ ] Add `ttfa_ms` to latency logs using the first engine-delta send timestamp.
- [ ] Add a failing frontend parser test, then add the replacement callback and set `streamingAnswer` to the narration text.
- [ ] Run backend stream tests, frontend tests/build, and a local one-request TTFA measurement.
- [ ] Commit the independently verified Task 2 change.

### Task 3: Persistent narration cache and background precompute

**Files:**
- Modify: `backend/app/chat/narrator.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/settings.py`
- Modify: `.env.example`
- Modify: `tests/test_chat_mvp.py`

**Interfaces:**
- Add `Settings.narration_cache_path`, defaulting to `data/cache/narration_cache.json`.
- Keep cache keys unchanged: SHA-256 over model, intent, and prompt.
- Use a throwaway `ClaudeNarrator` for cache population; never run the request narrator agent during startup precompute.

- [ ] Add failing tests for restart cache hits, truncated/empty JSON, no-key no-op, and throwaway-agent precompute.
- [ ] Run focused tests and confirm expected persistence/precompute failures.
- [ ] Load valid entries into the LRU at construction and atomically persist verified entries via temporary file replacement.
- [ ] Treat load/write failures as cache misses/warnings without changing the returned verified response.
- [ ] Add a background precompute function for six scenarios by three suggested prompts and reload warmed entries into the request narrator.
- [ ] Keep existing `prewarm()` behavior and its throwaway-agent regression test intact.
- [ ] Run all narrator/dependency tests and commit the independently verified Task 3 change.

### Task 4: Final verification and pull request

**Files:**
- Verify all changed files and PR metadata.

- [ ] Run `uv run pytest` and require zero failures.
- [ ] Run `uv run ruff check .` and require zero findings.
- [ ] Run `npm run build` and `npm test` under `frontend` and require success.
- [ ] Confirm 120 scenarios have zero payload differences and record Task 1 before/after measurements.
- [ ] Confirm prohibited DB/RAG/guard files have no diff.
- [ ] Review the complete diff for request traceability and create Task-sized commits.
- [ ] Push `codex/perf-chat-streaming-latency` and create a PR with contract, measurements, test updates, and collision-avoidance notes.
