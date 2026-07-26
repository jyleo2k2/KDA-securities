# codex/이재용/chat-copy-polish — 남은 작업

> 작성일: 2026-07-26 · 작성자: 이재용(codex) · PR: [#379](https://github.com/jyleo2k2/KDA-securities/pull/379) (Draft)
> 대상 작업: 인계 프롬프트 [인계_챗봇_답변문구_톤리뷰.md](./인계_챗봇_답변문구_톤리뷰.md) — PR #362 산출물 답변 54개 톤 리뷰

## 1. 작업 상태 — 코드 작업은 완료

답변 54개를 전부 실제 출력 형태로 뽑아 읽고 근거 있는 8곳을 고쳤다. 커밋·push·Draft PR까지 마쳤다.
로컬 검증은 기준선과 동일하다.

| 항목 | 결과 |
|---|---|
| `uv run pytest -q` | 1505 passed, 1 skipped (기준선 동일, 테스트 개수 불변) |
| `uv run ruff check backend/app/chat tests/` | All checks passed |
| `git diff --check origin/main` | 클린 |

수정한 파일은 `backend/app/chat/handlers/`의 `glossary.py`·`hesitation.py`·`graceful_decline.py` 3개다.
수치와 사실은 바꾸지 않았고 문장 구조만 손봤다.

## 2. 남은 일 — 이것만 하면 끝난다

### 2-1. (차단) GitHub Actions 러너 미배정 — 저장소 전역 장애

PR #379의 `backend`·`frontend`·`route-map-sync` 3개 job이 모두 실패했지만 **이 PR의 코드 문제가 아니다.**
러너가 배정되지 않은 채 3초 만에 끝났고 실행된 스텝이 0개다(`runner_name`이 비어 있음).

2026-07-26 09:55:01(`chat-donut-sort-by-weight`)을 마지막으로 **09:56:44부터 `main` push를 포함한 저장소의 모든 CI 실행이 예외 없이 실패**로 바뀌었다.
`.github/workflows/ci.yml`은 이 기간에 변경되지 않았다.

할 일:

1. GitHub Settings → Billing / Actions usage에서 사용량 한도·결제 상태를 확인한다.
2. 해결되면 PR #379의 CI를 재실행한다. 코드 수정은 필요 없다.
3. 같은 이유로 막혀 있는 다른 PR(#375 등)도 함께 재실행 대상이다.

확인 명령:

    gh run list --limit 20 --json headBranch,conclusion,createdAt
    gh pr checks 379

### 2-2. Draft → Ready 전환과 머지 승인

CI가 초록으로 돌아온 뒤 Draft를 해제하고 이재용(총괄) 머지 승인을 받는다.
`route-map-sync`는 프론트 라우트·화면 변경이 없으므로 통과가 정상이다(이 PR은 백엔드 문구만 변경).

### 2-3. 병합 후 정리

    uv run python scripts/git_session_manager.py release

병합 확인 후 브랜치·워크트리 삭제는 `git-pr-cleanup`의 검증을 거쳐 수행한다.
워크트리 경로: `C:\dev\finance-project-1-codex-이재용-chat-copy-polish`

## 3. 리뷰어에게 물어볼 것 (선택)

톤 리뷰 중 근거가 약해 **그대로 둔** 항목이다. 총괄이 다르게 판단하면 후속 작업으로 처리한다.

- 62~66자 문장 4개(`복리가 왜 좋아?`, `내가 잘하고 있는 건가?` 등) — 60자 기준을 살짝 넘지만 쉼표로 자연스럽게 끊긴다. 억지로 쪼개면 뚝뚝 끊기는 인상이 된다.
- `한 곳에 몰아넣으면 왜 위험해?`의 "자산이" 3회 반복 — 같은 개념을 지칭하는 필수 반복이라 바꾸면 뜻이 흐려진다.
- 여는 문장 3종 배분은 `common` 2 / `worth_asking` 2 / `common_and_worth` 2로 이미 균등해 손대지 않았다.

## 4. 참고 — 이 작업에서 발견한 것

`S&P500` 조사 오류는 취향 문제가 아니라 실제 결함이었다.
`tests/test_chat_economy_glossary.py:69`는 `"S&P500이 뭐야?"`를 단언하는데
`glossary.py`의 후속 질문 생성기는 `"S&P500가 뭐야?"`를 만들고 있었다.
코드 안에서 같은 단어를 읽는 법이 서로 어긋나 있었고, 테스트가 후속 질문 라벨까지는 검사하지 않아 드러나지 않았다.

후속 질문 버튼 50개를 모두 실행해 막다른 폴백으로 빠지는 경우가 0건임은 별도 프로브로 확인했다(프로브는 커밋하지 않음).
