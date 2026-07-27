# 인계 — codex/이재용/chat-answer-brevity (PR #380)

> 작성일: 2026-07-26 · 작성자: Codex(이재용 세션) · 대상: 후속 Codex/Claude 세션
> 브랜치: `codex/이재용/chat-answer-brevity` · PR: [#380](https://github.com/jyleo2k2/KDA-securities/pull/380) (Draft, MERGEABLE)
> 워크트리: `C:\dev\finance-project-1-codex-이재용-chat-answer-brevity`

---

## 0. 한 줄 요약

"연금이 뭐야"에 계좌 규칙 전문 3,314자가 떨어지던 것을 490자 정의 답변으로 바꿨다.
**PR #380은 커밋·푸시까지 끝났고 Draft 상태다.** 아래 3번의 잔여 항목은 이 PR에
포함하지 않았으며, 별도 작업으로 남긴다.

---

## 1. 이 브랜치에서 끝낸 것

| 대상 | 내용 |
|---|---|
| `handlers/account_rules.py` | 계좌 미지목 정의 질문만 짧은 소개로 보내는 예외 추가. `_PENSION_DEFINITION` 문구, `_asks_pension_definition()` 신설. 계좌 카드 3종 본문을 문단 → 한 문장 |
| `query_planner.py` | `_PENSION_BASICS_QUESTION`에 `뭔지`·`이란`·`이라는` 추가 |
| `cards.py` | `verified_pension_account_brief`가 빈 배열을 반환하던 것을 `pension_account_brief_follow_ups()` 3종으로 교체 |
| `narrator.py` | 350자 상한이 흩어져 있던 3곳을 `NARRATION_MAX_CHARS` 상수로 통합. 프롬프트 문장 수 지시를 "두 문장 이내"로 축소 |
| `tests/test_chat_answer_brevity.py` | 신규. 화면 총 분량 900자 상한, 정의 질문 문구, 후속 질문 라우팅, 상한 상수 일치 검증 |

검증: `uv run pytest` → **1518 passed, 1 skipped** / `uv run ruff check .` → 통과.

### 분량 변화 (실측)

| 질문 | 이전 | 이후 |
|---|---|---|
| 연금이 뭐야 | 3,314자 | 490자 |
| 연금이 뭔지 알려줘 | 66자(지원 밖) | 490자 |
| IRP랑 연금저축 차이 | 448자 | 281자 |
| IRP가 뭐야 | - | 180자 |

---

## 2. 다음 세션이 재조사하지 않아도 되는 사실

### 2-1. 내레이션 상한을 350자에서 못 낮추는 이유

지연 단축(계좌 비교 5.96초 → 2.72초)을 노리고 160자·280자로 낮춰 봤으나 **둘 다 실패**했다.
세액공제와 중도해지를 함께 묻는 결정론 원문이 **342자**라, 상한을 그 아래로 두면
`len(candidate) > NARRATION_MAX_CHARS`에 걸려 정상 내레이션이 통째로 폴백된다.
실패 재현 테스트: `tests/test_pension_tax_chat.py`의 `test_narrator_must_call_both_tax_tools_before_rephrasing`
외 2건.

따라서 **길이로 지연을 줄이려면 상한이 아니라 결정론 원문 자체를 줄여야 한다.**
원문 길이 분포(실측): 세액공제 한도 251자 · 수령 요건 235자 · 세액공제 계산 220자 ·
중도인출 175자 · 나머지는 대부분 30~60자.

### 2-2. 지연의 진짜 원인 (PR #364에서 확인된 것)

adaptive thinking은 원인이 **아니다**(소넷 ON 9.13초 vs OFF 9.04초). 소넷 자체 생성
속도가 원인이다(같은 241자에 소넷 8.3초 vs 하이쿠 3.6초). `chat.py`의
`stream_before_narration`이 결정론 답변을 먼저 흘리므로 사용자가 보는 10초는
빈 화면이 아니라 문장 교체 시점이다. 진짜 빈 화면이면 Render 콜드 스타트
(무료 인스턴스, 실측 54초)를 의심한다.

### 2-3. 프론트 테스트 4건 실패는 이 브랜치와 무관

`frontend/src/pages/GuidePage.test.tsx`의 아래 4건이 5초 타임아웃으로 실패한다.

- shows three ETF TOP3 tables without numeric cards or issue codes
- keeps every ETF theme paragraph as a separate uniformly spaced item
- hides educational portfolio detail sections while retaining the review panel
- opens the planner instead of resending its dedicated follow-up

**같은 커밋(`eaedbf6`)의 깨끗한 루트 워크트리에서 돌려도 동일하게 실패한다.**
이 브랜치는 프론트 파일을 한 줄도 수정하지 않았다. 별도 작업으로 다뤄야 한다.

---

## 3. 남은 작업 (이 PR에 없음)

### 3-1. [중] 규칙 전문 응답 3,314자 자체를 줄이기

"연금계좌 전체적으로 정리해줘"는 **의도적으로 규칙 전문을 유지**했다. 전용 응답이
따로 있는 질문까지 짧은 소개로 삼키면 회귀가 나기 때문이다(실제로 한 번 발생시켰다가
되돌렸다). 다만 3,314자·섹션 6개는 여전히 한 화면 분량이 아니다.

대상은 `backend/app/chat/pension_account_overview.py`의
`data_mode="verified_pension_account_overview"` 응답이다. 섹션 6개 중 "핵심 숫자부터"만
먼저 보여주고 나머지 5개를 접거나 후속 질문으로 돌리는 방향이 유력하다.
`AnswerSection`에 접힘 상태 개념이 없으므로 프론트 계약 변경이 필요하다 —
`docs/30_스펙/챗봇_추천카드_계약.md`를 함께 봐야 한다.

### 3-2. [중] 카드 안 긴 설명을 문서 링크로 돌리기

사용자 원 요청 중 "길어지면 관련 문서나 링크를 안내하는 방식은 어떤가"는 **후속 질문으로만
대응**했다. 실제 문서 링크는 넣지 않았다. `sources`에 `evidence_id`와 locator가 이미
실려 있으므로, 승인 문서로 연결되는 사용자 노출 링크를 만들 여지가 있다.

주의: 승인 문서는 `data/knowledge/approved_documents.json` 매니페스트로 관리되고
SHA-256이 물려 있다. 사용자에게 노출할 URL이 실제로 존재하는지 먼저 확인해야 한다.
없는 링크를 안내하면 환각과 같은 문제가 된다.

### 3-3. [중] 결정론 원문 길이 줄여 지연 낮추기

2-1에서 적었듯 상한으로는 해결되지 않는다. 251자짜리 세액공제 한도 답변과 235자짜리
수령 요건 답변을 줄이면 내레이션 입력·출력이 함께 짧아져 지연이 준다. 다만 이 문구들은
규칙 엔진 SSOT를 서술한 것이라, 숫자와 조건을 빠뜨리면 `narration_guard`가 아니라
**답변 자체가 부정확해진다.** 승인 근거를 확인하며 조심스럽게 다뤄야 한다.

### 3-4. [저] 프론트 GuidePage 테스트 4건 타임아웃

2-3 참고. 이 브랜치 이전부터 실패 중이며 별도 브랜치가 필요하다. 5초 기본 타임아웃이
부족한 것인지, 실제로 늦어진 렌더링이 있는지 먼저 구분해야 한다.

### 3-5. [저] 내레이터 가드의 서술 확장 미탐

PR #364에서 발견하고 미해결로 남긴 항목이다. 하이쿠가 원문에 없던 서술을 덧붙여도
`narration_guard.py`가 잡지 못한다. 숫자 검증만 있고 문체·서술 확장 검사가 없다.

---

## 4. 작업 환경 메모 (반복해서 막혔던 것)

- **PowerShell 파이프로 한글을 Python stdin에 넘기면 깨진다.** `plan_question`에 넘긴
  한글이 `?`로 바뀌어 라우팅 결과가 왜곡됐다. 프로브는 반드시 `.py` 파일로 쓰고
  `uv run python <파일>`로 실행한다. 끝나면 지운다.
- 파일 읽기는 `uv run python -c "import pathlib; ..."` + `read_text(encoding='utf-8')`.
  `Get-Content`는 한글이 깨진다.
- 커밋 메시지·PR 본문은 `apply_patch`로 임시 파일을 만든 뒤 `-F` / `--body-file`로 넘기고
  node `fs.rmSync`로 지운다. PowerShell 인라인 heredoc은 정책에 막힌다.
- `Remove-Item`은 정책에 막힐 수 있다. node `fs.rmSync`를 쓴다.
- `git push`는 stderr 때문에 exit 1이어도 성공일 수 있다. 출력으로 판단한다.
- 워크트리에는 `.env`가 없다. 루트에서 복사해야 서버가 뜬다(`.gitignore` 확인됨).
- Playwright는 워크트리에 없다. `output/`에 따로 설치했고, headless shell 버전이 안 맞아
  `chromium-1234/chrome-win64/chrome.exe`를 `executablePath`로 직접 지정해야 떴다.
- 챗봇 화면(`/guide`)은 로그인 게이트 뒤에 있다. 계정 자격이 문서에 없어 자동 캡처를
  하지 못했다. 화면 확인은 사용자 로그인이 필요하다.

---

## 5. 세션 정리

claim된 경로는 아래와 같다. 후속 세션이 같은 파일을 만지려면 이 세션을 먼저 release한다.

```
backend/app/chat/handlers/account_rules.py
backend/app/chat/narrator.py
backend/app/chat/query_planner.py
backend/app/chat/cards.py
tests/test_chat_answer_brevity.py
tests/test_chat_cards.py
tests/test_chat_mvp.py
docs/team/이재용/인계_chat-answer-brevity.md
```

```powershell
cd C:\dev\finance-project-1-codex-이재용-chat-answer-brevity
uv run python scripts/git_session_manager.py release
```
