# 벤치마킹 API 작업 핸드오프

> 목적: 다음 작업자가 이 문서의 프롬프트를 그대로 읽고, 현재 조사·승인 상태에서 벤치마킹 REST API 작업을 이어간다.
> 작성 기준: 2026-07-20, `main` 작업트리. 이 문서는 작업 지시용이며 구현은 아직 시작하지 않았다.

## 다음 작업자 프롬프트

너는 연금 코파일럿 프로젝트의 백엔드 세션이다. 현재 작업은 피그마의 "투자 벤치마킹" 목록과 바텀시트 상세 화면용 REST API를 만드는 일이다.

### 시작 전 필독

1. 루트 `AGENTS.md`
2. `docs/team/_공통_AI규칙.md`
3. `docs/30_스펙/아키텍처.md`, `docs/30_스펙/코드베이스_지도.md`
4. `docs/30_스펙/화면_표시_데이터_계약.md`
5. DB를 수정할 가능성이 생기면 `supabase/AGENTS.md`, `supabase/DB_HANDOFF.md`
6. 이 파일 전체

### 절대 규칙

- 수익률은 기존 `trailing_12m_return_pct`의 과거 12개월 실적만 사용한다. 미래 수익 예측·보장 표현을 만들지 않는다.
- 모든 응답에 `data_boundary="mock"`, 기존 `BENCHMARK_NOTICE` 수준의 목데이터 고지와 수치 출처 정보를 유지한다.
- 내부 `user_id`, `account_id`, Auth 사용자 ID, 로그인 ID 등 개인 식별·연결 식별자는 API에 내보내지 않는다. 화면에는 안전한 공개용 `portfolio_id`와 익명 별명만 제공한다.
- API와 SQL에서 독자적인 투자 판단·수익률 예측을 만들지 않는다. 엔진 변경은 김태형 합의가 필요하다.
- 이미 적용된 `supabase/migrations/` 파일은 수정하지 않는다. 새 public 테이블이 정말 필요해지면 additive migration, RLS, GRANT 검증을 적용하고 원격 적용은 이재용 승인 후에만 한다.
- `main` 직접 push 금지. `benchmark/` 접두사 브랜치와 Draft PR을 사용한다.
- Python은 `uv run python`, 검증은 `uv run pytest`, `uv run ruff check .`을 사용한다.

## 목표 API

기존 집계 전용 `GET /benchmark/summary`는 유지한다. 다음 두 엔드포인트를 추가하는 것이 목표다.

- `GET /benchmark/portfolios`: 목록, 정렬·페이지네이션 포함
- `GET /benchmark/portfolios/{portfolio_id}`: 상세

후보 수정 파일:

- `backend/app/api/benchmark.py`
- `backend/app/benchmark_repository.py`
- `tests/test_benchmark_api.py`
- 승인 후 새 화면 데이터 계약 문서 `docs/30_스펙/`
- 승인 후 필요할 경우 `data/mock/`의 작은 표시용 manifest

## 이미 조사해 확인된 사실

### 기존 벤치마크 모집단

- `benchmark_mock_users`: 10,000명
- `benchmark_mock_accounts`: 16,900개
- `benchmark_mock_holdings`: 79,381개
- 이 테이블의 보유내역은 `EQUITY_KR`, `EQUITY_GLOBAL`, `BOND`, `CASH`, `PRINCIPAL_GUARANTEED` 자산군 수준이다. 전체 1만 명에게는 ETF 이름·종목코드가 없다.
- `employment_type`은 `SALARIED_EMPLOYEE`, `SELF_EMPLOYED`, `FREELANCER` 세 값뿐이다. "2차전지 종사자" 같은 산업 직군 데이터는 없다.
- 한 사용자는 1~3개 계좌를 보유한다. 각 계좌에는 `contribution_years`, `balance_krw`, `trailing_12m_return_pct`, `return_period_end`가 있다.

### 상세화된 대표 포트폴리오 6명

아래 6명은 이미 존재하며, 신규 생성하지 않는다. `backend/app/chat/heroes.py`의 `build_demo_heroes()`를 실행해 실제로 6명이 로드됨을 확인했다.

| scenario_code | 계좌 수 | 전체 보유 | ETF 종목 수 |
| --- | ---: | ---: | ---: |
| `dc_dormant` | 1 | 7 | 5 |
| `tax_contribution_uninvested` | 2 | 13 | 10 |
| `overlap_risk_concentration` | 3 | 20 | 15 |
| `young_retirement_distance` | 2 | 13 | 10 |
| `family_budget_pressure` | 3 | 20 | 15 |
| `pension_payout_transition` | 2 | 13 | 10 |
| 합계 | 13 | 86 | 65 |

- ETF가 아닌 나머지 21개는 현금성·원리금보장 상품이다.
- 대표 6명은 `demo_user_financial_context.benchmark_user_id`로 벤치마크 사용자 6명에 연결돼 있다.
- 대표 13개 계좌는 `mock_accounts.benchmark_account_id`로 벤치마크 계좌에 연결돼 있다.
- `mock_holdings` 및 공통 `account_holding_snapshots`에는 ETF 이름·`etf_isu_code`·금액·자산군이 있다. 해당 ETF의 계좌 적격성과 데이터 정합성은 기존 migration에서 검증됐다.
- 근거: `supabase/migrations/20260718090000_link_demo_hero_etf_holdings.sql`, `20260720044229_unify_demo_customer_contract.sql`, `20260720044230_sync_demo_etf_holdings_to_common_accounts.sql`, `supabase/DB_HANDOFF.md`.

## 이재용이 승인한 표시용 목데이터

목록·상세 대상은 위 대표 6명으로 제한한다. 기존 `박준호(가상)` 같은 이름은 API에 노출하지 않고 아래 익명 별명만 사용한다.

| scenario_code | display_alias | like_count | follower_count |
| --- | --- | ---: | ---: |
| `dc_dormant` | 차근차근거북이 | 1,204 | 1,118 |
| `tax_contribution_uninvested` | 절세모으미 | 986 | 917 |
| `overlap_risk_concentration` | 분산투자너구리 | 1,431 | 1,328 |
| `young_retirement_distance` | 연금새싹 | 754 | 699 |
| `family_budget_pressure` | 노후준비곰 | 1,126 | 1,042 |
| `pension_payout_transition` | 안정전환부엉이 | 868 | 804 |

- 좋아요 수는 모든 행에서 팔로워 수보다 조금 많다.
- 이 값은 실사용자 활동 데이터가 아닌 화면 표시용 목데이터다.
- 권장 구현: 위 6개 행만 가진 명시적 `data/mock/benchmark_portfolio_presentation.json`을 새로 두고, 생성 규칙·해시·ID 기반 가짜 값은 만들지 않는다. DB 마이그레이션은 이 표시 전용 6개 값 때문에 만들지 않는다.

## 아직 승인받아야 하는 두 가지 — 승인 전에는 구현하지 말 것

### A. 사람 단위 포트폴리오의 수익률

화면은 6명의 사람 단위 포트폴리오를 보여준다. 하지만 5명은 여러 계좌를 가지며, 기존 수익률은 계좌별 `trailing_12m_return_pct`만 있다.

선택지:

1. **권장:** 사람의 전체 잔액을 기준으로 계좌별 과거 12개월 수익률을 잔액가중 평균한다. 응답에 `return_aggregation_method="balance_weighted_account_trailing_12m"`와 한계(현금흐름 반영 TWR이 아님)를 명시한다.
2. 대표 계좌 하나의 수익률만 표시한다. 사람이 아닌 계좌의 성과가 되므로 권장하지 않는다.

API가 독자적인 판단을 만들면 안 되므로, 1번은 순수한 표시 집계 규칙으로 문서화하고 엔진 오너 김태형의 합의를 받는다. 합의 전에는 반환 필드를 확정하거나 임의 합산하지 않는다.

### B. "직접 구현 가능" 배지와 전략 규칙 상태

쉽게 말해 이 배지는 "화면에 나온 구성대로 사용자가 자기 연금계좌에서 비슷하게 담을 수 있는가"를 뜻한다. 현재 별도의 판정 필드·상태 문구는 없다.

제안 규칙:

- ETF 부분은 ETF 이름·종목코드가 있고 해당 계좌에 적격이며 비중 합계가 100%이고 미분류 종목이 없으면 직접 구성 가능으로 본다.
- 현금성·원리금보장 부분은 정확한 상품코드가 아니라 자산 종류만 있으므로, 상태 문구로 "ETF 종목과 비중은 직접 구성할 수 있어요. 현금성·원리금보장 부분은 이용 중인 금융회사의 상품 중에서 선택해야 해요."를 함께 표시한다.
- 전략 이름은 기존 5단계 `risk_profile`과 `PROFILE_POLICY`의 strategy ID, `engine/strategy_presentation.py`의 표시 메타를 재사용한다. 새 전략을 만들거나 수익률 가정을 바꾸지 않는다.

이 규칙을 승인한 뒤에만 engine 변경 여부를 김태형과 합의하고 구현한다. 엔진 변경이 필요 없다면 기존 확정 메타를 읽는 최소한의 어댑터만 둔다.

## 구현 순서 (두 승인 후)

1. 새 브랜치 `benchmark/portfolio-api`를 `main`에서 만든다. 작업트리와 원격 main 상태를 먼저 확인한다.
2. `data/mock/benchmark_portfolio_presentation.json`에 승인된 6개 별명·좋아요·팔로워만 명시한다. 이 파일은 식별자·로그인 정보·비밀번호를 포함하지 않는다.
3. REST 응답 계약을 `docs/30_스펙/`에 문서화한다. 기존 화면 표시 자산군 매핑을 재사용한다.
   - 국내주식: `EQUITY_KR`
   - 해외주식·ETF: `EQUITY_GLOBAL`
   - 채권: `BOND`
   - 현금성: `CASH`, `PRINCIPAL_GUARANTEED`
   - 대체: 값이 없더라도 0%로 포함
4. 테스트를 먼저 작성한다.
   - 목록은 공개 ID·별명·직업 표시·운용기간·금액·과거 12개월 수익률·5개 자산군·전략·좋아요·팔로워·목데이터 고지를 반환한다.
   - 정렬은 명시 화이트리스트만 허용하고 기본은 수익률 내림차순이다. 페이지네이션 경계도 검사한다.
   - 상세는 벤치마크 도넛용 5개 자산군과 ETF 종목명·자산군·현재 비중을 반환한다.
   - 실제 ID·Auth ID·로그인 ID가 응답에 없음을 검사한다.
   - 존재하지 않는 공개 `portfolio_id`는 404다.
5. `BenchmarkRepository`에 대표 6명 조회만 additive로 구현한다. SQL은 매개변수화하고 read-only로 유지한다. 공개 ID는 내부 DB ID가 아닌 manifest의 안전한 ID를 사용한다.
6. `api/benchmark.py`에 Pydantic 응답 모델·두 GET 경로를 추가한다. `BENCHMARK_NOTICE`와 `data_boundary="mock"`을 유지한다.
7. "내 현재 포트폴리오 vs 벤치마크"와 "변동 전/후"는 아직 입력 계약이 없다. 이 API가 현재 사용자·계좌를 알아야 한다면, 인증과 `current_account_id`의 소유권 검증 계약을 별도 승인받고 구현한다. 승인 전에는 프론트가 조립해야 하는 값을 API가 추측해 만들지 않는다.
8. 검증 후 PR 본문에 `계약 변경`을 표시하고, 목데이터 범위·엔진 무변경 또는 오너 합의·실측 결과를 적는다.

## 필수 검증

```powershell
uv run pytest tests/test_benchmark_api.py
uv run pytest
uv run ruff check .
git diff --check
```

PR에는 각 명령의 실제 출력과 다음 내용을 넣는다.

- 목록/상세가 대표 6명 범위임
- 수익률은 과거 12개월 실적임
- 모든 값이 `mock` 경계·고지를 유지함
- 공개 응답에 내부 식별자·개인 식별 정보가 없음
- DB migration을 만들었는지 여부와, 만들었다면 RLS·GRANT 검증 결과
- REST 응답 필드 추가에 따른 `계약 변경`

