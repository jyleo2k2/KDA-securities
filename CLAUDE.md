# 연금 코파일럿 — AI 자동로드 진입점

> 세션 시작 시 Claude Code가 자동으로 읽는 30초 오리엔테이션. 상세는 링크 문서로.
> ⚠️ 이 파일은 [AGENTS.md](./AGENTS.md)(Codex용)와 **내용 동기화**된다(도구끼리 서로 안 읽음). 한쪽 고치면 다른 쪽도 같이 고칠 것.
> 최종 갱신: 2026-07-13 · 단계: **DC형 타깃 기획 확정 / 구현 전(현재 레포는 문서만)**

## 한 줄 정의
DC형 퇴직연금 계좌를 선택했지만 운용 방법을 모르는 이용자에게 **계좌 운용 원리와 선택 기준을 쉽게 설명**하고, 스스로 운용 결정을 내리도록 돕는 모바일 연금 운용 가이드. (교육·의사결정 지원형 — 일임 아님)

## READ-FIRST (이 순서로)
1. 이 파일 (진입점)
2. [docs/team/_공통_AI규칙.md](./docs/team/_공통_AI규칙.md) — 헌장(모든 AI가 지킬 고정 규칙·가드레일)
3. [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 시스템 구조·폴더 경계
4. [README.md](./README.md) — 전체 문서 지도
   - 제품 상세: [pension-copilot-proposal.md](./pension-copilot-proposal.md)(청사진) · [pension-basics.md](./pension-basics.md)(도메인·엔진 근거) · [pension-market-research.md](./pension-market-research.md) · [kiwoom-pension-news.md](./kiwoom-pension-news.md)

## 절대 규칙 (어기면 안 됨 — 상세 근거는 헌장)
- **교육·의사결정 지원형만**: AI는 DC형 계좌 운용 원리·비교·시뮬레이션을 설명하고, 실제 상품 선택과 실행은 이용자가 판단한다. 일임(전권 위임) 구조 금지.
- **Explainable by Design**: 계산·판단은 **규칙 기반 엔진**이 한다. **LLM은 엔진 수치의 자연어 서술 + Q&A만**. LLM이 직접 수치 계산 금지.
- **한도 내장**: IRP/연금저축 위험자산 70% 한도를 엔진 제약으로 강제(디폴트옵션 상품은 예외). 위반 제안 원천 차단.
- **실/목 데이터 경계**: 시장 상품 수치 = 통합연금포털 실데이터(+KRX 보조), 사용자 계좌 = 시나리오 목데이터 3종. 이 경계를 흐리지 마라.
- **모든 수치엔 출처 칩**. 성향 밖 상품 제안 금지(금소법 적합성).

## 작업 환경
- Python: **`uv run python`** 사용 (단독 `python` 금지). 스택(안): PWA + FastAPI + Claude API 하네스. *세부 스택은 팀 확정 후 — TODO.*
- 한국어 .md는 편집도구/UTF-8로만. **PowerShell·sed 일괄치환 금지**(인코딩 깨짐).
- Git: `main` 직접 push 금지 → 브랜치 → PR.

## 일하는 방식 (메타)
먼저 읽어라(추측 금지) → 계획 먼저 제시·승인 → 작게 쪼개라 → 모르면 `TODO: 확인 필요`(환각 금지) → 검증하고 정직히 보고(테스트 실행 결과로).

## 현재 상태 / 다음 단계
- 기획·리서치 확정, **코드 미착수**. 통합연금포털 Open API 키 발급 완료.
- 다음: 팀 5명 확정 → 폴더=경계 역할배분·팀원별 프롬프트팩(플레이북 Step 5) → 첫 코드 골든패스 → `.claude/settings.json` 자동검증 훅(Step 7, 테스트 명령 생기면).
