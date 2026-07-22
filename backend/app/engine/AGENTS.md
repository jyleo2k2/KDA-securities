# 연금 코파일럿 규칙 엔진 진입점

> 적용 범위: `backend/app/engine/` 하위 전체.
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-22

## 담당 오너

**김태형.** 알고리즘 판단(배분 로직·위험 산출·계획가정)의 변경은 오너 합의 후 진행한다. 다른 세션은 버그 수정·성능 개선이라도 결과 수치가 바뀌는 변경이면 합의 없이 머지하지 않는다.

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- 파일 수정 전에 `git-session-manager`로 담당자와 예상 수정 경로를 claim한다. 루트 `main` 관제 워크트리에서는 수정하지 않는다.
- 최신 `origin/main`에서 만든 `engine/<owner>/<task>` 브랜치·전용 워크트리를 사용하고 첫 커밋 후 Draft PR을 연다. 병합 브랜치 재사용과 `main` 직접 push는 금지한다.
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다. 공유 엔진 I/O나 `__init__.py`가 겹치면 이재용과 김태형이 병합 순서를 정한다.

## 불변식 (모든 세션 공통)

- 순수 규칙 엔진: **DB 의존성 추가 금지, LLM 호출 금지, 네트워크 호출 금지.** 입력은 호출자가 주입한다.
- 수치는 `Decimal` 결정론 계산. 같은 입력이면 언제나 같은 출력.
- 수익률 데이터는 과거 실적만 다룬다. 미래 수익 예측 로직 금지.
- DC·IRP 위험자산 70% 한도와 계좌별 규칙 혼합 금지는 엔진 코드로 강제된다 — 완화·우회 금지.
- 교육용 포트폴리오의 정식 엔진은 `educational_portfolio.py`다. 신규 기능은 이 모듈 기준으로 작업한다.

## 성능 변경 규칙

성능 최적화(캐시·메모이제이션 등)는 허용하되, 변경 전후 교육용 포트폴리오 120개 시나리오(나이 25·35·45·52 × 은퇴 55·60 × 성향 5 × 계좌 3) 결과가 **0건 차이**임을 테스트로 증명하고 PR에 전후 실측 수치를 기록한다.

## 검증 명령

```powershell
uv run pytest tests/test_engine.py tests/test_educational_portfolio.py tests/test_pension_tax.py tests/test_allocation.py tests/test_simulation.py tests/test_portfolio_risk_and_cma.py tests/test_planning_return.py   # 빠른 루프
uv run pytest        # 세션 종료 전 전체 1회
uv run ruff check .
```

도메인 근거: [docs/20_리서치/연금_기초.md](../../../docs/20_리서치/연금_기초.md).
