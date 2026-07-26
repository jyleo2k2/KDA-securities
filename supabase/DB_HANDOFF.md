# 연금 코파일럿 DB 작업 핸드오프

> DB 작업의 단일 현황판이자 인수인계 문서다. 작업자는 시작 전 읽고, 의미 있는 변경을 마칠 때마다 이 문서를 최신화한다.
>
> 최종 확인: 2026-07-23 16:16 KST
> 확인 기준: 리밸런싱 알림 설정 원격 migration·RLS·권한 재검증
> 원격 프로젝트: `KDA-securities`
> 담당자: 김태형
> 머지 승인: 이재용(총괄)

## 1. 문서 운영 규칙

- 상태와 작업 로그의 기준 문서는 이 파일 하나다. 같은 현황을 별도 메모에 복제하지 않는다.
- `LOCAL-DRAFT`, `LOCAL-VERIFIED`, `REMOTE-APPLIED`, `BLOCKED`를 구분한다. 원격 조회 전에는 `REMOTE-APPLIED`로 표시하지 않는다.
- 작업 시작 시 브랜치, HEAD, dirty 파일, 원격 마이그레이션을 확인한다.
- 작업 종료 시 상태표, 결정·위험, 검증 결과, 원격 적용 여부, 다음 작업을 갱신한다.
- 기존 작업 로그는 삭제하지 않는다. 최신 항목을 `작업 로그` 맨 위에 추가한다.
- 불확실한 내용은 추정하지 않고 `TODO: 확인 필요`로 남긴다.
- 루트 [`AGENTS.md`](../AGENTS.md)와 [`CLAUDE.md`](../CLAUDE.md)는 이재용만 수정한다. 이 핸드오프 작업을 이유로 두 파일을 편집하지 않는다.

## 2. 시작 전 읽을 문서

1. 루트 [`AGENTS.md`](../AGENTS.md) 또는 [`CLAUDE.md`](../CLAUDE.md)
2. [`docs/team/_공통_AI규칙.md`](../docs/team/_공통_AI규칙.md)
3. [`docs/30_스펙/아키텍처.md`](../docs/30_스펙/아키텍처.md)
4. [`DB_SESSION_GUIDE.md`](./DB_SESSION_GUIDE.md)
5. 이 문서
6. [`migrations/`](./migrations) 전체를 시간순으로 읽고 [`seed.sql`](./seed.sql) 확인
7. DB 변경과 맞닿는 엔진 모델·저장소·API·테스트 확인

## 3. 현재 원격 상태

2026-07-22 KST에 승인된 해외 ETF 공식 구성정보 migration 2건과 최초 11종목 스냅샷을 적용한 뒤 연결된 Supabase 프로젝트를 읽기 전용으로 재확인했다.

| 항목 | 원격 상태 |
|---|---|
| public 기본 테이블 | 54개 |
| 적용 마이그레이션 | 32개(`20260715005435` ~ `20260723024221`) |
| RLS | 54/54 활성화 |
| `anon` 테이블 권한 | 없음 |
| `authenticated` 권한 | 사용자 소유 엔진 결과·채팅 관련 5개 테이블 |
| `service_role` 권한 | 54개 테이블 |
| `knowledge_chunks.embedding` 타입 | `vector(1024)` |
| HNSW 인덱스 | `knowledge_chunks_embedding_hnsw_idx` 존재 |
| PostgreSQL / 프로젝트 상태 | 17.6.1 / `ACTIVE_HEALTHY` |
| Supabase MCP 현재 연결 | 정상 |

### 원격 주요 행 수

| 테이블 | 행 수 |
|---|---:|
| `pension_savings_provider_stats` | 88 |
| `retirement_provider_stats` | 126 |
| `financial_institutions` | 102 |
| `news_items` | 15 |
| `knowledge_documents` | 15 |
| 활성·BGE-M3 임베딩 `knowledge_chunks` | 56 / 56 |
| `etf_theme_content_reviews` | 230(`.3` 115 + `.4` 115) |
| `etf_theme_content_evidence` | 230(`.3` 115 + `.4` 115) |
| `etf_daily_market_snapshots` | 1,147 |
| 최신 ETF 데이터셋(version 4) 상품 / 총수익 이력 | 2,507 / 1,207,952 |
| 최신 ETF 데이터셋 계좌별 상품(DC / IRP / 연금저축) | 823 / 823 / 861 |
| `mock_scenarios` | 6 |
| `mock_accounts` | 13 |
| `mock_holdings` | 86 |
| `demo_user_financial_context` | 6 |
| `demo_investor_profiles` / `demo_investor_profile_answers` | 6 / 66 |
| `demo_public_portfolio_metrics` | 6 |
| `benchmark_mock_users` | 10,000 |
| `benchmark_mock_accounts` | 16,900 |
| `benchmark_mock_holdings` | 79,381 |
| `profile_question_sets` / `profile_questions` / `profile_question_options` | 1 / 6 / 30 |
| `pension_accounts` / `account_snapshots` / `account_holding_snapshots` | 13 / 13 / 86 |
| `account_cash_flows` / `financial_products` | 0 / 0 |
| `etf_component_snapshots` / `etf_component_snapshot_items` | 911 / 729 |
| 공식 해외 ETF 완전 스냅샷 / TOP3 항목 / 활성 바인딩 | 11 / 33 / 11 |

원격에서 직접 수정된 시나리오 설명 5건과 대표 고객 납입액 5건은 `20260718131917_sync_modified_mock_data.sql`로 migration history에 정식 반영했다. 적용 전후 값과 `updated_at`이 모두 같아 데이터 재기록 없이 이력만 정상 추가됐음을 확인했다.

`20260720044229_unify_demo_customer_contract.sql`과 `20260720044230_sync_demo_etf_holdings_to_common_accounts.sql`은 **원격 적용 완료** 상태다. 첫 migration은 원격 구버전 벤치마크 계좌 10명의 개인연금 합산 납입액을 생성기와 같은 비례·1만 원 단위 규칙으로 보정한 뒤, 1만 명 사용자 전원에 연금저축펀드/개인 IRP 당해연도 납입액 컬럼을 추가하고 대표 6명을 실제 사용자 6행·계좌 13행에 연결하며 대표 보유내역을 86행으로 교체한다. 두 번째 migration은 공통 계좌 13개·스냅샷 13개·상세 ETF 보유 86개로 재동기화한다. 원격 재조회 결과 납입한도·세율·사용자 납입액 투영·legacy/common 잔액 불일치는 모두 0건이고 KODEX·TIGER·ACE·RISE·SOL·HANARO 6개 브랜드가 모두 존재한다.

원격 컬럼 설명 3건(`pension_savings_provider_stats.fee_rate_1y`, `retirement_provider_stats.response_division`, `knowledge_chunks.embedding`)은 `20260718154819_repair_corrupted_column_comments.sql`로 교정했다. 실제 설명을 재조회해 목표 문구와 일치하고 U+FFFD 대체문자가 없음을 확인했다. 테이블·컬럼·데이터·RLS·GRANT는 바뀌지 않았다.

### 현재 54개 테이블의 역할

| 영역 | 테이블 |
|---|---|
| 출처·수집 | `data_sources`, `ingestion_runs` |
| 금융기관·공시 | `financial_institutions`, `institution_aliases`, `pension_savings_provider_stats`, `retirement_provider_stats` |
| 자산·목계좌 | `asset_classes`, `mock_scenarios`, `mock_accounts`, `mock_holdings` |
| 목 벤치마크 | `mock_public_profiles`, `mock_public_portfolios`, `mock_public_portfolio_holdings` |
| 대규모 벤치마크 | `benchmark_mock_users`, `benchmark_mock_accounts`, `benchmark_mock_holdings` |
| 대표 고객 공개 계약 | `demo_user_financial_context`, `demo_investor_profiles`, `demo_investor_profile_answers`, `demo_public_portfolio_metrics` |
| 규칙·감사 | `rule_sets`, `pension_rules`, `engine_runs`, `engine_run_evidence` |
| RAG·뉴스 | `knowledge_documents`, `knowledge_chunks`, `news_items`, `curated_contents`, `etf_theme_content_reviews`, `etf_theme_content_evidence` |
| 채팅 | `chat_sessions`, `chat_messages`, `chat_message_evidence`, `chat_request_idempotency` |
| 사용자·성향·계좌 | `user_profiles`, `profile_question_sets`, `profile_questions`, `profile_question_options`, `investment_profile_assessments`, `investment_profile_answers`, `investment_profile_confirmations`, `pension_accounts`, `account_snapshots`, `account_cash_flows`, `financial_products`, `account_holding_snapshots` |
| ETF 유니버스 | `etf_dataset_versions`, `etf_universe_products`, `etf_return_histories` |
| ETF 일별 시장 | `etf_daily_market_snapshots` |
| ETF 승인 설명 | `etf_product_descriptions` |
| ETF 구성정보 | `etf_component_snapshots`, `etf_component_snapshot_items`, `etf_component_source_bindings` |

## 4. 현재 작업트리의 진행 중 작업

`신규작업브랜치`의 ETF 테마 챗봇 UI·엔진·RAG 변경(`71e896d`)과
`origin/main`의 KRX 전체 상장 ETF 일별 거래량·FastAPI 변경(`b795763` 기준)을
이번 통합 작업트리에 함께 반영했다.

- 신규 `20260720080955_add_krx_etf_daily_market_snapshots.sql`은
  `(base_date, isu_code)` 기준의 거래량·거래대금·NAV 스냅샷과 최신 거래량·종목
  이력 인덱스를 추가한다. RLS를 활성화하고 브라우저 권한을 회수하며
  `service_role`만 허용한다.
- 기존 `data/raw/krx` 원본을 `data_sources`·`ingestion_runs` 근거와 함께 멱등
  upsert하는 적재 스크립트와 `/market/etfs`, 종목별 `volume-history` API를
  추가했다.
- 실제 2026-07-14 KRX 원본 1,147행을 원격 적재했다. 영문 혼합 6자리 코드
  280개와 거래량 0인 13개도 보존하고 원본·DB 거래량·거래대금 합계가 일치한다.
- KRX 변경 단독 검증에서는 전체 회귀 834 passed·1 skipped, Ruff,
  `git diff --check`, FastAPI 원격 조회 1,147건이 통과했다. 이번 통합 결과는
  아래 검증 기준으로 다시 확인한다.

- `20260720091219_add_etf_theme_content_verification.sql`은 원격 적용 완료다.
  MCP가 기록한 실제 버전에 맞춰 로컬 migration 파일명도 정합화했다.
- 승인 지식 문서 15개·활성 청크 56개를 멱등 적재했고, 활성 청크 56개 모두
  `BAAI/bge-m3` 1024차원 임베딩을 보유한다.
- 카탈로그 `2026-07-20.4`의 23개 테마 × 5개 질문 유형 115건을 모두
  `verified`로 적재하고 공식 URL·활성 RAG 청크 근거 115건과 연결했다.
  감사 이력 보존을 위해 기존 `.3` 115건도 삭제하지 않았다.
- migration repair, db reset, 기존 이력 수정은 수행하지 않았다.

### 임베딩 마이그레이션 주의사항

- `20260715165614_fix_embedding_dimension_bge_m3.sql`은 이미 원격 적용됐다.
- 원격 non-null embedding은 45건이고 모두 1024차원이며, HNSW 인덱스도 존재한다.
- 적용된 파일의 "기존 embedding 값은 전부 null" 주석은 원격 적용 직전 사실과 달랐지만, 적용 이력 파일은 수정하지 않는다. 이 문서에 사실 차이만 기록한다.
- 원격 migration history의 해당 버전은 statements 배열이 비어 있다(statement count 0). 과거 이력을 repair하거나 조작하지 않는 legacy 예외로 유지한다.
- 현재 원격 활성 청크 56건은 모두 `vector(1024)` 임베딩을 보유하고 비정상
  차원은 0건이다. 과거 migration 적용 당시의 45건 기록과 구분한다.

## 5. PDF 설계 검토 결론

PDF는 사용자·투자성향·연금계좌·보유상품·커뮤니티를 분리한 개념 설계로는 적절하다. 다만 현재 코드와 Supabase 계약 때문에 그대로 DDL로 옮기면 안 된다.

### 확정 제약

- `CUSTOMER.login_id`, `CUSTOMER.password_hash`는 만들지 않는다. 인증정보는 Supabase Auth만 관리한다.
- 앱 사용자 프로필은 `auth.users(id)`를 참조하는 `user_profiles`로 확장한다.
- 계좌 유형은 코드와 동일한 `dc`, `irp`, `pension_savings`만 사용한다.
- 투자성향은 `stable`, `stable_seeking`, `risk_neutral`, `active`, `aggressive` 5단계를 저장하고 한글은 표시명으로 처리한다.
- 기존 목시나리오의 `conservative`, `balanced`, `growth` 3단계와 5단계 성향의 매핑은 승인 전 만들지 않는다.
- `risk_asset_yn` 대신 `capital_preservation`, `general_risky`, `statutory_exception`과 `eligible_tdf`, `default_option`을 사용한다.
- `provider_name` 문자열을 기준키로 사용하지 않고 `financial_institutions.id`를 참조한다.
- `allocation_rate`와 수익률은 원천값과 계산값을 구분한다. 계산값은 엔진 버전·근거와 함께 남긴다.
- 개인 계좌·성향·대화 데이터는 RAG embedding에 넣지 않는다.

## 6. 제안 스키마

아래 이름과 분할은 2026-07-16 사용자 승인에 따라 구현 범위로 확정했다. `community_reviews`는 후속으로 보류한다.

| 테이블 | 역할 | 핵심 계약 |
|---|---|---|
| `user_profiles` | Auth 사용자 확장 | `user_id uuid PK -> auth.users(id)`, nickname, timestamps |
| `profile_question_sets` | 설문 버전 | version, status, effective dates, rule version |
| `profile_questions` | 문항 | 세트별 code·문구·순서, 현재 엔진의 6개 code와 일치 |
| `profile_question_options` | 선택지·점수 | 문항별 answer value·label·score |
| `investment_profile_assessments` | 성향 진단 이력 | owner, 총점·백분율·5단계 성향, engine/rule version, provisional |
| `investment_profile_answers` | 진단 당시 답변 | assessment·question·option과 당시 값·점수 스냅샷 |
| `pension_accounts` | 실계좌·목계좌 공통 | UUID, `owner_id` 또는 `scenario_id`, account type, institution, data boundary |
| `account_snapshots` | 기준일 계좌 상태 | 누적 납입액·평가액·기준일·출처, 계좌/기준일 unique |
| `account_cash_flows` | 외부 현금흐름 | 납입·인출·이체 금액과 발생일, 과거 수익률 계산 입력 |
| `financial_products` | 상품 마스터 | 기관·외부코드·상품종류·자산군·위험처리·법정예외·출처 |
| `account_holding_snapshots` | 기준일 보유내역 | snapshot FK, product FK 또는 raw name, 평가액·위험처리 스냅샷 |
| `community_reviews` | 공개 포트폴리오 리뷰 | 이번 마이그레이션 제외. owner·portfolio FK·신고·보존 정책 승인 후 별도 구현 |

### 계좌 소유 제약 권장안

- `data_kind='real'`: `owner_id` 필수, `scenario_id` null.
- `data_kind='mock'`: `scenario_id` 필수. 현재 목시나리오는 공용이며 `owner_id`는 null.
- 위 두 경우 외 조합은 CHECK로 차단한다.
- 사용자가 직접 입력한 값과 금융기관에서 수집한 값은 `origin` 또는 출처 필드로 구분한다.

### 수익률·비중 저장 원칙

- `account_snapshots`에는 관측 사실인 납입원금·평가액을 저장한다.
- 외부 현금흐름은 `account_cash_flows`에 저장한다.
- PDF의 `return_rate`는 스냅샷 원천 컬럼으로 취급하지 않는다. 현재 `ReturnSubperiod` 계약으로 계산하고 `engine_runs`와 evidence에 버전형 결과를 저장한다.
- holding 비중은 holding 평가액과 같은 snapshot의 계좌 평가액으로 계산한다. 꼭 캐시해야 한다면 원천값인지 파생값인지 컬럼명과 근거로 구분한다.

## 7. 기존 데이터 처리 계획

### 유지

- 출처·수집·기관·공시·RAG·뉴스·규칙·감사·채팅 테이블은 유지한다.
- `mock_scenarios`와 `mock_public_*`는 시나리오·벤치마크 카탈로그로 유지한다.
- FSS의 provider stats는 기관 단위 집계다. `financial_products` 상품 마스터로 합치거나 제품 데이터인 것처럼 사용하지 않는다.

### 이관

- 현재 6개 시나리오, 13개 계좌, 26개 보유내역을 신규 공통 계좌 구조로 backfill한다.
- 기존 `mock_accounts.balance_krw`와 holdings 합계가 일치하는지 마이그레이션 전후에 검증한다.
- 목상품은 synthetic 출처를 명확히 남기거나 product FK가 아직 없을 때 raw instrument name을 보존한다.
- 필수 reference data와 backfill SQL은 원격에도 적용되도록 마이그레이션에 포함하고, 로컬 reset용 `seed.sql`도 멱등하게 맞춘다.

### 제거 후보

- `mock_accounts`, `mock_holdings`만 최종 제거 후보이다.
- 첫 마이그레이션에서는 삭제하지 않는다.
- 신규 저장소 전환, 세 시나리오 엔진 결과 동등성, 전체 참조 제거를 확인한 뒤 별도 cleanup 마이그레이션에서 삭제한다.
- `data/mock/chatbot_scenarios.json`은 DB 미연결 개발·테스트 fallback으로 유지하되 실행 시점의 두 번째 SSOT가 되지 않게 한다.

## 8. 백엔드 연동 계획

현재 챗봇은 `DATABASE_URL`이 있으면 `PostgresScenarioRepository`, 없으면 `LocalScenarioRepository`를 사용한다. `/engine/mock-scenario/{scenario_code}`는 아직 로컬 저장소 경로다.

1. 완료: `ScenarioRepository` 프로토콜, `PostgresScenarioRepository`, dependency injection, DB/로컬 선택 경계와 원격 E2E.
2. 후속: `/engine/mock-scenario`의 DB 전환 여부를 결정한다.
3. 후속: 사용자 계좌 조회 저장소가 DB 행을 `AccountInput`·`AggregationInput`으로 변환한다.
4. 후속: 성향 저장 API가 입력을 `ProfileSurveyInput`으로 검증한 뒤 규칙 엔진 결과와 버전을 저장한다.
5. 규칙 엔진은 순수 함수로 유지하고 Supabase 의존성을 추가하지 않는다.
6. 계산 결과·규칙·출처 연결은 기존 `engine_runs`·`engine_run_evidence`를 재사용한다.

공유 REST·엔진 I/O·상품 테이블 계약을 바꾸는 PR에는 `계약 변경`을 명시하고 관련 담당자의 합의를 받는다.

## 9. 마이그레이션 절차

1. 작업 시작 시 최신 `main`, dirty 파일, 원격 migration history를 확인한다.
2. Supabase 최신 changelog와 관련 공식 문서를 확인한다.
3. 로컬 전역 CLI가 없으면 `npx.cmd --yes supabase`를 사용하고 실제 명령 도움말을 확인한다.
4. 새 마이그레이션 파일은 CLI의 `supabase migration new <name>`으로 생성한다. 원격 이력에 존재하는 적용 완료 마이그레이션은 수정하지 않는다.
5. 첫 PR은 additive DDL, 인덱스, RLS, GRANT, reference seed만 포함한다.
6. backfill은 사전 건수·합계 기록, 트랜잭션, 사후 동등성 검증을 포함한다.
7. 저장소를 dual-read 또는 fallback 방식으로 연결하고 기존·신규 결과를 비교한다.
8. 원격 적용 전 SQL 구문·테스트·보안 정책·advisors를 확인하고 이재용 승인을 받는다.
9. 원격 적용 후 migration history, 테이블·정책·권한·인덱스·행 수·API E2E를 다시 조회한다.
10. 삭제는 별도 cleanup PR과 마이그레이션으로 수행한다.

공식 기준: [Database migrations](https://supabase.com/docs/guides/deployment/database-migrations), [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security).

## 10. 보안·데이터 계약

- public의 모든 신규 테이블에 RLS를 활성화한다.
- Data API GRANT와 RLS는 별개로 검증한다. 기본값은 `anon`·`authenticated` 권한 회수와 FastAPI 경유다.
- 사용자 소유 정책은 `TO authenticated`와 `(select auth.uid()) = owner_id`를 함께 사용한다.
- UPDATE 정책은 `USING`과 `WITH CHECK`를 모두 둔다.
- `service_role`/secret은 브라우저·로그·문서·커밋에 노출하지 않는다.
- public view가 필요하면 `security_invoker = true`를 사용하거나 클라이언트 권한을 회수한다.
- 권한 오류를 해결하려고 public `SECURITY DEFINER` 함수를 만들지 않는다.
- 모든 사용자 계좌 수치에는 기준일, 실/목 경계, 출처 또는 입력 주체를 연결한다.
- 금액은 기존 계약과 맞는 정밀도를 사용하고, 비율은 반올림 전 원천값과 표시값을 혼동하지 않는다.
- 삭제가 필요한 사용자 콘텐츠는 우선 `deleted_at` soft delete를 사용하고 실제 삭제·보존 정책은 별도 승인한다.

## 11. 검증 기준

### 로컬

```powershell
uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py
uv run pytest
uv run ruff check .
```

## 스키마 정비 B — 파괴적 변경 사전 조사 (LOCAL-VERIFIED)

### 2026-07-21 KST

- 작업 브랜치: `db/schema-destructive-review` (기준 `origin/main` `c66d0ee`). 원격 DB 쓰기·마이그레이션 작성 없음.
- 원격 조사: `mock_public_profiles` 3행, `mock_public_portfolios` 3행, `mock_public_portfolio_holdings` 9행, `curated_contents` 0행.
- 고아 테이블 참조 조사:
  - `frontend/`, `scripts/`, `tests/`에는 네 테이블의 런타임 참조가 없다.
  - `supabase/seed.sql`은 `mock_public_*` 세 테이블에 3/3/9행을 넣으며, `curated_contents`에는 seed가 없다.
  - `docs/`에는 목 벤치마크와 향후 벤치마크 탭의 후보 계약으로 `mock_public_*`가 남아 있다. `curated_contents`는 RAG·콘텐츠 그룹 설명에만 남아 있다.
  - FK 유입: `mock_public_portfolios.profile_id -> mock_public_profiles.id`, `mock_public_portfolio_holdings.portfolio_id -> mock_public_portfolios.id`, `mock_public_portfolio_holdings.asset_class_id -> asset_classes.id`. `curated_contents`의 FK 유입은 0건이다. `asset_classes`는 `account_holding_snapshots`, `financial_products`, `mock_holdings`, `mock_public_portfolio_holdings`가 참조한다.
  - 결론: `mock_public_*`는 seed와 문서상 후속 벤치마크 계약이 있어 **보류**. `curated_contents`는 0행·런타임 참조 0건·FK 유입 0건으로 **삭제 가능 후보**이나, 문서의 RAG·콘텐츠 역할 정리와 소유자 확인 후에만 destructive PR에서 처리한다.
- 레거시 목데이터 이중 저장 조사:
  - `backend/app/chat/scenarios.py:103,105`, `backend/app/chat/user_context.py:277,278,289`가 `mock_accounts`/`mock_holdings`를 아직 직접 읽는다. `backend/app/benchmark_repository.py`는 이름이 비슷하지만 `benchmark_mock_*`만 읽으므로 삭제 대상과 별개다.
  - 동등성 쿼리(시나리오별 계좌 수·보유 건수·계좌 잔액 합계·보유 평가액 합계): `dc_dormant` 1/7/60,980,000원, `tax_contribution_uninvested` 2/13/40,680,000원, `overlap_risk_concentration` 3/20/149,330,000원, `young_retirement_distance` 2/13/23,210,000원, `family_budget_pressure` 3/20/88,660,000원, `pension_payout_transition` 2/13/157,430,000원. 여섯 시나리오 모두 legacy/common 지표가 일치했다(총 13계좌·86보유).
  - 정리 제안: (1) `scenarios.py`와 `user_context.py`를 공용 모델 조회로 전환하고 계약 테스트를 추가한다. (2) 시나리오별 동등성 쿼리와 Auth/RLS E2E를 재실행한다. (3) 백업 가능한 export와 롤백용 복원 SQL을 별도 승인 PR에 포함한 뒤 `mock_holdings` → `mock_accounts` 순서로 삭제한다. 삭제 직후 공용 모델 재조회·동등성 검증을 수행하며, 실패 시 삭제 migration을 되돌리고 백업으로 복원한다.
  - `mock_scenarios`는 `pension_accounts.scenario_id`가 참조하므로 삭제 대상이 아니다.
- 다음 단계: TODO: 이재용이 `mock_public_*`의 벤치마크 탭 사용 여부와 `curated_contents` 폐기 여부를 확정한 뒤, 레거시 코드 전환 PR과 별도 destructive 삭제 PR을 승인한다.

- 모든 migration과 seed를 UTF-8로 읽고 SQL 구문 검사를 통과한다.
- 신규 public 테이블마다 RLS와 의도한 GRANT가 계약 테스트에 존재한다.
- 승인된 목시나리오 backfill의 계좌 합계, 위험자산 비율, 한도 판정, 자산군 비중이 이전 결과와 동일하다.
- 5단계 성향 코드와 현재 6개 질문 코드가 Python 모델·seed·DB CHECK에서 동일하다.
- 사용자 A가 사용자 B의 프로필·계좌·진단을 읽거나 변경할 수 없는지 검증한다.
- 수익률 계산은 현금흐름 전후 케이스를 포함한다.

### 원격

- migration history에 승인된 버전만 존재한다.
- RLS, role별 GRANT, 정책 predicate, FK, CHECK, unique index를 카탈로그에서 재검증한다.
- backfill 전후 승인된 목표 건수와 금액 합계가 일치한다.
- FastAPI를 통한 Auth 사용자 경로와 목시나리오 fallback을 각각 E2E 검증한다.
- `supabase db advisors` 또는 MCP advisors 결과의 보안·성능 경고를 검토한다.

## 12. 작업 상태표

| ID | 작업 | 상태 | 완료 조건 | 다음 행동 |
|---|---|---|---|---|
| DB-00 | BGE-M3 1024차원·HNSW 마이그레이션 | `REMOTE-APPLIED` | 원격 1024차원·HNSW·migration history 확인 | 적용 파일 수정 금지 |
| DB-01 | 사용자·성향·계좌 스키마 승인 | `REMOTE-APPLIED` | `user_profiles`, 현금흐름 포함, 커뮤니티 제외, 매핑 보류 계약이 원격 스키마에 반영 | 적용 파일 수정 금지 |
| DB-02 | Additive domain migration | `REMOTE-APPLIED` | `20260716001737`, 11개 테이블·RLS·정책·권한·행 수 재검증 | 적용 파일 수정 금지 |
| DB-02A | 성향 답변 복합 FK 인덱스 | `REMOTE-APPLIED` | `(option_id, question_id)` covering index·Advisor 미인덱스 FK 0건 | 적용 파일 수정 금지 |
| DB-03 | 공통 계좌 구조 backfill | `REMOTE-APPLIED` | 기존 6/13/26을 `pension_accounts`·snapshot·holding 구조로 이관하고 금액·엔진 결과 동등 | `20260720034015`; source/target 6·13/26→13/13/26, 금액 불일치 0, nullable 원금·ETF 코드 인덱스·RLS/GRANT 재검증 완료 |
| DB-03A | 생애주기 대표 고객·Auth 준비 | `REMOTE-APPLIED` | 시나리오 6·계좌 13·보유 26, synthetic demo Auth 사용자 6개 존재 | 데모 로그인 smoke는 다음 인증 가능 세션에서 재검증 |
| DB-03B | 원격 직접 수정 목데이터 Git 동기화 | `REMOTE-APPLIED` | `20260718131917`, 시나리오 설명 5건·대표 고객 납입액 5건 일치·재적용 시 무변경 확인 | 적용 파일 수정 금지 |
| DB-03C | 1만 명 공통 납입 계약·대표 6명 기준행/ETF 상세화 | `REMOTE-APPLIED` | `20260720044229`·`20260720044230`, 사용자 10,000·계좌 16,900·보유 79,381, 대표 legacy/common 6/13/86·6개 운용사, 납입한도·세율·잔액 불일치 0 | 적용 파일 수정 금지; 배포 보정 PR 머지 후 파일명·본문 고정 |
| DB-03D | 대표 6명 성향·후기·공개지표·짧은 로그인 ID | `REMOTE-APPLIED` | `20260721025143`, 성향 6·답변 66·지표 6, Auth 짧은 ID 6·로그인 후보 5·실로그인 6 성공 | 적용 파일 수정 금지; 공식 커뮤니티 랭킹과 실제 리뷰 정책은 DB-06에서 별도 결정 |
| DB-04 | 챗봇 Postgres scenario repository 연결 | `LOCAL-VERIFIED` | DB 우선·JSON fallback과 원격 채팅 저장·replay E2E 통과 | `/engine/mock-scenario` DB 전환 여부 별도 결정 |
| DB-04A | 사용자 연금계좌 repository·API 연결 | `LOCAL-VERIFIED` | 신규 공통 계좌 구조 조회·Auth 소유권·엔진 입력 변환 E2E | 실제 Supabase Bearer-token으로 `/me/pension-accounts`가 mock 계좌·보유를 반환함을 E2E 확인. 다음은 commit·push·PR |
| DB-05 | 기존 mock account tables 정리 | `BLOCKED` | 코드·SQL 참조 0, 별도 승인·복구 계획 | DB-04 안정화 전 삭제 금지 |
| DB-06 | 커뮤니티 리뷰 | `BLOCKED` | 포트폴리오 FK·RLS·신고·보존 정책 승인 | 핵심 계좌 연동 후 검토 |
| DB-07 | ETF 포트폴리오 유니버스 스키마·조회 연결 | `REMOTE-APPLIED` | `20260717054500`, 상품 2,507행·이력 217,833행·RLS/권한·120개 동등성·API E2E 확인 | 적용 파일 수정 금지, 다음 데이터 버전 적재 시 ready 전환 계약 유지 |
| DB-08 | 손상된 컬럼 설명 3건 교정 | `REMOTE-APPLIED` | `20260718154819`, COMMENT 3문 전용·실제 설명·불변식 재조회 | 적용 파일 수정 금지 |
| DB-09 | Auth 유출 비밀번호 보호 | `BLOCKED` | Security Advisor의 `auth_leaked_password_protection` WARN 제거 | Supabase Dashboard 또는 CLI 로그인 후 `password_hibp_enabled` 활성화·Advisor 재조회 |
| DB-10 | main 원격 DB 런타임 회귀 | `LOCAL-VERIFIED` | Auth/RLS·채팅 persist/replay·RAG·뉴스·공시·ETF·NAVER rollback-only SQL E2E 통과 | main 변경 시 재실행 |
| DB-11 | KRX 전체 ETF 일별 거래량 DB·API 연결 | `REMOTE-APPLIED` | `20260720080955`, 2026-07-14 전체 1,147행·원본 합계 동등성·RLS/GRANT·FastAPI 원격 E2E 확인 | 일일 갱신 자동화와 보존기간은 후속 결정 |
| DB-12 | ETF 테마 콘텐츠 검증·승인 RAG 연결 | `REMOTE-APPLIED` | `20260720091219`, `.4` 검토·근거 115/115건(`.3` 포함 총 230/230), 승인 문서 15개·활성 임베딩 청크 56/56건 | 적용 파일 수정 금지; 챗봇 화면 E2E·검토기한 만료 전 재검증 |
| DB-13 | 투자성향 진단 저장·조회 API | `REMOTE-APPLIED` | POST/GET·24개월 KST 정책·append-only 확인 이력·RLS·소유자 스코프·전체 회귀·원격 카탈로그 검증 통과 | `20260720154033_add_investment_profile_confirmations.sql` 적용 완료 |
| DB-13A | 로그인 투자자정보 확인서 통합 설문 | `REMOTE-APPLIED` | `20260722020126`, 활성 세트 1개·17문항·76선택지, 기존 세트 retire, 0~7점 제약·복수선택 답변 제약·RLS/클라이언트 권한 재검증 | 원격 적용 MCP 버전에 맞춰 로컬 파일명을 `20260722020126`으로 유지; 적용 파일 수정 금지 |
| DB-14 | KIS ETF 구성종목 신뢰성 보강 | `LOCAL-VERIFIED` | 국내주식형 장중 수집·임시 빈 응답 최대 3회 재개, 마지막 정상 스냅샷 보존, 단일 연결 풀, 해외 KIS 부분 스냅샷 비노출, 선택 종목 재수집 및 첫 질문 TOP3 조회까지 로컬·원격 데이터 검증 | 코드 배포·국내 335개 장중 백필 전; KIS 미지원 614개는 KRX PDF·운용사 보조 소스 계약 필요 |
| DB-15 | 레거시 목계좌 테이블 퇴역 백업·쓰기 전환 | `LOCAL-VERIFIED` | 읽기 전용 JSON·SHA-256 백업, 공통 계좌 동등성 확인, seed·데모 적재·생성기의 공통 계좌 직접 쓰기 | 복구 절차와 로컬 reset·원격 E2E를 재검증한 뒤 별도 파괴적 migration 검토 |
| DB-16 | 사용자 리밸런싱 점검 알림 설정·API | `REMOTE-APPLIED` | `20260723071528`, additive 테이블·RLS 활성화·브라우저 권한 회수·service_role 권한 재검증 | PR 병합·백엔드 배포 후 인증 API E2E, 이후 프론트 알림 카드 연결 |

## 13. 미결정 사항

- DB 작업의 실명 담당자와 폴더 소유권: `TODO: 확인 필요`.
- 사용자 프로필 명칭은 `user_profiles`로 확정.
- 실제 계좌 연동 방식과 provider import 원천: `TODO: 확인 필요`. 현재 사용자 계좌는 목데이터만 허용된다.
- 3단계 목시나리오 성향과 5단계 진단 성향 매핑: 팀 승인 전 미구현.
- `account_cash_flows`는 과거 수익률 계산의 현금흐름 입력을 위해 첫 스키마에 포함.
- 상품 마스터를 제공할 공식 product-level API: 현재 FSS 데이터는 provider-level이므로 별도 확인 필요.
- 커뮤니티 리뷰의 실제 사용자 대상 공개 시점과 보존·신고 정책: 후속 결정.

## 14. 작업 로그

### 2026-07-23 16:16 KST — 리밸런싱 점검 알림 저장·API (REMOTE-APPLIED)

- 작업자/브랜치/커밋: Codex(김태형) / `codex/김태형/rebalancing-reminder-notifications` / 현재 `HEAD`.
- 변경 내용: 신규 migration `20260723071528_add_rebalancing_reminder_preferences.sql`은 사용자별 동의 상태·동의 시각·마지막 점검 완료 시각만 보관한다. RLS를 활성화하고 브라우저 역할 권한을 회수해 FastAPI의 인증 소유자 경로만 사용한다.
- 결정 및 근거: 점검 주기와 허용 이탈폭은 DB에 복제하지 않고 기존 순수 엔진 `rebalancing_cadence()`에서 조회한다. 화면 열람은 점검 완료로 기록하지 않으며, 사용자가 `POST /me/rebalancing-reminder/complete`를 호출할 때만 다음 점검일이 갱신된다.
- 로컬 검증과 실제 결과: 관련 테스트 `uv run pytest tests/test_rebalancing_reminder_repository.py tests/test_rebalancing_reminder_api.py tests/test_schema_contract.py` 43 passed, 전체 `uv run pytest` 1118 passed·1 skipped, 전체 `uv run ruff check .`, `git diff --check` 통과. 브라우저 `PUT` 사전요청 CORS 회귀도 포함했다.
- 원격 적용 여부와 migration version: 이재용 승인 후 첫 적용은 원격 `extensions.moddatetime()` 부재로 원자적 실패했고 테이블·migration history 모두 미생성임을 재조회했다. 트리거 의존을 제거한 동일 additive SQL을 재적용해 `20260723071528_add_rebalancing_reminder_preferences`가 원격에 기록됐다.
- 원격 재검증: 테이블 RLS 활성화, 정책 0개(서버 전용 deny-by-default), `anon`·`authenticated` 권한 0개, `service_role` 권한만 존재함을 확인했다. Security Advisor의 새 테이블 INFO는 이 의도된 서버 전용 구성과 일치한다.
- 다음 작업: PR 병합·백엔드 배포 뒤 실제 Bearer-token API E2E를 확인한다. 프론트 알림 카드는 병합된 계약을 기준으로 별도 화면 연결 작업으로 진행한다.

### 2026-07-23 KST — benchmark schema pilot phase 1 (REMOTE-APPLIED)

- Migration `20260723045228_move_benchmark_tables_to_schema` created schema `benchmark`, moved the three benchmark tables, and retained public `security_invoker` compatibility views for the deployed read path.
- Remote verification: benchmark table counts are users 10,000, accounts 16,900, holdings 79,381; public compatibility views return the identical counts.
- `public.table_domain_catalog` intentionally no longer lists the three tables because it catalogs only `public` base tables; the benchmark domain tag now remains on the moved table objects.
- Phase 2 code commit uses explicit `benchmark.` references for the repository, loader, demo scripts, seed, and generated demo migration. Direct repository verification returned 10,000 users, 16,900 accounts, and 79,381 holdings.
- Do not remove public compatibility views until the Phase 2 code is merged and deployed. Phase 3 requires a new migration and separate approval.

### 2026-07-23 13:45 KST 테이블 도메인·라이프사이클 태그 + 카탈로그 뷰 (REMOTE-APPLIED)

- 작업자/브랜치: Codex(이재용) / `codex/이재용/db-domain-catalog`(origin/main `e4e2878` 기준 워크트리).
- 배경: public 한 스키마에 56개 테이블이 누적됐고 그중 41개는 테이블 코멘트가
  전혀 없어 관리자가 라이브·보존·예약·dead를 식별할 수 없었다. 삭제가 아니라
  경계 식별로 먼저 정리한다(비파괴 B단계).
- 변경: 신규 `20260723043507_annotate_table_domains.sql` 1건(원격 적용 시 MCP가
  부여한 실행 시각 버전 `20260723043507`에 로컬 파일명을 맞췄다. SQL 내용은
  로컬 검증본과 동일하며 migration repair는 하지 않았다).
  - 코멘트가 없던 41개 테이블에만 `'[<domain>/<lifecycle>] 설명'` 태그를 단다.
    이미 코멘트가 있던 15개 테이블은 재정의하지 않는다.
  - domain 11종: `source`, `institution`, `asset`, `mock_scenario`,
    `mock_public`, `benchmark`, `demo_customer`, `engine_audit`, `rag_news`,
    `chat`, `user_pension`. lifecycle 4종: `live`, `retained`, `reserved`, `dead`.
  - `mock_public_*` 3개와 `curated_contents`는 `dead`, `mock_accounts`·
    `mock_holdings`는 `retained`, `account_cash_flows`·`financial_products`는
    `reserved`로 표기했다(표기만이며 삭제·이관은 별도 승인 건).
  - 관리자 식별용 조회 뷰 `public.table_domain_catalog`(security_invoker=true)를
    추가하고 브라우저 권한을 회수한 뒤 `service_role`에만 `select`를 부여했다.
- 비변경: 데이터·인덱스·RLS·GRANT(테이블)·스키마·seed.sql은 바꾸지 않았다.
  seed.sql은 순수 데이터 insert만 있어 `db reset`이 마이그레이션의 코멘트·뷰를
  먼저 적용하므로 수정 불필요.
- 검증(로컬): `pglast` 파싱 OK(45 statements). `uv run pytest
  tests/test_schema_contract.py tests/test_embedded_sql.py` 35 passed.
  신규 계약 테스트 `test_table_domain_annotations_are_additive_and_complete`는
  additive-only(alter/create table/drop/insert 금지), 정확히 41개 태그,
  허용 domain·lifecycle 형식, 기존 15개 미재정의, 카탈로그 뷰 권한을 강제한다.
  `uv run ruff check` clean, `git diff --check` 오류 0.
- 검증(원격, 적용 직후 재조회): `apply_migration` success=true.
  `table_domain_catalog`로 태그 41·미태그 13(기존 코멘트 테이블 수와 일치)을
  확인했다. public 테이블 54/RLS 54는 적용 전후 동일(비파괴). 뷰는
  `security_invoker=true`, GRANT는 `service_role`만(anon·authenticated 없음).
  원격 버전 `20260723043507_annotate_table_domains` 이력 등재 확인.
- 다음(A단계, 승인 대기): 위 domain 태그를 물리 스키마 경계로 분리한다.
  파일럿 1순위는 `benchmark`(3개 테이블, `service_role` 전용, 코드 참조 소수).

### 2026-07-23 11:40 KST ETF 비용 마스터·API 운영 완료 (REMOTE-APPLIED)

- 작업자/브랜치: Codex(김태형) / `codex/김태형/etf-cost-ops-completion`.
- 2026-07-23 비용 마스터를 신규 생성했다. 통합 861개, DC 823개, IRP 823개,
  연금저축 861개이며 이력 누락 0, 검증비용 861, KOFIA TER 861, 운용사 861,
  매매·중개수수료 진단 861, 추적오차 진단 861건이다. KIS 비용 대체와 비용 미확인은
  각각 0건이다.
- KOFIA TER와 보수합계·기타비용의 원문 반올림 절대차를 별도 보존했다. 최대 0.008%p,
  파서 허용범위 0.01%p 초과 0건이다. 매매·중개수수료와 독립 추적비용의 계획수익률
  포함 플래그는 모두 false이며 원격 포함 건수도 각각 0건이다.
- 원격 적재: 기존 ready 버전을 보존하고 `etf_dataset_versions.id=4`,
  `as_of=2026-07-23`, `source_sha256=4bbeaa621d99440a747453f2a0c1472cadcffbce2ac77fc6c24421338d56fff2`로
  상품 2,507행·총수익 이력 1,207,952행을 적재했다. 계좌별 운용사·검증비용·매매중개·
  추적오차 진단 커버리지는 각 상품 수와 동일하고 중복 차감 플래그는 0건이다.
- FastAPI 원격 DB E2E: `POST /engine/educational-portfolio`가 200을 반환했다. 연금저축
  위험중립 표본의 선택 ETF 6개 모두 운용사·매매중개·추적오차 진단값을 반환했고,
  `brokerage_commission_included=false`, `tracking_cost_included=false`, 비용 기준일
  2026-07-23, 비중가중 연간비용 0.0975%를 확인했다.
- Advisor: 신규 DDL은 없다. 기존 서버 전용 테이블의 `rls_enabled_no_policy` INFO와
  [유출 비밀번호 보호 비활성화 WARN](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)은
  그대로이며 이번 데이터 적재로 새 보안 경고는 발생하지 않았다.
- 검증: 관련 회귀 31 passed, 최신 main 병합 후 전체 `1068 passed, 1 skipped`, Ruff와
  `git diff --check`가 통과했다. GitHub CI는 PR 단계에서 최종 확인한다.

### 2026-07-22 KST KIS ETF 구성종목 P0 수집·표시 보강

- 수집 범위를 최신 ready 유니버스의 국내주식형(`equity`·`south_korea`)으로 제한하고, 월요일 11:30 KST 전체 실행 뒤 임시 빈 응답만 최대 3회 재개하도록 변경했다. 부분 결과는 `failed`·HTTP 의미코드 `207`·`outcome=partial`로 기록하며 프로세스도 실패 코드로 종료한다.
- 수집기는 최대 1개 연결의 전용 풀을 재사용하고, API 공용 풀은 원격 세션 한도 15를 전부 점유하지 않도록 최대 5개로 축소했다.
- 챗봇 조회기는 최신 ready 상품 분류에서 해외주식형으로 확인된 KIS 스냅샷을 반환하지 않는다. 최초 상품 특징 경로에서도 해외형 KIS 구성종목을 비우며, 첫 질문에서 구성종목을 요청하면 후보 순위를 바꾸지 않고 선정된 최대 3개 코드를 한 번에 조회한다.
- 원격 읽기 검증: 최신 version 2에서 새 수집 대상은 국내주식형 335개다. 동일 조회기로 `069500`·`381180`·`0020H0`를 함께 요청했을 때 국내형 `069500`만 반환되고 TOP3 3행이 유지됐다.
- 검증: 전체 Python `999 passed, 1 skipped`, `uv run ruff check .`, `git diff --check` 통과. 신규 migration과 원격 쓰기·백필은 수행하지 않았다. 해외형 운용사 공식 보유내역 adapter와 출처별 기준일 계약은 후속 작업이다.
### 2026-07-22 KST 레거시 목계좌 쓰기 경로 공통 계좌 전환

- 작업자/브랜치: Codex / `db/jyleo2k2/legacy-account-write-cutover`.
- 변경: `supabase/seed.sql`의 대표 6명 계좌·보유 초기화는 `pension_accounts`·`account_snapshots`·`account_holding_snapshots`에 직접 13·13·86행을 멱등 적재한다. `scripts/render_demo_customer_sql.py`는 더 이상 적용 완료 migration을 재생성하지 않고 공통 계좌 seed만 생성한다. `scripts/load_benchmark_mock_data.py`도 레거시 계좌 표 갱신을 중단했다.
- 보존: 역사 migration과 read-only 백업 도구는 복구 근거로 그대로 유지한다. 이번 범위에서는 `mock_accounts`·`mock_holdings` 삭제나 원격 DB 쓰기를 수행하지 않았다.
- 검증: seed PostgreSQL 파싱 통과, SQL 계약 32 passed, 전체 `uv run pytest` 1022 passed·1 skipped, `uv run ruff check .`, `git diff --check` 통과. seed·생성기·벤치마크 적재기에서 `public.mock_accounts`·`public.mock_holdings` 쓰기 참조는 0건이다.
- 다음: 백업 복원 리허설·로컬 reset과 Auth/RLS 원격 E2E를 재검증하고, 이재용 승인 후에만 별도 파괴적 migration으로 테이블을 제거한다.

### 2026-07-22 KST 레거시 목계좌 퇴역 백업 준비

- 작업 브랜치/워크트리: `db/retire-legacy-mock-tables` / `C:\dev\finance-project-1-db-legacy-cleanup`.
- 코드 전환 기준: 챗봇 시나리오·로그인 사용자 요약은 공통 `pension_accounts`·`account_snapshots`·`account_holding_snapshots`를 읽도록 전환된 커밋 `bf4c848`을 기반으로 한다.
- 백업: `scripts/backup_legacy_mock_accounts.py`가 repeatable-read·read-only 트랜잭션에서 `mock_scenarios`·`mock_accounts`·`mock_holdings`를 정렬 JSON으로 내보내고 SHA-256 manifest를 생성한다. 출력은 Git 제외 `output/legacy_mock_account_backups/`에만 쓴다.
- 실제 읽기 검증: 2026-07-22 KST에 공통 계좌 동등성 검사를 통과한 뒤 시나리오 6개·계좌 13개·보유 86개·총 평가액 520,290,000원 백업을 생성하고, DB 재접속 없이 SHA-256 검증을 다시 통과했다. 원격 DB 쓰기·migration 적용은 수행하지 않았다.
- 삭제 전 남은 의존성: `supabase/seed.sql`, `scripts/load_benchmark_mock_data.py`, `scripts/render_demo_customer_sql.py`, 일부 데모 문서가 레거시 테이블을 아직 생성·갱신·설명한다. 이를 공통 계좌 구조로 전환하고 로컬 reset/원격 E2E·복구 절차를 검증하기 전에는 `mock_holdings`·`mock_accounts`를 삭제하지 않는다.
- 검증: 백업 도구 단위 테스트 3건·Ruff 통과. 챗봇 공통 구조 전환 기준 전체 회귀는 `981 passed, 1 skipped`.

### 2026-07-22 KST 로그인 투자자정보 확인서 통합 설문 원격 적용

- 작업자/브랜치: Codex / `codex/login-survey-db`.
- 시작 상태: 원격 활성 설문세트 1개·6문항·30선택지, 사용자 투자성향 평가·답변 행은 각각 0건이었다.
- 원격 적용: MCP `apply_migration`으로 로그인 설문 통합 SQL을 적용했다. MCP가 실제 원격 버전 `20260722020126_replace_profile_question_set_with_login_union`을 부여했으므로, 로컬 migration 파일도 같은 버전으로 이름을 맞췄다. `migration repair`는 사용하지 않았다.
- 원격 재검증: 활성 세트 1개·retired 세트 1개, 활성 17문항·76선택지, 점수/답변 점수 CHECK 모두 `0..7`, 답변 유니크 제약은 `(assessment_id, question_id, option_id)`, 관련 public 5테이블 RLS 5/5, `anon`·`authenticated` 테이블 GRANT 0개를 확인했다.
- Advisor: 신규 경고는 없었다. `RLS Enabled No Policy` INFO는 서버 전용 reference 테이블의 기존 deny-by-default 구성이고, `auth_leaked_password_protection` WARN은 기존 미해결 항목(DB-09)이다.
- 로컬 검증: `uv run pytest tests/test_demo_user_context.py tests/test_profile.py tests/test_investment_profile_api.py tests/test_schema_contract.py tests/test_embedded_sql.py` 73 passed, `uv run ruff check ...` 통과, 프론트 `npm test` 53 passed·`npm run build` 통과.

### 2026-07-21 KST KIS ETF 구성종목 빈 응답 신뢰성 보강

- 원인 재확인: 기존 최신 스냅샷 861개 중 정상 상세 227개·빈 상세 634개였고, 빈 응답 634개 모두 KIS 성공 코드였다. 이 중 633개는 `output1.etf_cnfg_issu_cnt`가 양수인데 `output2`만 비어 있어 정상 무구성 상품이 아니라 상세 누락이었다.
- 로컬 변경: 양수 구성종목 수+빈 상세를 임시 누락으로 판정해 최대 3회 재시도하고, 소진 시 run을 `partial`로 표시하며 CLI를 실패 코드로 종료한다. 당일 재개는 성공 및 명시적 0건만 건너뛰며 임시 빈 응답은 다시 수집한다. 조회기는 최신 레코드가 아니라 마지막 `succeeded`·양수 스냅샷만 사용한다. 장애 종목만 재검증하는 반복형 `--isu-code`도 추가했다.
- 원격 데이터 검증: 오늘 임시 빈 종목 5개 소규모 실행은 5개 모두 반복 누락으로 정확히 차단됐다. 테마 답변 후보 중 빈 종목 31개를 지정 재수집해 20개가 정상 TOP3를 회복했고 11개는 네 번 호출 후에도 계속 비었다. 최신 전체 상태는 861개 중 정상 247개·빈 614개, 최신 정상 스냅샷의 조회용 구성종목 행은 690개다. 기존 행 삭제·수정과 migration 적용은 없고 append-only 스냅샷만 추가했다.
- 남은 11개: `0023A0`, `0048K0`, `0051G0`, `160580`, `352540`, `371460`, `437080`, `439860`, `474800`, `487230`, `498270`. 신규 영문혼합 코드뿐 아니라 해외 주식·리츠·채권·원자재가 섞여 있어 KIS 상품군 지원 공백으로 분류한다.
- 검증: 신규·관련 테스트 9 passed 후 전체 `uv run pytest` 944 passed·1 skipped, `uv run ruff check .`, `git diff --check`가 통과했다. `--isu-code` 추가 후 최종 전체 회귀는 아래 최신 검증 결과로 다시 기록한다.
- 원격 migration: 없음. KRX PDF·운용사 공시를 보조 소스로 저장하려면 출처 구분·기준일·원문 SHA-256 계약과 additive migration을 먼저 설계하고 이재용의 명시 승인을 받아야 한다.

### 2026-07-21 KST KIS ETF 구성종목 TOP3 원격 스냅샷

- 승인: 사용자 전달에 따라 이호연 조장·이재용 총괄의 원격 적재 및 주간 갱신 승인 범위에서 수행했다.
- 적용: `add_etf_component_snapshots` migration을 Supabase MCP로 적용했다. `etf_component_snapshots`(원문 JSON·SHA-256·수집시각)와 `etf_component_snapshot_items`(비중 TOP3)를 추가하고 KIS 출처를 등록했다.
- 원격 검증: 두 테이블의 RLS 활성화와 `anon`·`authenticated` 권한 회수, `service_role` 전용 권한을 확인했다. 최신 ready ETF 유니버스는 고유 ETF 861개다.
- 초기 적재: 실제 KIS 호출 3개는 성공(성공 2·빈 목록 1, TOP3 행 6개)했다. 로컬 10분 실행 제한으로 전체 실행이 중단된 뒤, 당일 KST 스냅샷을 건너뛰는 재개 모드로 남은 ETF 백필을 백그라운드 실행 중이다. 중단된 run은 `failed`로 정리했다.
- 검증: 관련 SQL 계약·repository·챗봇 테스트 57 passed, 전체 `uv run pytest` 933 passed·1 skipped, `uv run ruff check .`·`git diff --check` 통과.
- 다음: 백필 종료 후 861개 수집 결과·TOP3 행 수·실패 수 재조회, GitHub Actions 주간 workflow 배포 후 첫 scheduled run 확인.

### 2026-07-21 KST 대표 6명 전체 공개 계약·짧은 로그인 ID 원격 적용

- 로그인 계약: tracked manifest를 v4로 올려 사용자가 입력하는 `login_id`를 `junho46` 같은 짧은 값으로 바꾸고, Supabase Auth 내부 식별자는 `auth_email`로 분리했다. 프론트는 짧은 ID에 데모 도메인을 붙여 `signInWithPassword`를 호출한다.
- Auth 원격 검증: 서버 관리 `app_metadata.demo_login_id`에 짧은 ID 6개를 저장했다. 승인된 임시 고정 비밀번호를 다시 동기화한 뒤 6계정 모두 실제 로그인에 성공했고, 로그인 후보는 5명이다. 비밀번호와 내부 Auth 이메일은 로그에 출력하지 않았다.
- DB 원격 적용: `20260721025143_store_demo_customer_profiles_and_metrics.sql`을 적용했다. `demo_investor_profiles` 6행, `demo_investor_profile_answers` 66행, `demo_public_portfolio_metrics` 6행을 저장했다. 기존 고객 6·계좌 13·ETF 보유 86·금융 컨텍스트 6과 scenario FK로 연결된다.
- 보안: 신규 3개 테이블 모두 RLS 활성화, `anon`·`authenticated` SELECT 없음, `service_role` SELECT 있음으로 재조회했다. 과거 수익률의 미래예측/공식랭킹 플래그와 좋아요의 비합성/성과기반 플래그 위반은 모두 0건이다.
- Advisor: 신규 서버 전용 테이블 3개의 deny-by-default `rls_enabled_no_policy` INFO는 의도한 결과이며 성능 신규 경고는 없다. 기존 `auth_leaked_password_protection` WARN은 임시 약한 데모 비밀번호 정책 때문에 유지한다.
- 적용 복구 기록: 첫 적용은 공격투자형 손실감내 답변의 7점을 5점 상한으로 잘못 제한해 실패했으며 트랜잭션 전체가 롤백돼 테이블·migration 이력이 남지 않았다. 문항 실제 최대값에 맞춰 0~7점으로 수정한 뒤 재적용했다.
- 범위 경계: 이번 테이블은 대표 6명의 서버 관리 시연 목데이터 저장이다. 실제 사용자 리뷰·신고·보존 정책과 공식 TWR/MWR 랭킹은 포함하지 않으므로 `DB-06`은 계속 `BLOCKED`다.
- 검증: 관련 15건, 전체 Python 929 passed·1 skipped, 최신 main 프론트 39건, 프로덕션 빌드, 변경 Python Ruff, migration 생성 동등성, `git diff --check`를 통과했다.

### 2026-07-21 KST 대표 시나리오 공개 포트폴리오 과거 수익률·좋아요 지표

- 요청 범위: 시연 로그인 고객이 다른 대표 고객의 공개 포트폴리오에서 동일 기간 과거 수익률과 추천(좋아요) 수를 비교할 수 있도록 로컬 표시 계약을 추가했다.
- 과거 수익률: `data/mock/accounts.csv`의 2025-01-01~2025-12-31 계좌별 과거 12개월 목수익률을 계좌 잔액으로 가중했다. 계산은 결정론적 생성기에서만 수행하며 결과는 각각 7.72%, 11.20%, 11.16%, 0.74%, 12.79%, 4.69%다. 미래 예측이 아니며 공식 커뮤니티 순위 지표로 사용하지 않는다.
- 좋아요: 2026-07-21 기준 126, 284, 173, 412, 358, 97건을 시연용 합성 참여지표로 배정했다. 과거 수익률과 무관하고 성과 기반 추천으로 해석하지 않는다.
- 로컬 계약: `data/mock/demo_public_portfolio_metrics.json`을 SSOT로 두고 생성기·FastAPI 영웅 고객 응답·프론트 표시·Word 보고서가 같은 값을 사용한다. 수익률 기간·계산 기준·목데이터/합성 여부·출처 칩도 함께 전달한다.
- 원격 적용: migration·테이블·RLS·GRANT·원격 데이터 변경 없음. 공식 TWR/MWR 랭킹 공식, 실제 사용자 공개 범위, 신고·보존 정책이 미확정이므로 `DB-06`은 계속 `BLOCKED`다. 2026년 7월 Supabase 변경사항을 확인했으며 신규 public 테이블을 만들지 않아 Data API 권한 보정 대상도 없다.
- 검증: 지표 생성기·API·성향 관련 6건, 전체 Python 927 passed·1 skipped, 프론트 29건, 프로덕션 빌드, 변경 Python Ruff, `git diff --check`를 통과했다. Word는 압축 무결성·51개 표·6명 자격증명·여섯 수익률/좋아요·페이지 설정을 구조 검증했다.

### 2026-07-21 KST 대표 시나리오 고객 임시 고정 비밀번호 적용

- 요청 범위: 기존의 강한 무작위 비밀번호 생성·교체 로직은 유지하고, 발표·시연 기간에만 대표 고객 6명의 비밀번호를 고정했다. Supabase Auth 설정의 최소 길이 6자를 준수하기 위해 요청한 4자 값을 같은 문자 6자로 확장했다.
- 원격 적용: migration·스키마 변경 없이 서버 전용 Admin API로 Auth 사용자 6명의 비밀번호를 교체했다. 같은 프로비저닝 실행에서 6개 계정 모두 실제 로그인에 성공했으며, 금융 컨텍스트도 기존 계약대로 동기화됐다.
- 보안 경계: 실제 자격증명 JSON과 아이디·비밀번호 포함 Word 보고서는 Git 제외 `secrets/`에만 보관한다. 값 자체는 이 문서·로그·테스트 출력에 기록하지 않는다. 공개 배포 전에는 기존 `provision_demo_auth_users.py --rotate-existing` 경로로 강한 무작위 비밀번호를 다시 발급해야 한다.
- 검증: 데모 Auth 단위 테스트 7건 통과. Security Advisor의 기존 `auth_leaked_password_protection` 비활성화 경고는 이번 임시 데모 정책상 유지했다.

### 2026-07-21 KST 투자성향 확인 이력 migration 원격 적용

- 승인: 이재용이 `PR #107` migration 원격 적용을 명시 승인했다.
- 적용: `add_investment_profile_confirmations`를 Supabase MCP로 적용했다. 원격 적용 버전은 실행 시각 기준 `20260720154033`이며, 이력을 repair하지 않고 로컬 파일명을 같은 버전으로 맞춘다.
- 원격 검증: RLS 활성화, 소유자 SELECT/INSERT 정책 2개, assessment/owner FK·1:1 unique·모순 토글 CHECK, owner/confirmed 인덱스, `anon` SELECT와 `authenticated` INSERT 권한 없음, `service_role` INSERT 권한 있음.
- Advisor: 신규 테이블 관련 경고 없음. 기존 `auth_leaked_password_protection` WARN과 서버 전용 테이블의 RLS deny-by-default INFO는 유지된다.

### 2026-07-20 23:50 KST 투자성향 진단 저장·조회 API

- 작업자/브랜치: Codex / `profile/assessment-api` / `origin/main` `76d286e` 기반 별도 worktree.
- 원격 읽기 재검증: 프로젝트 `ACTIVE_HEALTHY`, 적용 migration 22개, profile question set/question/option은 1/6/30, assessment/answer는 0/0, 만료일·두 확인 토글 컬럼은 기존 public 스키마에 없음.
- 로컬 변경: API 전용 wrapper POST/GET, 기존 순수 엔진 결과를 저장하는 소유자 스코프 repository, KST 24개월 유효기간 정책, append-only `investment_profile_confirmations` migration·RLS·소유자 인덱스, REST 계약 문서와 테스트를 추가했다.
- 원격 적용: 후속 승인으로 `20260720154033_add_investment_profile_confirmations.sql` 적용 완료.
- Advisor: 기존 `auth_leaked_password_protection` WARN과 서버 전용 테이블의 RLS deny-by-default INFO를 재확인했다. 이번 신규 테이블은 RLS SELECT/INSERT 소유자 정책과 authenticated 권한 회수로 별도 노출하지 않는다.
- 검증: 관련 정책·API·repository·SQL 계약 37 passed, 전체 `uv run pytest` 921 passed·1 skipped, `uv run ruff check .`·`git diff --check` 통과.
- 다음: commit·push·Draft PR. 원격 migration 적용은 PR과 별도로 이재용 승인 요청.

### 2026-07-20 22:07 KST ETF 테마 성과 관찰 요인 구체화

- 23개 테마의 `performance_drivers`를 각각 3개로 통일하고, 모든 항목을
  `요인명: 왜 주문·매출·비용·가동률 등 테마 성과와 연결되는지` 형식으로
  구체화한 카탈로그 `2026-07-20.4`를 반영했다.
- 승인 지식 문서를 멱등 재적재했다. 첫 실행은 첫 문서 upsert 후 Windows
  CP949 출력 오류로 종료됐으나, UTF-8 모드로 전체 재실행해 완료했다.
  변경된 청크 3개를 BGE-M3 1024차원으로 재임베딩했다.
- `.4`의 23개 테마 × 5개 질문 유형 115건을 모두 `verified`로 적재하고
  승인 공식 URL·활성 RAG 청크 근거 115건과 연결했다. 기존 `.3` 장부는
  감사 이력으로 유지해 원격 총계는 검토 230건·근거 230건이다.
- 원격 재조회 결과 `.4` 검토 115/115·근거 115건, 승인 문서 15개,
  활성 청크 56개·임베딩 56개를 확인했다. migration·repair·reset은
  수행하지 않았다.
- 검증: 관련 백엔드 217건, 전체 백엔드 855 passed·1 skipped, 프론트
  28건, SQL 계약 27건, 프로덕션 빌드, Ruff, `git diff --check`가 통과했다.
  실제 챗봇 화면에서 성과 요인 3개와 각각의 인과 설명을 확인했고, 성과
  요인·장단점 문단 모두 CSS `10pt`가 계산값 `13.3333px`로 적용됨을
  확인했다.

### 2026-07-20 18:43 KST 신규작업브랜치 main 통합

- `신규작업브랜치`의 ETF 테마 챗봇·검증 장부 변경을 보존한 채
  `origin/main` `b795763`을 병합했다. 충돌은 이 문서 한 파일에서만 발생했고,
  KRX 일별시장 `20260720080955`와 ETF 테마 검증 `20260720091219`의 원격 적용
  상태·행 수·작업 로그를 모두 유지하는 의미 병합으로 해결했다.
- 병합 커밋은 `2c51ea2`, 프론트 테스트의 중복 안내 문구 단언 보정은
  `d7d8760`이다. 병합 전 ETF 테마 커밋 `71e896d`는 복구 태그
  `archive/20260720-before-etf-category-main-sync`로 보존했다.
- 검증: 승인 지식 manifest 문서 15개·청크 56개 유효, 관련 백엔드 281건
  통과, 전체 백엔드 852 passed·1 skipped, 프론트 20건 통과, 프로덕션 빌드,
  Ruff, `git diff --check` 통과. `origin/main`은 현재 HEAD의 조상이며 재병합
  시 충돌이 없음을 확인했다.
- 원격 Supabase 쓰기·migration 적용·repair·reset은 수행하지 않았다.

### 2026-07-20 17:12 KST KRX 전체 ETF 일별 거래량 연결

- 신규 migration `20260720080955_add_krx_etf_daily_market_snapshots.sql`과
  KRX 원본 정규화·ingestion run·멱등 upsert 적재기를 추가했다. 원본 JSON은
  파일에 유지하고 DB에는 조회용 정규화 값과 출처 연결만 저장한다.
- FastAPI에 `GET /market/etfs`와
  `GET /market/etfs/{isu_code}/volume-history`를 추가했다. 요청일 이하 최신
  거래일을 사용하며 거래량·거래대금·순자산 정렬을 화이트리스트로 제한한다.
- 실제 `20260714.json`은 수신 1,147행·정규화 1,147행·스킵 0행이었다.
  숫자 전용 코드 가정이 틀렸음을 확인해 `0184E0` 같은 대문자 영숫자 6자리
  코드 280개를 DB·적재기·API 전체에서 허용했다. 거래량 0인 13개도 유지한다.
- 원격 적용: 이재용 승인에 따라 `20260720080955`를 적용하고 2026-07-14
  1,147행을 적재했다. 원본과 DB의 종목 수·거래량 합계 18,155,107,333좌·
  거래대금 합계 46,862,470,547,267원이 일치한다. 테이블은 516,096바이트이며
  전체 DB는 111,660,179바이트다.
- 검증: 최신 `main` 기준 전체 `pytest` 834 passed·1 skipped, `ruff check .`,
  `git diff --check` 통과. RLS 44/44, `anon` 0·`authenticated` 5·
  `service_role` 44개 테이블, 신규 테이블 인덱스 3개를 확인했다.
  `/market/etfs`는 HTTP 200·1,147건, `069500` 이력 API는 HTTP 200·1건이다.
- Advisor: 신규 보안 WARN은 없고 서버 전용 테이블의 의도된
  `RLS Enabled No Policy` INFO와 초기 미사용 인덱스 INFO만 추가됐다. 기존
  `auth_leaked_password_protection` WARN은 DB-09 범위로 유지한다.

### 2026-07-20 16:36 KST

- 작업자/브랜치/기준: Codex / `codex/demo-candidate-tax-year-fix` / `origin/main` `913c96b`.
- 결정: 대표 시나리오 고객 6명과 Auth 계정은 모두 유지한다. 시연 로그인 후보는 1~5번 5명이며 `pension_payout_transition`은 후보에서 제외하되 타 고객 포트폴리오 데이터로는 계속 사용할 수 있다. 추적 manifest와 서버 관리 Auth `app_metadata`의 `is_demo_login_candidate`를 기준으로 삼는다.
- 원인·수정: 원격 `demo_user_financial_context.tax_year=2026` 제약과 엔진 지원연도는 올바르다. `scripts/provision_demo_auth_users.py`, SQL 생성기, 로컬 seed가 2025 벤치마크 연도를 주입한 경로를 2026 고정 투영으로 통일했으며 과거 적용 migration과 제약은 수정하지 않았다.
- 원격 적용: migration 추가·적용 없음. 대화에 노출된 데모 비밀번호 6개를 다시 교체하고 Auth 사용자 6명의 후보 메타데이터를 갱신했다. 같은 실행에서 금융 컨텍스트 6행을 upsert한 뒤 행 수 6, 최소·최대 `tax_year=2026`, 새 비밀번호 로그인 6건, 후보 플래그 5 true/1 false를 검증했다. 자격증명은 Git 제외 `secrets/`에만 보관하고 출력하지 않았다.
- 로컬 검증: 관련 39개 테스트 통과, 전체 `825 passed, 1 skipped`, `uv run ruff check .` 통과, 프론트 `npm.cmd run build` 통과, `git diff --check` 통과.
- 남은 작업: 브랜치 커밋·PR·이재용 머지 승인. 원격 migration history 변화는 없다.

### 2026-07-20 ETF 테마 콘텐츠 검증 통합

- 김태형의 엔진 산식 변경 합의와 이재용의 원격 적용 승인을 전달받았다. 테마 ETF 후보 순위는 거래대금 중앙값 내림차순, 동률 시 총보수 오름차순으로 변경했다. 두 값이 없는 상품은 순위에서 제외한다.
- 원격 migration `20260720091219_add_etf_theme_content_verification.sql`은 테마·질문 유형별 payload SHA-256 검토 장부와 승인 지식 문서·청크·공식 URL 근거 연결을 추가한다.
- 두 신규 테이블은 RLS를 활성화하고 `public`·`anon`·`authenticated` 권한을 회수하며 `service_role`만 접근한다.
- 런타임은 `verified` 상태, 해시, 검토기한, 승인 지식 metadata, 활성 청크와 공식 URL이 모두 유효할 때만 해당 문구를 검증 완료로 표시한다. DB 미적용·장애·불일치는 기존 초안 표기를 유지한다.
- 승인 RAG는 문서 15개·활성 청크 56개이며 전부 BGE-M3 1024차원 임베딩을 보유한다. ETF 테마 승인 문서는 공식 URL 27개와 고유 테마 표식 23개를 포함한다.
- 카탈로그 `2026-07-20.3`의 `overview`, `representative_companies`, `investment_considerations`, `performance_drivers`, `risks`가 각각 23건으로 총 115건이고, 검증 해시·근거 링크·활성 청크가 모두 115/115 일치한다. 최소 재검토일은 2027-01-16이다.
- 원격 챗봇 E2E에서 조선 테마 개요가 `verified_knowledge` 출처 1건을 반환하고 `공식 문서 검증 전 초안` 한계를 제거했다. 후속 버튼은 `테마 대표기업`, `테마 장단점`, `테마 ETF상품` 3개다.
- 검증: 백엔드 전체 `832 passed, 1 skipped`, 프런트 `16 passed`, 프로덕션 빌드, Ruff, 승인 매니페스트 검증을 통과했다. 원격 하이브리드 검색 품질은 24/24 기준 Hit@5·Hit@1·MRR@5 모두 1.000이다.
- Advisor의 신규 두 테이블 `RLS Enabled No Policy` INFO는 브라우저 직접 접근을 막는 의도된 서버 전용 deny-by-default 설계다. 프로젝트 기존 WARN인 Auth 유출 비밀번호 보호 비활성화와 기존 성능 INFO는 이번 범위에서 변경하지 않았다. [RLS INFO 설명](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) · [Auth WARN 조치 안내](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)

### 2026-07-20 14:39 KST

- 승인/적용: 이재용의 원격 Supabase 적용 승인을 전달받아 `20260720044229`와 `20260720044230`을 CLI `db push`로 적용했다. migration history 20개가 로컬과 1:1로 일치한다.
- 사전 정합화: 원격에 `20260718172329_repair_market_news_is_active`로 적용됐지만 로컬 파일명이 `20260719184500`이던 기존 불일치를 이력 조작 없이 파일명만 원격 버전에 맞췄다. `migration repair`는 사용하지 않았다.
- 적용 중 발견·보정: 첫 시도에서 대표 고객 런타임 `tax_year=2025`가 기존 2026 엔진 제약과 충돌해 전체 롤백됐다. 대표 컨텍스트는 2026을 유지하도록 migration·loader를 교정했다. 두 번째 시도에서는 구버전 원격 벤치마크 10명이 합산 납입 1,800만 원을 초과해 전체 롤백됐다. 생성기와 같은 비례·1만 원 단위 보정 SQL을 추가했으며 18개 영향 계좌의 목표값이 최신 로컬 CSV와 모두 일치함을 적용 전에 확인했다.
- 원격 검증: 사용자 10,000·계좌 16,900·보유 79,381 유지, 개인연금 납입한도 위반 0, 사용자 납입액 투영 불일치 0, 소득구간별 16.5%/13.2% 세율 불일치 0. 대표 고객 6명·계좌 13개·legacy 보유 86개와 공통 계좌/스냅샷/보유 13/13/86, 양쪽 잔액 불일치 0, ETF 6개 브랜드를 확인했다.
- 보안/회귀: public 테이블 RLS 43/43, 권한 `anon` 0·`authenticated` 5·`service_role` 43, CLI Advisor WARN 이상 0건. 전체 `pytest` 721 passed·1 skipped, Ruff와 `git diff --check` 통과.
- 주의: `db push` 후 로컬 Docker가 없어 pg-delta 카탈로그 캐시 생성 경고가 있었으나 원격 적용과 이력 기록은 정상 완료됐다. 이번 보정 코드와 핸드오프 문서는 별도 PR로 main에 반영해야 한다.

### 2026-07-20 13:49 KST

- main 통합: 고객 계약 PR #77이 최신 `main`과 충돌해 별도 worktree에서
  `origin/main` `5409a33`을 병합했다. 대표 고객의 1만 명 기준 나이·계좌·소득은
  유지하고, main의 짧은 로그인 ID를 함께 보존했다.
- migration 순서: 원격 적용 완료 `20260720034015`는 수정하지 않았다. 원격
  미적용 고객 계약을 `20260720044229`로 재정렬하고, legacy 86개 상세 보유를
  공통 계좌 13개·스냅샷 13개·보유 86개로 동기화하는
  `20260720044230`을 CLI로 추가했다. 두 파일 모두 원격 미적용이다.
- 검증: 변경 전체 Ruff 통과, 전체 pytest `704 passed, 1 skipped`, 모든 SQL
  migration `pglast` 파싱, seed의 86개 공통 보유 계약을 통과했다. 고객데이터
  병합 대상 시크릿 패턴 검사도 0건이다.
- 다음 작업: 충돌 해결 커밋을 PR #77 브랜치에 push하고 GitHub 병합 상태를
  확인한다. 원격 Supabase migration 적용은 별도 승인 전 수행하지 않는다.

### 2026-07-20 12:42 KST

- API E2E: `verify_auth_rls_e2e.py`에 폐기형 Auth 사용자를 `dc_dormant`
  시나리오에 임시 연결하는 검증을 추가했다. 실제 Bearer token으로
  `GET /me/pension-accounts`를 호출해 `data_boundary=mock`, 비어 있지 않은
  계좌·보유내역을 확인했다.
- 정리·회귀: 스크립트는 Auth/RLS, 연금계좌 API, 채팅 replay, RAG·뉴스·공시·ETF,
  rollback-only NAVER SQL을 통과했다. 종료 후 임시 demo context는 0건임을
  원격에서 재조회했다. 계약 테스트 25건과 스크립트 Ruff도 통과했다.
- 다음 작업: 변경 범위를 다시 검토한 뒤 명시적 stage·commit·push와 Draft PR을
  생성한다. main push·PR 머지는 하지 않는다.

### 2026-07-20 12:20 KST

- 승인·원격 적용: 이재용 총괄의 명시적 승인 후 MCP로
  `backfill_mock_pension_accounts`를 적용했다. 원격 migration version은
  `20260720034015`이며, 로컬 신규 파일도 같은 버전으로 이름만 정합화했다.
  `migration repair`, reset, 기존 mock 데이터 삭제는 수행하지 않았다.
- 사후 동등성: source 시나리오/계좌/보유는 6/13/26, 신규 공통 구조는
  account/snapshot/holding 13/13/26이고 잔액·보유합계 불일치는 0건이다.
  `contributed_principal_krw` nullable, `etf_isu_code` 컬럼·partial index도
  실제 카탈로그에서 확인했다.
- 보안·런타임: public 43개 테이블의 RLS 43/43, 테이블 권한은 anon 0·
  authenticated 5·service_role 43으로 적용 전과 같았다. 원격
  `verify_auth_rls_e2e.py`는 Auth/RLS, 채팅, RAG·뉴스·공시·ETF, rollback-only
  NAVER SQL을 통과했다. 신규 repository도 기존 demo Auth 컨텍스트에서
  목계좌 1개·보유 1개를 읽어 `AggregationInput`으로 변환했다.
- 남은 검증: 새 `GET /me/pension-accounts`의 실제 Bearer-token API E2E와
  PR stage·commit·push·리뷰는 아직 수행하지 않았다.

### 2026-07-20 11:48 KST

- 작업자/브랜치/기준: Codex / `codex/pension-account-backfill` /
  `origin/main` `557e8f1`; 별도 ignored worktree에서 작업했다.
- 시작 상태: main과 origin/main은 동일하고 원래 worktree는 clean이었다.
  지정 MEMORY 경로는 확인 불가였다. Supabase CLI 2.109.1과 현재
  `migration new` 도움말을 확인했다.
- TDD/변경: backfill migration과 seed 재현 계약이 없는 상태에서 신규 테스트
  2건이 실패함을 먼저 확인했다. CLI로
  `20260720024530_backfill_mock_pension_accounts.sql`을 생성해 기존
  6/13/26을 `pension_accounts`·`account_snapshots`·
  `account_holding_snapshots`으로 멱등 이관하도록 작성했다. 기존
  mock 테이블은 유지한다.
- 데이터 의미: 기존 목데이터에는 누적 납입원금 사실이 없으므로 평가액을
  납입원금으로 꾸며내지 않는다. `contributed_principal_krw`의 NOT NULL을
  완화하고 backfill 값은 NULL로 보존한다. 계좌·스냅샷·보유 UUID는 자연키와
  기준일로 결정론 생성한다. 기존 목보유의 KRX 종목코드는 신규 nullable
  `account_holding_snapshots.etf_isu_code`에 보존한다.
- DB-04A: `PensionAccountRepository`와 인증
  `GET /me/pension-accounts`를 추가했다. 본인 실계좌가 있으면 그것만 읽고,
  없을 때만 `demo_user_financial_context`로 연결된 목시나리오 계좌를
  사용한다. 계좌별 최신 스냅샷만 읽으며 잔액·보유합계 불일치는 엔진 변환
  전에 차단한다. 응답은 현재 보유 ETF 코드와 원금 미확인 NULL을 유지하고
  `AggregationInput`으로 결정론 변환할 수 있다. REST·보유 스냅샷 계약 변경이다.
- 원격 읽기 검증: 프로젝트는 `ACTIVE_HEALTHY`, public 테이블 43개 모두
  RLS 활성이다. source 6/13/26, 잔액·보유합계 불일치 0건, target
  account/snapshot/holding 0/0/0을 확인했다. 원격 쓰기는 수행하지 않았다.
- 드리프트 판정: 원격 migration은 17개이며
  `repair_market_news_is_active`가 `20260718172329`로 기록되어 있지만
  main의 로컬 파일은 `20260719184500`이다. 원격 statement 1건과 로컬 SQL은
  공백을 제외하면 동일하다. 기존 이력을 수정·repair·재적용하지 않는다.
- 로컬 검증: 최초 신규 계약 2건 실패 후 계약 테스트 21건을 통과했다.
  누락된 잠금 의존성을 `uv sync --frozen`으로 설치하고 쓰기 가능한
  `--basetemp`를 지정했다. DB-04A 타깃 37건과 최종 전체 회귀
  686건 통과·1건 스킵을 확인했다.
  `uv run ruff check --no-cache .`와 `git diff --check`도 통과했다.
- 원격 적용: 없음. DB-03은 `LOCAL-DRAFT`; 이재용 승인 전 적용·push·PR
  머지를 하지 않는다.
- 다음 작업: SQL 리뷰와 전체 회귀, migration drift의 동일 DDL 판정을 마쳤다.
  이재용의 DB-03 원격 적용 승인을 받은 뒤 target 13/13/26,
  금액·위험처리·엔진 결과 동등성을 원격에서 재검증한다.

### 2026-07-19 01:21 KST

- 작업자/브랜치/기준: Codex / `codex/supabase-current-state-docs` / `origin/main` `c7e097f`; PR #55·#57·#58은 모두 MERGED이고 각 backend/frontend CI가 통과했다. main의 최신 추가 커밋은 세션 하네스 문서·설정이며 DB/backend 변경은 없다.
- 시작·격리 확인: 세션 시작 시 지정 경로의 MEMORY는 확인 불가였으나 종료 전 생성된 파일을 다시 읽어 RAG PR #56 완료 기록만 있음을 확인했다. 원래 작업 폴더는 다른 세션의 `harness/session-md`이며 clean 상태이고 수정·stash·reset하지 않았다.
- 원격 적용: 승인된 COMMENT 전용 migration을 적용했다. MCP가 `20260718154819_repair_corrupted_column_comments`를 기록했으며, 로컬 파일명도 SQL SHA-256을 보존한 채 같은 버전으로 정합화했다. `migration repair`, `db reset`, destructive SQL은 사용하지 않았다.
- 원격 재검증: 현재 branch의 migration 16개와 원격 16개는 이름·버전이 1:1로 일치한다. public 테이블 43개·RLS 43/43, 권한 `anon` 0·`authenticated` 5·`service_role` 43이다. 교정한 설명 3건은 목표 문구와 정확히 같고 U+FFFD가 없다. COMMENT migration statement count는 1, legacy BGE-M3 migration은 0이다. 공시 88/126, 지식 10/45, 뉴스 15, 목데이터 6/13/26, ETF 2,507/217,833은 적용 전과 같다.
- 런타임 E2E: `scripts/verify_auth_rls_e2e.py`가 Auth 두 사용자 RLS 격리, 채팅 저장·idempotency replay, RAG·뉴스·공시·ETF API, rollback-only NAVER SQL을 실제 원격 DB에서 통과했다. 종료 후 임시 Auth 사용자·임시 제목 세션·고아 세션은 각각 0건이다.
- 연결 상태: 적용·migration/RLS/GRANT/행 수/Advisor 조회까지 Supabase MCP가 정상 동작했으나, 최신 main rebase 후 마지막 cleanup SELECT에서 OAuth `401 token_revoked`가 발생했다. 시크릿을 출력하지 않는 직접 DB `SELECT`로 임시 Auth 사용자 0·임시 세션 0·고아 세션 0·`ingestion_runs` 37을 대체 재확인했다.
- Advisor: 보안 INFO 29는 클라이언트 권한이 없는 서버 전용 테이블의 의도된 deny-by-default 상태다. WARN 1은 Auth 유출 비밀번호 보호 비활성화다. 성능 INFO 39는 미사용 인덱스이며 이번 COMMENT 변경과 무관하다.
- blocker: Supabase Dashboard가 로그인 화면이고 로컬 CLI도 access token이 없어 `password_hibp_enabled`를 변경할 수 없다. 자격 증명을 요청·출력하지 않고 DB-09를 `BLOCKED`로 유지한다.
- 로컬 검증: 계약 테스트 19건, 전체 pytest 612건(기존 DeprecationWarning 1건), Ruff, `git diff --check`, `supabase/AGENTS.md`·`CLAUDE.md` 동일성 검사가 모두 통과했다.
- Git/PR: `codex/supabase-current-state-docs`를 push하고 Draft PR #59를 생성했다. backend/frontend CI status check 대상이며 ready 전환·머지는 하지 않았다.
- 다음 작업: PR #59 CI·리뷰를 확인한다. 이후 Supabase MCP 또는 Dashboard/CLI를 재인증해 DB-09를 처리한다. PR 머지는 이재용의 별도 명시적 승인 전까지 금지한다.

### 2026-07-19 00:11 KST

- 작업자/브랜치/기준: Codex / `codex/supabase-column-comments` / `origin/main` `dc94f0d`.
- 원격 읽기 재검증: 프로젝트 `ACTIVE_HEALTHY`, migration 15개, public 테이블 43개·RLS 43/43, 권한 `anon` 0·`authenticated` 5·`service_role` 43, 목데이터 목표값 5/5를 확인했다. 로컬 main 15개와 원격 migration 이름·버전은 1:1이다.
- 발견: 컬럼 설명 3건에 U+FFFD 대체문자가 존재했다. BGE-M3 원격 상태는 `vector(1024)` non-null 45건·HNSW 존재이며, `20260715165614` migration statements는 0건이다.
- TDD/변경: migration 부재로 계약 테스트가 먼저 실패하는 것을 확인한 뒤 CLI 2.109.1의 `migration new`로 `20260718151030_repair_corrupted_column_comments.sql`을 생성했다. SQL은 COMMENT 3문만 포함한다.
- 문서: DB 세션 고정 운영 절차를 [`DB_SESSION_GUIDE.md`](./DB_SESSION_GUIDE.md)로 분리하고 `AGENTS.md`·`CLAUDE.md` READ-FIRST를 동일하게 갱신했다.
- 검증: 관련 계약 19건 통과, 전체 `uv run pytest` 603건 통과(기존 DeprecationWarning 1건), `uv run ruff check .`, `git diff --check`, `AGENTS.md`·`CLAUDE.md` 동일성 확인 통과.
- Advisor: 보안 INFO 29·WARN 1(유출 비밀번호 보호 비활성화), 성능 INFO 40(미사용 인덱스)이며 이번 COMMENT 범위와 무관해 변경하지 않았다.
- Git/PR: `codex/supabase-column-comments`를 push하고 Draft PR #57을 열었다. 원격 적용과 PR 머지는 하지 않았다.
- 원격 적용: 없음. 이재용 승인 전 적용 금지. `migration repair`, `db reset` 미사용.
- 다음 작업: 이재용에게 원격 migration 적용 승인을 요청한다. 승인 후 적용·실제 컬럼 설명 재조회·migration 16개 정합성을 검증한다.

### 2026-07-18 22:19 KST

- 작업자/브랜치/기준: Codex / `fix/supabase-migration-reconcile` / `origin/main` `3573619`.
- 이력 정리: `add_lifecycle_demo_scenarios`와 `add_benchmark_mock_data`는 원격 적용 SQL과 로컬 SQL이 같음을 확인하고 파일 버전을 각각 `20260716041911`, `20260716043326`으로 맞췄다. PowerShell 기본 출력에서 보인 한글 깨짐은 파일 손상이 아니라 콘솔 인코딩 표시 문제였다.
- 원격 적용: `sync_modified_mock_data`의 시나리오 UPSERT에 값 변경 조건을 추가하고 `20260718131917`로 정식 적용했다. 적용 전후 5개 시나리오와 5개 대표 고객의 값·`updated_at`이 모두 같아 불필요한 재기록이 없었다.
- 원격 재검증: migration 15개, public 테이블 43개, RLS 43/43, `service_role` 권한 43개 테이블을 확인했다. 로컬 15개 migration 이름·버전과 원격 이력이 1:1로 일치한다.
- 금지 명령: `migration repair`, `db reset`은 사용하지 않았다.
- 다음 작업: 로컬 SQL 계약·전체 회귀 검증 후 PR 리뷰·머지.

### 2026-07-18 KST

- 작업자/브랜치: Codex / `feat/etf-portfolio-supabase-integration` / 사용자(이재용) 승인 하.
- 변경: 참고 캐시를 `data/cache/`로 이동하고 교육용 포트폴리오 캐시를 `.3`→`.4`로 스키마 보강했다. 120개 시나리오의 기존 후보·위험·계획 결과는 유지하고 누락 3필드만 추가했다. `source_sha256`은 cost-return 마스터뿐 아니라 실제 사용한 KIS 수정주가·KIND 이벤트·필요 시 KRX fallback까지 포함한다.
- 원격 적용: `20260717054500_add_etf_portfolio_universe` 적용. 3개 테이블 RLS 활성, `anon`·`authenticated` 권한 없음, `service_role` 테이블 권한과 identity sequence usage 확인. 기준일 2026-07-16 `ready` 버전 1에 상품 2,507행(DC 823·IRP 823·연금저축 861), 861종목 총수익 이력 217,833행 적재.
- 조회 연결: FastAPI 엔진·챗봇은 `DATABASE_URL`이 있으면 최신 `ready` DB 버전을 사용하고, URL이 없는 개발·테스트 환경에서만 로컬 캐시를 사용한다. DB 오류를 로컬 캐시로 숨기지 않는다.
- 검증: DB·로컬 상품·이력·출처 불일치 0, DB 정렬 기준 120개 포트폴리오와 확정 캐시 불일치 0, 위험한도 위반 0, 후보 슬리브 누락 0. `/engine/educational-portfolio` 원격 DB E2E HTTP 200·후보 5개·엔진 `.4` 확인.
- Advisor: ETF 관련 보안 항목은 서버 전용 테이블 3개의 의도된 deny-by-default `RLS Enabled No Policy` INFO뿐이며, ETF 관련 성능 경고는 0건이다. 프로젝트 전체 기존 항목은 보안 INFO 29·WARN 1(유출 비밀번호 보호 비활성화), 성능 INFO 42건이다.
- 주의: 원격 migration history에는 로컬에 없는 후속 뉴스 마이그레이션과 일부 로컬 파일명과 다른 버전이 이미 존재한다. 이번 작업은 ETF 마이그레이션 1건만 추가했으며 기존 이력을 수정하지 않았다.

### 2026-07-17 14:50 KST

- 작업자/브랜치: Claude, 사용자(이재용) 승인 하 / `feat/etf-portfolio-supabase-integration` / 기준 `main` `a7771a9`.
- 배경: 교육용 포트폴리오 엔진 입력이 로컬 파일 캐시(`data/cache/`, gitignore)에만 존재해 다른 환경에서 챗봇 운용전략 답변이 불가한 문제를 원격 통합으로 해결하기로 결정(이재용).
- 신규 migration: `20260717054500_add_etf_portfolio_universe.sql` (`LOCAL-DRAFT`). 테이블 3개 — `etf_dataset_versions`(적재 버전·ready 계약), `etf_universe_products`(계좌별 상품 마스터, payload jsonb), `etf_return_histories`(종목별 253관측 총수익 지수). 원시 수정주가 89.7만 행은 적재하지 않고 파일 원본 보존(무료 티어 500MB 대응, 적재 대상 약 24만 행).
- 보안: RLS 3/3 활성화, `public`/`anon`/`authenticated` 권한 회수, `service_role`만 부여(기존 내부 테이블 패턴 동일).
- 검증: `tests/test_schema_contract.py`에 `test_etf_universe_is_server_only_and_versioned` 추가, 16 passed(전체 migration pglast 파싱 포함). `ruff check` 통과.
- 원격 미적용: 이재용 승인·적재 스크립트 완성 후 적용 예정.
- 다음 작업: ①적재 스크립트 `scripts/load_portfolio_universe.py` ②`PortfolioUniverseRepository.from_database()` + DB 우선·파일 fallback ③산출물 동등성(120개 포트폴리오)·챗봇 E2E 검증. 스키마는 엔진 입력 계약과 겹치므로 김태형 합의 필요(`계약 변경` PR 표기 예정).

### 2026-07-17 15:05 KST

- 작업자/브랜치: Claude, 이재용 승인 하 / `feat/etf-portfolio-supabase-integration` / 기준 `main` `a7771a9`.
- 이재용 결정: 실 데이터 수집(수시간·수천 API 호출)은 직접 실행하지 않고 김태형의 기존 검증 캐시를 받는 쪽으로 진행(2026-07-17). 그 사이 적재 스크립트를 완성했다.
- 신규 코드: `backend/app/etf_universe_database.py`(`load_portfolio_universe`) — 계좌 3종의 `PortfolioUniverseRepository.from_latest_cache` 결과를 그대로 옮긴다. 계좌 간 as_of 불일치는 예외로 차단, 같은 종목이 여러 계좌에서 적격이면 이력을 종목당 1행으로 병합, 적재 원본 파일들의 결합 SHA-256을 `source_sha256`에 기록. `scripts/load_portfolio_universe.py`는 `.env`의 `DATABASE_URL`로 이를 실행하는 얇은 CLI.
- 검증: `tests/test_etf_universe_database.py` 신규(합성 fixture로 병합·불일치 차단 검증, `psycopg.connect`를 fake 커넥션으로 치환해 실제 DB 없이 SQL 실행 경로 검증) 2 passed. 전체 `uv run pytest` 514 passed, `uv run ruff check .` 통과. **실제 원격 적재는 아직 수행하지 않았다** — 김태형 캐시 파일 수령 전.
- 다음 작업: 김태형 캐시(`data/cache/returns`·`data/cache/kis/adjusted_prices`·`data/cache/events`) 수령 → 이 스크립트로 실적재 → `PortfolioUniverseRepository.from_database()` + DB 우선·파일 fallback 구현 → 산출물 동등성(120개 포트폴리오)·챗봇 E2E 검증 → 이재용 승인 후 마이그레이션 원격 적용.

### 2026-07-18 01:15 KST

- 작업자/브랜치/기준: Codex / `Supabase데이터-` / `origin/main` `fa009fa`.
- 시작 상태: 원래 worktree는 다른 브랜치의 미커밋 변경이 있어 `C:\dev\KDA-securities-supabase-data` 별도 worktree를 생성했다. 기준 회귀는 546건 통과였다.
- 원격 확인: Supabase MCP로 `KDA-securities` 연결과 40개 public 테이블 RLS 40/40을 확인했다. 시나리오 설명 5건과 대표 고객 납입액 5건이 2026-07-17 19:42 KST에 직접 수정된 상태였다. 원격 현재 건수는 시나리오/계좌/보유 6/13/26, 대표 고객 6, 벤치마크 사용자/계좌/보유 10,000/16,900/79,381이다.
- 변경 내용: `20260717160209_sync_modified_mock_data.sql`을 CLI로 생성해 멱등 DML을 추가하고, `seed.sql`, 챗봇 fallback 시나리오, 대표 고객 manifest와 Auth 프로비저닝 SQL을 같은 설명·납입액으로 동기화했다. 계좌 잔액·보유자산은 변경하지 않았다.
- TDD/검증: 신규 계약 테스트가 migration 부재·manifest 필드 부재로 실패하는 것을 먼저 확인했다. 구현 후 관련 40건 통과, 전체 `uv run pytest` 550건 통과(기존 DeprecationWarning 1건), `uv run ruff check .`와 `git diff --check` 통과.
- 원격 적용: 없음. 원격 데이터가 이미 목표값이므로 재실행하지 않았다. migration history의 `20260716015043`↔`20260716041911`, `20260716042903`↔`20260716043326` 불일치가 있어 `db push`·`migration repair`도 실행하지 않았다.
- 로컬 DB reset: Docker CLI/daemon이 없어 실행하지 못했다. 모든 migration은 `pglast` 계약 테스트로 파싱했다.
- Advisor: 보안 WARN은 기존 Auth leaked-password protection 비활성화 1건, INFO는 서버 전용 테이블의 RLS deny-by-default 상태다. 성능 INFO는 초기/미사용 인덱스이며 이번 DML 변경과 무관해 수정하지 않았다.
- 다음 작업: PR 리뷰·머지 후 migration history 정리 방식을 이재용 승인으로 결정한다. 신규 데이터 migration은 원격에 적용하지 않아도 현재 값과 일치한다.

### 2026-07-16 11:35 KST

- 작업자: Claude, 사용자(이재용) 요청에 따른 RAG 지식 코퍼스 실적재.
- 변경 범위: `knowledge_documents`/`knowledge_chunks`만 다룬다. 같은 시점 반영된 `20260716001737` 사용자·성향·계좌 도메인 작업과는 무관하다.
- 변경 내용: 청크 사이즈 `DEFAULT_CHUNK_CHARS` 1800→800자(`backend/app/ingestion/knowledge.py`). 세액공제 신규 문서(`docs/40_규제/연금계좌_세액공제.md`, 소득세법 제59조의3·국세청 공식 안내를 WebFetch로 원문 대조 확인 후 작성) 추가. `연금_기초.md:155`에 프로젝트 공식 용어 "적격 TDF"를 반영(사실관계 변경 없음, 검색 신호 보강).
- 원격 적용: `scripts/ingest_knowledge.py`, `scripts/embed_knowledge_chunks.py` 실행. `knowledge_documents` 1→2건, `knowledge_chunks` 1→31건(전건 BGE-M3 1024차원 embedding 보유).
- 검증: 원격 하이브리드 검색 실측(이번이 최초의 다중 문서 기준 실측) `mode=hybrid, Hit@5=1.000, Hit@1=1.000, MRR@5=1.000 (10/10)`. 로컬 `uv run pytest` 347 passed, `uv run ruff check .` 통과.
- 발견 및 조치: 청크 사이즈 축소 직후 1차 실측에서 `critical_top1` 케이스(`tdf-exception`) 실패(Hit@1=0.900)를 확인했다. 원인은 청크 크기가 아니라 원문에 "적격"이라는 정확한 용어가 없어 무관 청크와 오매칭된 것이었다. 용어 보강 후 재적재·재임베딩으로 해결을 확인했다(추측 없이 실제 top-5 결과를 조회해 원인 특정).
- 벤치마크 갱신: `data/search_quality/knowledge_v1.json`의 `tax-credit` 케이스 정답 문서를 신규 세액공제 문서로 갱신(문서 유형 부스트로 regulation 문서가 우선하는 것이 의도된 동작).
- 다음 작업: 벤치마크 쿼리를 10개→50개 이상으로 확충(문서가 2개 이상이 된 지금부터 유의미), 나머지 후보 문서(퇴직연금감독규정 등) 순차 추가.

### 2026-07-16 10:59 KST

- 작업자/브랜치/기준: Codex / `codex/lifecycle-scenario-auth` / `main` `eea2b4e`.
- 원격 사전 확인: migration 7개(`20260716011137` 포함), 목시나리오 3개·목계좌 6개·목보유 10개, Auth 사용자 0명.
- 로컬 변경: 기존 행동형 3명을 유지하고 `young_retirement_distance`, `family_budget_pressure`, `pension_payout_transition` 생애주기형 3명을 추가했다. 적용 후 목표 건수는 6/13/26이다.
- Auth 준비: 대표 고객 6명의 고정 UUID v4·로그인 ID·시나리오 매핑 manifest와 서버 전용 생성/검증 스크립트를 추가했다. 실제 비밀번호 6개는 Git 제외 `secrets/demo_scenario_auth.json`에 서로 다른 무작위 값으로 준비했으며 출력·커밋하지 않았다.
- 원격 미적용: 신규 migration과 Auth 계정은 PR·이재용 승인 전이므로 원격에 적용하지 않았다.
- 로컬 중간 검증: 관련 테스트 46건 통과. Windows 기본 임시 폴더 권한 문제는 쓰기 가능한 `--basetemp` 지정으로 재실행했으며 코드 실패가 아니었다.

### 2026-07-16 10:12 KST

- 작업자/브랜치/커밋: Codex / `codex/db-handoff-post-deploy` / 기준 `main` `7757a29`.
- 승인·머지: 사용자에게 이재용 팀장 승인을 전달받아 PR #22를 ready 전환 후 `main`에 머지했다. 머지 커밋은 `7757a29`이다.
- 원격 적용: `20260716001737_add_user_pension_domain.sql` 적용 완료. CLI의 `--dry-run` 호출이 실제 적용 로그를 출력해 즉시 중단·재실행 없이 migration history와 카탈로그로 실제 적용을 확인했다.
- 원격 검증: migration 6개, public 테이블 36개, RLS 36/36. 신규 도메인 11개 테이블·RLS 11/11, 소유권 정책 28개, 명시 인덱스 24개, `anon`·`authenticated` 신규 테이블 권한 0개, `service_role` 11개 테이블 권한을 확인했다.
- reference data: 성향 설문 세트 1개, 질문 6개, 선택지 30개. 사용자 프로필·진단·계좌·스냅샷·현금흐름·상품·보유내역은 backfill 전이므로 모두 0건이다.
- 기존 데이터 보존: 목시나리오 3개·목계좌 6개·목보유 10개, 연금저축 공시 88개, 퇴직연금 공시 126개, knowledge chunk 1개로 적용 전과 동일하다.
- Advisor: 보안 INFO는 클라이언트 GRANT가 없는 서버 전용 reference 테이블의 의도된 RLS deny-by-default 상태다. 성능 Advisor가 `investment_profile_answers(option_id, question_id)` 복합 FK의 covering index 1건을 지적해 `20260716011137_add_profile_answer_fk_index.sql`로 별도 보완했다. 신규 테이블의 unused-index INFO는 데이터·트래픽이 없는 초기 상태라 삭제하지 않는다.
- 로컬 검증: 후속 migration 포함 SQL 계약 테스트 14 passed, 전체 pytest 339 passed(기존 DeprecationWarning 1건), Ruff 통과, `git diff --check` 통과.
- 원격 미적용: 후속 `20260716011137`은 별도 PR 승인 전 적용하지 않는다.
- 다음 작업: 후속 인덱스 PR 승인·적용 후 성능 Advisor 재검증, 이후 DB-03 목데이터 3/6/10 backfill.

### 2026-07-16 09:21 KST

- 작업자/브랜치/커밋: Codex / `codex/db-handoff-integration` / 시작 HEAD `a39e883`.
- 시작 상태: 깨끗한 브랜치. 원격 DB 25개 테이블·RLS 25/25·적용 마이그레이션 5개를 재확인.
- 변경 내용: 작업 시작 시 원격 적용 이력에서 Git에 빠졌던 채팅 멱등성 마이그레이션 2개를 원문 복원했다. PR 생성 시 최신 `main` `f01934e`에 동일 파일이 이미 포함된 것을 확인해 리베이스했고, 최종 PR에는 중복 파일 없이 `20260716001737_add_user_pension_domain.sql`과 관련 문서·테스트만 남겼다. 신규 migration에는 사용자 프로필·5단계 성향·DC/IRP/연금저축계좌·스냅샷·현금흐름·상품·보유내역의 additive DDL, RLS, service-role-only GRANT, FK 인덱스, 잠정 설문 reference data를 추가.
- 결정 및 근거: `user_profiles` 사용, `account_cash_flows` 포함, 기존 목테이블 유지, `community_reviews` 보류, 3단계 목성향과 5단계 진단성향 매핑 금지. FastAPI 경유 원칙 때문에 신규 테이블의 `anon`·`authenticated` 권한은 회수하고 소유권 RLS를 방어 계층으로 유지.
- 원격 사실 보정: embedding은 `vector(1024)`, HNSW 존재, non-null 1건·비정상 차원 0건. 채팅 멱등성 `session_id` FK 인덱스 누락은 신규 마이그레이션에서 보완.
- 로컬 검증: 최신 `main` 리베이스 후 SQL 계약 테스트 13 passed, 전체 `uv run pytest -p no:cacheprovider` 308 passed(기존 DeprecationWarning 1건), `uv run ruff check .` 통과.
- 원격 적용 여부: 신규 `20260716001737`은 적용하지 않음. 이재용 승인 전 원격 적용 금지.
- 남은 위험: 잠정 성향 설문의 실제 문구·배점 승인, 목계좌 3/6/10 backfill과 엔진 동등성, 실제 Auth 경로 E2E가 후속 필요.
- 다음 작업: Draft PR 리뷰 후 이재용 승인 시 원격 migration 적용·재검증, 이후 승인된 별도 backfill 작업.

### 2026-07-15 17:21 KST

- 작업자: Codex, 사용자 요청에 따른 핸드오프 문서 작성.
- 기준: `main` / `bccaae3` / 기존 dirty worktree 유지.
- 확인: 원격 24개 테이블, 적용 마이그레이션 2개, RLS 24/24, 주요 행 수, embedding type과 HNSW 부재를 읽기 전용 SQL로 재검증.
- 발견: 원격 `knowledge_chunks` 1건에 1024차원 embedding이 이미 있어 pending migration의 "전부 null" 가정이 사실과 다름.
- 동시 작업: 문서 작성 중 임베딩 관련 `backend/app/chat/narrator.py`, `tests/test_chat_mvp.py`, `scripts/apply_embedding_migration.py` 변경이 추가로 나타남. 소유자 미확인 상태로 보존.
- 변경: DB·코드는 수정하지 않고 `supabase/DB_HANDOFF.md`, `supabase/AGENTS.md`, `supabase/CLAUDE.md`만 추가.
- 로컬 검증: `uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py` 실행, 8 passed.
- 원격 적용: 없음.
- 다음: 진행 중 임베딩 작업 소유자 확인 후 DB-00과 DB-01을 분리해 리뷰.

### 2026-07-15 18:29 KST

- 작업자/브랜치: Codex / `codex/rag-retrieval-foundation`.
- 시작 상태: PR1 커밋 이후 review 수정, `origin/main` 대비 ahead 1·behind 3. 루트가 후속 stacked rebase를 관리한다.
- 변경 내용: 지식 문서 URL을 fragment 없는 canonical 값으로 통일하고, 청크 재적재를 삭제 대신 동일 ID upsert로 변경했다. 변경 청크의 embedding은 비우고 제거된 후행 청크는 metadata `is_active=false`로 비활성화한다.
- 결정 및 근거: 신규 컬럼·migration 없이 기존 JSON metadata 계약으로 soft-deactivate한다. 검색과 embedding 대상은 허가 출처·문서 유형·`verified_knowledge`·비개인·비목데이터·active 청크로 제한한다.
- 로컬 검증: `uv run pytest` 216 passed, `uv run ruff check .` 통과, `git diff --check` 통과. 로컬 승인 코퍼스는 Hit@5·Hit@1·MRR@5 모두 1.000이다.
- 원격 적용 여부: 없음. migration history 변경 없음. `supabase/seed.sql`의 로컬 reset용 URL·metadata만 동기화했다.
- 남은 위험: 원격에 canonical URL과 legacy fragment URL이 동시에 존재하면 자동 병합하지 않고 적재를 실패시킨다. 중복이 확인될 경우 참조 건수를 먼저 확인한 뒤 별도 정리한다.
- 다음 작업: PR 리뷰 후 승인된 적재 명령 실행, 변경 청크 BGE-M3 재임베딩, 원격 검색 품질 재측정.

## 스키마 정비 A — additive 제약·자동 시각 갱신 (LOCAL-VERIFIED)

### 2026-07-21 KST

- 작업 브랜치: `db/schema-additive` (기준 `origin/main` `c66d0ee`). 새 migration `20260721120000_add_updated_at_triggers_and_holding_constraints.sql`를 추가했으며 원격 적용은 하지 않았다.
- 원격 사전 카탈로그 조회: `updated_at` 보유 public 테이블은 13개(`chat_sessions`, `data_sources`, `demo_investor_profiles`, `demo_public_portfolio_metrics`, `demo_user_financial_context`, `etf_product_descriptions`, `etf_theme_content_reviews`, `financial_institutions`, `financial_products`, `knowledge_documents`, `mock_scenarios`, `pension_accounts`, `user_profiles`)이고 기존 BEFORE UPDATE 트리거는 0개였다.
- 변경: `extensions` 스키마의 `moddatetime` extension과 위 13개 테이블의 BEFORE UPDATE 트리거를 명시적으로 추가했다. 앱 코드의 `updated_at = now()`는 유지했다.
- A-2 사전 위반 조회: `account_holding_snapshots`의 product 중복 그룹 0건·raw 이름 중복 그룹 0건, `account_holding_snapshots.etf_isu_code` 형식 위반 0건, `mock_holdings.etf_isu_code` 형식 위반 0건. 따라서 partial unique index 2개와 두 ETF 코드 형식 CHECK를 추가했다.
- 검증: `uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py` 31 passed. 로컬 Supabase reset은 Windows Docker daemon 부재로 실행하지 못했으며, `supabase/seed.sql`의 공용 모델 replay 계약은 schema contract test로 정적 확인했다. TODO: 원격 적용 승인 후 실제 migration 적용·trigger 카탈로그 재조회·seed reset을 재검증한다.
- 원격 적용 여부: 없음. 상태는 `LOCAL-VERIFIED`이며 이재용 승인 전 원격 migration을 적용하지 않는다.

## 해외주식형 ETF 공식 상위 구성정보 (REMOTE-APPLIED)

### 2026-07-22 18:27 KST

- 작업자/브랜치/기준: Codex / `ETF테마소개` / 시작 HEAD `7fa6507`; 기존 ETF 테마 P0 dirty 변경을 보존한 채 후속 구현했다.
- 계약 변경: 국내주식형은 기존 KIS 스냅샷을 사용하고, 해외주식형은 승인된 운용사 공식 공시를 사용한다. `actual_portfolio`는 `실제 보유종목 TOP3`, PDF/PCF의 `creation_basket`은 `구성 바스켓 TOP3`로 답변에 구분하며 기준일·원문 URL·운용사·비중 근거를 함께 보존한다. 공식 기준일 10일 초과, 유효 비중 종목 3개 미만, 담보자산은 답변에서 제외한다.
- migration: `20260722093206_add_official_etf_component_sources.sql`은 기존 스냅샷에 기준일·출처 유형·커버리지·완전성·비중 기준·원문 위치를 additive하게 추가하고, 서버 전용 `etf_component_source_bindings` 테이블과 RLS/GRANT를 추가한다. 운용사 출처 5개와 승인 종목 11개를 멱등 등록하며 `seed.sql`의 출처 reference data도 동기화했다. Advisor가 신규 `source_id` 외래키 covering index를 지적해 실패 계약 테스트를 추가한 뒤 `20260722093547_add_official_etf_binding_source_index.sql`로 보완했다.
- 승인 범위: 별도 공유 대화 대기 중인 17 금/원자재, 18 코리아밸류업, 19 ESG, 22 메타버스는 건드리지 않았다. 초기 바인딩은 그 밖의 현재 해외주식형 후보 11개(SOL 3, TIGER 3, KIWOOM 2, KODEX 1, KoAct 2)로 제한했다.
- 수집기: 다섯 운용사별 HTML/JSON 어댑터, 원문 JSON·SHA-256, 종목별 실패 격리, 부분 응답 품질 게이트, 평일 12:40 KST GitHub Actions를 추가했다. TLS 검증은 끄지 않고 `truststore` 운영체제 신뢰 저장소를 사용한다.
- 실사이트·최초 적재: 2026-07-22 KST에 11/11 상품이 모두 `complete`로 파싱·원격 적재됐고 각 상품의 TOP3·기준일·원문 종목 수를 확인했다. 기준일은 SOL·TIGER 2026-07-21, KIWOOM·KODEX·KoAct 2026-07-22였다. 공식 스냅샷 11건·TOP3 항목 33건·성공 수집이력 11건이며 실패·부분·날짜/URL/해시/항목 수 오류는 모두 0건이다.
- 로컬 검증: 관련 ETF 테스트 81 passed, 인덱스 보완 후 스키마 계약 테스트 32 passed, 최종 전체 `uv run pytest` 1008 passed·1 skipped, `uv run ruff check .` 통과, `git diff --check` 통과했다.
- 원격 적용·보안 검증: 이재용 승인에 따라 원격 migration `20260722093206`, `20260722093547`을 적용했다. public 테이블 54/54 RLS, `anon` 0개·`authenticated` 5개·`service_role` 54개 테이블 권한을 재확인했다. 신규 바인딩은 정책 0개·브라우저 GRANT 0개인 서버 전용 deny-by-default 구조다. Advisor의 `rls_enabled_no_policy` INFO는 이 구조에 따른 의도된 알림이고, 보완 인덱스의 `unused_index` INFO는 최초 생성 직후라 유지한다.
- 런타임 E2E: 원격 리포지토리가 승인 코드 11/11의 TOP3를 반환했다. 챗봇 응답 조립은 SOL 3개를 `실제 보유종목 TOP3`, TIGER·KIWOOM·KODEX 표본을 `구성 바스켓 TOP3`로 각각 3개 섹션·3개 출처·9개 수치 근거·한계 0건으로 생성했다.
- 다음 작업: 현재 브랜치의 코드·workflow가 PR로 머지된 뒤 평일 12:40 KST 자동 갱신 첫 실행을 확인하고, 실패 알림·원격 스냅샷 증가를 모니터링한다.

### 2026-07-22 22:40 KST — Bonds theme (REMOTE-APPLIED)

- Migration `20260722133833_add_bond_theme_component_bindings` was applied to `KDA-securities` after approval.
- Added five active official-source bindings: TIGER 2, ACE 2, and KODEX 1; `ace_pdf` is server-only and the existing RLS/GRANT deny-by-default model is unchanged.
- Initial refresh requested 5, succeeded 5, partial 0, failed 0. Each latest snapshot is `complete` and has exactly three stored Top-3 items.
- Remote ChatService E2E selected `453850`, `0046A0`, and `484790` by the current trading-value rule; the follow-up response rendered all three official creation-basket Top-3 sections.
- Existing advisor INFO/WARN notices are unchanged and no new migration-specific security or performance finding was introduced.

### 2026-07-23 KST — ETF dataset v1 removal (REMOTE-APPLIED)

- Branch/commit: `codex/이재용/etf-storage-parquet` / `745ad54` (Draft PR #186).
- Applied migration `20260723024048_delete_etf_dataset_v1`: deletes only dataset `id=1` with `as_of=2026-07-16`; existing cascade removed its child product and return-history rows.
- Before: 3 dataset versions, 7,521 product rows, 2,633,766 return-history rows, database 544 MB.
- After: v2 and v4 remain ready; 5,014 product rows and 2,415,904 return-history rows. The live IRP repository E2E returned 823 products and 823 history codes from v4.
- Physical relation size remained 440 MB immediately after DELETE. Do not run `VACUUM FULL` without a separate maintenance-window decision because it rewrites and exclusively locks the large table.
- Next: provision and verify the Storage S3 direct-read credentials, then run the v4 Parquet parallel-read migration. The return-history table must remain until that gate is complete.

### 2026-07-23 KST — ETF dataset v2 removal (REMOTE-APPLIED)

- Branch/commit: `codex/이재용/etf-storage-parquet` / `b139e7a` (Draft PR #186).
- Applied migration `20260723024952_delete_etf_dataset_v2`: deletes only dataset `id=2` with `as_of=2026-07-20`; v4 was verified as the newest ready version before the deletion.
- v2 and v4 return-history values were equal, while v4 product payload adds current KOFIA/FSC cost and identity evidence. v2 was not a production read target.
- After: only v4 remains ready, with 2,507 product rows and 1,207,952 return-history rows. Database size remains 544 MB immediately after DELETE because dead space is not physically reclaimed.
- The direct repository E2E retry was blocked by the Supabase session-mode pool limit (`pool_size: 15`); this is recorded separately from the data migration. MCP verification confirmed the single ready v4 state.
- Next: decide the maintenance window and safe physical-space recovery method; do not run `VACUUM FULL` opportunistically. Storage + Parquet work remains a separate gate.

### 2026-07-23 KST — ETF return-history space recovery (REMOTE-APPLIED)

- After explicit maintenance approval, ran `VACUUM FULL ANALYZE public.etf_return_histories` through an autocommit administrative connection.
- Database size decreased from 544 MB to 285 MB; `etf_return_histories` total relation size decreased from 440 MB to 182 MB.
- Post-maintenance verification: only ready v4 remains, with 2,507 product rows and 1,207,952 history rows. Direct IRP repository E2E returned v4 (`2026-07-23`), 823 products, and 823 history codes.
- No schema or API response contract changed. Storage + Parquet migration remains pending its separate direct-read credential and parallel-read gates.

### 2026-07-23 KST — 죽은 mock_public·curated_contents 테이블 드롭 (LOCAL-DRAFT)

- 작업자/브랜치/커밋: 이재용 / `claude/이재용/drop-dead-mock-public-tables`
- 시작 상태: 원격 DB 306MB/500MB, 테이블 91개. `20260723043507_annotate_table_domains`가 대상 4종을 `[dead] … 별도 승인 후 드롭 예정`으로 표기해 둔 상태.
- 변경 내용: `20260723061500_drop_dead_mock_public_and_curated_tables` 추가. `mock_public_portfolio_holdings` → `mock_public_portfolios` → `mock_public_profiles` → `curated_contents` 순으로 드롭한다. `seed.sql`에서 mock_public 3종 seed 블록을 제거했다.
- 결정 및 근거: 사전 참조 조사에서 backend/app·scripts·tests 참조 0건을 확인했다. FK 자식→부모 순으로 제거하고 cascade는 쓰지 않아, 예상 밖 의존 객체가 있으면 조용히 지우지 않고 실패하도록 했다. 같은 조사에서 `engine_runs`·`engine_run_evidence`(EngineAuditRepository가 사용), `financial_products`(pension_accounts_repository가 조인), `account_cash_flows`(테스트 참조 + 실계좌 연동 예정 자리)는 살아 있어 드롭 대상에서 제외했다.
- 로컬 검증과 실제 결과: `uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py` 37 passed. `seed.sql` 잔여 mock_public 참조 0건.
- 원격 적용 여부와 migration version: 미적용(LOCAL-DRAFT). 원격 적용은 백업과 이재용 승인 후 별도로 수행한다.
- 남은 위험 또는 blocker: 삭제 직전 행 수는 profiles 3 / portfolios 3 / holdings 9 / curated_contents 0이라 용량 효과는 약 230KB에 불과하다. 이 작업의 목적은 용량 확보가 아니라 스키마 정리다.
- 다음 작업: 원격 적용 승인 후 적용, 적용 직후 테이블 수·행 수·GRANT 재검증.

## 공식 ETF 분배금 원본 보관·증분 갱신 (REMOTE-E2E-VERIFIED)

### 2026-07-24 KST

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/etf-distribution-refresh-implementation` / `origin/main` `3a4e4fb`.
- 변경 내용: private Storage 버킷 `official-etf-distribution-raw`를 만드는 additive migration을 추가하고 적용했다. 원본 SHA-256·파일 크기·1년 보존 종료일을 manifest로 보관하는 서버 전용 어댑터, KIND 45일 정정 창·KIS 120일 예정 창·확정 현금분배금 30% 초과 감소 격리 규칙을 추가했다. 후속 runner는 최신 ready 원본 payload를 읽어 비분배 이벤트를 보존하고, KIND·KIS 보고서와 실제 원본 디렉터리를 private Storage에 업로드한 뒤에만 새 ready 버전을 적재한다.
- 결정 및 근거: 기존 `etf_distribution_event_versions`의 `loading → ready` 전환과 KIND 계산 권위를 변경하지 않는다. `service_role`은 Storage RLS를 우회하므로 별도 `storage.objects` 허용 정책을 만들지 않아 anon/authenticated deny-by-default를 유지한다. Storage는 공개 URL·브라우저 credential을 만들지 않는다.
- 로컬 검증과 실제 결과: runner 관련 `uv run python -m pytest tests/test_etf_distribution_refresh.py tests/test_etf_distribution_event_repository.py tests/test_etf_corporate_events.py` 17 passed, 관련 `ruff check`, `git diff --check`, `uv run python scripts/refresh_etf_distribution_events.py` dry run을 통과했다. 실제 첫 실행에서 DB raw payload의 `date` 직렬화 오류를 재현해 회귀 테스트를 추가했고, 수정 PR #276을 병합했다. 수정 후 전체 `1165 passed, 1 skipped`와 `ruff check .`을 통과했다.
- 원격 적용 여부와 migration version: 이재용 승인 후 MCP가 부여한 원격 migration `20260724022829_create_official_etf_distribution_raw_storage`를 적용했다. 버킷은 `public=false`, `storage.objects` 커스텀 정책은 0건으로 확인했다. 최초 정책 생성 시도는 managed `storage.objects` 소유권 제약으로 실패했고, 원격 객체가 남지 않은 것을 확인한 뒤 정책 없는 deny-by-default migration으로 교정했다.
- 원격 E2E: GitHub Actions `Official ETF distribution refresh` run `30065654222`가 성공했다. private bucket에는 run `20260724T040046Z`의 `manifest.json`을 포함해 원본·보고서 객체 1,396개가 보관됐고, `etf_distribution_event_versions`에는 `id=2`, `as_of=2026-07-24`, `status=ready`, `event_rows=9,861`이 적재됐다. 이전 ready 버전은 `id=1`, 9,615행으로 보존된다.
- 남은 위험 또는 blocker: 1년 만료 삭제는 Supabase Storage lifecycle 기능이 아닌 Storage API 삭제 작업으로 별도 구현·E2E가 필요하다. GitHub Actions 정기 스케줄은 첫 수동 E2E가 통과했으므로, 만료 삭제와 함께 평일 06:30 KST 운영 일정으로 별도 활성화할 수 있다.
- 다음 작업: Storage API로 만료 run을 안전하게 삭제하는 runner·테스트를 추가하고, 운영 승인 후 평일 정기 스케줄을 활성화한다.

## 15. 작업 로그 템플릿

### 2026-07-26 13:53 KST — ETF 유니버스 캐시 원격 보관 (REMOTE-E2E-VERIFIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/etf-cache-ops-handoff` / `origin/main` `7e21fe2`.
- 변경 내용: private Storage 버킷 `official-etf-universe-reference-raw`, `official-etf-universe-cache`를 원격에 적용했다. 후자는 일별 가격·총수익률 캐시의 매 실행 산출물과 manifest, 최신 run 포인터를 보관한다.
- 결정 및 근거: 두 버킷 모두 `public=false`로 유지하고 공개 URL·브라우저 credential·`storage.objects` 사용자 정책을 만들지 않았다. 서버 전용 적재·복원 흐름만 허용해 원본·캐시의 외부 노출 경계를 유지한다.
- 로컬 검증과 실제 결과: `uv run python scripts/archive_etf_universe_cache.py --apply`와 `uv run python scripts/restore_etf_universe_cache.py --apply`를 실행했다. run `20260726T045232Z`에 8개 산출물을 SHA-256·바이트 단위로 검증하며 복원했고, 버킷에는 manifest·latest 포인터를 포함한 객체 10개가 확인됐다. DB 감사는 version `4`, 기준일 `2026-07-23`, 상품 `2,507`, 총수익 이력 `898,190`, 이력 없는 상품 `0`으로 일치했다.
- 원격 적용 여부와 migration version: Supabase MCP로 `create_official_etf_universe_reference_raw_storage`, `create_official_etf_universe_cache_storage`를 적용했다. 두 버킷의 `public=false`를 사후 조회로 확인했다.
- 운영 조치: 유휴 상태가 5분을 넘긴 `postgres` Supavisor 연결 6개만 종료해 session pool 포화를 해소했고, 이후 앱 DB 연결·ETF 감사가 정상 통과했다. 활성 연결과 시스템 역할 연결은 건드리지 않았다.
- 남은 위험 또는 blocker: 공식 원본 XLS의 최초 비공개 등록은 별도 승인·원본 수령이 필요하다. 현재 캐시 아카이브는 정기 워크플로가 복원 후 DB 감사까지 수행하도록 구성되어 있다.
- 다음 작업: 공식 원본 수령 시 reference raw 버킷에 최초 등록하고, 월간 유니버스 갱신 run의 원본 SHA·기준일을 이 문서에 이어 기록한다.

### 2026-07-26 KST — FOMC 과거 이벤트 원장 범위 확장 (LOCAL-VERIFIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/fomc-event-ledger-backfill` / `origin/main` `ed6a0a7`.
- 변경 내용: 공식 Federal Reserve FOMC 기록을 근거로 2011-08-09부터 2025-12-10까지의 명시적 정책 이벤트 30건을 `data/reference/fomc_policy_event_ledger_2011_2025.json`에 추가했다. 각 이벤트는 은행·금융 ETF 3종(`091170`, `091220`, `139270`)만 비교 대상으로 고정하며, 분류·예측·비중 변경 입력으로 사용하지 않는다.
- 결정 및 근거: 기사 제목에서 이벤트를 추론하지 않고 Federal Reserve 공식 연도별 기록·회의 일정 URL만 원장 근거로 사용한다. 기존 `news_event_outcomes`의 2025년 2건도 같은 event key로 포함해 재현 가능한 단일 입력 원장으로 만든다.
- 로컬 검증과 실제 결과: 원장 계약·사후성과 엔진 테스트 `5 passed`, Ruff·`git diff --check`를 통과했다. 원격 총수익률을 읽기 전용으로 계산한 결과 90개 이벤트-ETF 쌍 중 48개는 1·3·6개월 성과가 모두 산출됐고, 42개는 기존 총수익률 이력 시작일 이전이라 126개 구간이 `outcome_precedes_history_coverage`으로 남았다. 결측 경계를 보간하지 않았다.
- 원격 적용 여부와 migration version: 원장 파일·테스트만 추가한 LOCAL-VERIFIED 상태다. `news_event_outcomes` 원격 적재는 PR 병합 및 이재용 승인 후 별도 실행한다.
- 남은 위험 또는 blocker: 2011~2019 14개 이벤트의 결과를 카드에 넣으려면 해당 ETF의 공식 총수익률 이력 백필이 먼저 필요하다. 현재 검증된 2020~2025 구간만 적재 후보로 유지한다.
- 다음 작업: 승인된 원장을 기준으로 2020~2025 48개 완결 쌍의 보고서를 생성·적재하고, 오래된 이력 백필 후 같은 명령으로 2011~2019 결측을 재평가한다.

### 2026-07-26 KST — FOMC 과거 사후성과 원격 적재 (REMOTE-APPLIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/fomc-event-ledger-remote-load` / `origin/main` `aaedf08`.
- 변경 내용: 병합된 `fomc_policy_event_ledger_2011_2025.json`을 원격 ETF 총수익률로 계산해, 완결된 2020~2025 FOMC 이벤트의 1·3·6개월 사후성과를 `news_event_outcomes`에 upsert했다.
- 결정 및 근거: 입력 원장 30건 중 기존 총수익률 이력 시작일 이전의 2011~2019 구간은 보간하지 않고 제외했다. 적재 결과는 과거 설명 카드 전용이며 계획수익률·비중 변경·리밸런싱 신호에는 사용하지 않는다.
- 로컬 검증과 실제 결과: `build_news_event_outcome_ledger.py`는 30개 이벤트·90개 이벤트-ETF 쌍을 평가해 검증된 horizon 144개를 생성했고, `load_news_event_outcome_ledger.py --apply`가 144행을 적재했다. 임시 보고서는 적재 후 삭제했다.
- 원격 적용 여부와 migration version: schema 변경 없는 REMOTE-APPLIED 데이터 적재다. Supabase 사후 조회에서 FOMC 원장 행 144, 이벤트 16, 이벤트-ETF 쌍 48, horizon `[1, 3, 6]`을 확인했다.
- 남은 위험 또는 blocker: 2011~2019 14개 이벤트·42개 이벤트-ETF 쌍은 공식 총수익률 이력 백필 전까지 `outcome_precedes_history_coverage`으로 유지한다.
- 다음 작업: 오래된 수정주가·분배금 원본을 확보하면 같은 원장을 재실행해 결측 구간만 추가 적재하고, 별도 원장 검토 절차로 FOMC 외 공식 이벤트를 확장한다.

### 2026-07-26 KST — FOMC 2011~2019 KIS·KIND 결합 백필 준비 (LOCAL-VERIFIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/fomc-kis-history-backfill` / `origin/main` `60a7b85`.
- 변경 내용: KIS 수정주가 수집기를 3개 은행·금융 ETF에 2011-01-01~2020-06-30 범위로 실행해 6,951개 관측을 원본·캐시로 보관했다. KIND 2011-01-01~2026-07-16 현금분배·분배락 원본과 결합해 같은 ETF의 총수익률 근거를 만들었다.
- 결정 및 근거: `--local-cache`와 `--through-date` 옵션을 원장 생성기에 추가해, DB 기반 기본 경로를 유지하면서도 명시적 KIS·KIND 캐시와 이벤트 상한으로 증분 백필을 재현한다. 가격 이력만으로 현금분배를 추정하지 않고 KIND 현금분배를 결합한다.
- 로컬 검증과 실제 결과: 생성기·사후성과 테스트 `7 passed`, Ruff·`git diff --check`를 통과했다. `--through-date 2019-12-31` E2E는 FOMC 이벤트 14건·이벤트-ETF 쌍 42건·검증된 1·3·6개월 결과 126행을 생성했고 gap은 0건이었다.
- 원격 적용 여부와 migration version: LOCAL-VERIFIED 상태다. 새 스키마 migration은 없고, 원격 `news_event_outcomes` 126행 upsert는 PR 병합과 이재용 승인 후 별도 실행한다.
- 남은 위험 또는 blocker: 수집 첫 재시도에서 KIS 토큰 발급 HTTP 403이 있었으나, 충분한 간격 뒤 한 번의 3종 배치로 정상 수집했다. 정기 운영은 같은 실행에서 토큰을 한 번만 발급·재사용해야 한다.
- 다음 작업: PR 병합 후 생성 보고서를 원격 원장에 upsert하고, 2020~2025 기존 144행과 합쳐 FOMC 전체 270행을 사후 조회로 검증한다.

### 2026-07-26 14:50 KST — FOMC 2011~2019 KIS·KIND 결합 결과 원격 적재 (REMOTE-APPLIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/fomc-event-legacy-remote-load` / `origin/main` `8447050`.
- 시작 상태: `news_event_outcomes`의 FOMC 결과는 144행·이벤트 16건·이벤트-ETF 쌍 48건·horizon `[1, 3, 6]`이었다. 이는 2020~2025 구간만 적재된 상태다.
- 변경 내용: 이전에 KIS 수정주가·KIND 현금분배 결합으로 검증한 2011~2019 보고서를 `scripts/load_news_event_outcome_ledger.py --apply`로 멱등 upsert해 126행을 추가했다. 스키마·RLS·권한·계산식은 변경하지 않았다.
- 결정 및 근거: 적재 대상은 FOMC 원장에 있는 14개 공식 정책 이벤트와 고정된 은행·금융 ETF 3종의 과거 1·3·6개월 총수익률·최대낙폭·동일 ETF군 중앙값이다. 결과는 챗봇의 과거 근거 카드에만 사용하며, 계획수익률·자동 비중 변경·매매 또는 리밸런싱 신호에는 사용하지 않는다.
- 로컬 검증과 실제 결과: 보고서에는 이벤트 14건·이벤트-ETF 쌍 42건·horizon 결과 126행·gap 0건이 포함된 것을 확인했다. 현재 원본 캐시만으로 보고서를 다시 생성하려 한 경로는 비용-수익률 마스터 부재로 중단됐으며, 이미 `LOCAL-VERIFIED`로 기록한 결합 보고서만 적재에 사용했다. 원격 loader 출력은 `loaded_outcome_rows: 126`이다.
- 원격 적용 여부와 migration version: schema 변경 없는 REMOTE-APPLIED 데이터 적재다. Supabase 사후 조회에서 FOMC 결과 270행·이벤트 30건·이벤트-ETF 쌍 90건·horizon `[1, 3, 6]`·최초 이벤트 `2011-08-09`·최신 이벤트 `2025-12-10`을 확인했다.
- 남은 위험 또는 blocker: 이번 백필 범위의 FOMC 결과는 완결됐다. FOMC 외 공식 이벤트 확장은 별도 이벤트 원장 검토와 동일한 공식 가격·분배금 근거 확인이 필요하다.
- 다음 작업: 챗봇 근거 카드의 30개 FOMC 이벤트 노출을 실제 환경에서 점검하고, 이후 이벤트 범위를 추가할 때만 같은 검증·적재 절차를 재사용한다.

### 2026-07-26 15:10 KST — 한국은행 기준금리 변경 사후성과 원격 적재 (REMOTE-APPLIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/bok-rate-event-remote-load` / `origin/main` `c56906f`.
- 시작 상태: `news_event_outcomes`에는 FOMC 결과 270행만 있었고, 한국은행 기준금리 변경 이벤트 결과는 0행이었다.
- 변경 내용: 병합된 `bok_base_rate_change_event_ledger_2011_2025.json`의 31개 공식 기준금리 변경을 기존 총수익률 이력으로 평가해, 근거가 완결된 16개 이벤트 × ETF 3종 × 1·3·6개월 결과 144행을 멱등 upsert했다. 스키마·RLS·권한·계산식은 변경하지 않았다.
- 결정 및 근거: 2011~2025 이벤트 31건 중 이전 이력 범위가 부족한 15개 이벤트의 135개 horizon은 보간하거나 추정하지 않고 제외했다. 적재 결과는 챗봇의 과거 근거 카드에만 사용하며 계획수익률·자동 비중 변경·매매 또는 리밸런싱 신호에는 사용하지 않는다.
- 로컬 검증과 실제 결과: `build_news_event_outcome_ledger.py`가 이벤트-ETF 쌍 93건에서 검증 결과 144행을 산출했고, `load_news_event_outcome_ledger.py --apply`가 144행을 적재했다.
- 원격 적용 여부와 migration version: schema 변경 없는 REMOTE-APPLIED 데이터 적재다. Supabase 사후 조회에서 BOK 결과 144행·이벤트 16건·이벤트-ETF 쌍 48건·horizon `[1, 3, 6]`, FOMC 결과 270행, 전체 결과 414행을 확인했다.
- 남은 위험 또는 blocker: 현재 챗봇 카드의 읽기 상한은 300행이므로, FOMC+BOK 전체 414행을 정확한 범위 요약에 반영하려면 조회 상한 또는 요약 조회를 별도 보완해야 한다.
- 다음 작업: 카드의 검증 범위 집계를 전체 원장 기준으로 보완하고, 이후 다른 공식 이벤트 원장을 추가할 때도 동일한 결측 보류 원칙을 유지한다.

### 2026-07-26 KST — FOMC 정례·긴급회의 원장 확장 및 사후성과 적재 (REMOTE-APPLIED)

- 작업자/브랜치/시작 기준: 김태형 / `codex/김태형/fomc-meeting-ledger-expansion` / `origin/main` `f5dbd1a`.
- 시작 상태: FOMC 원장은 2011~2025 공식 정책 이벤트 30건, 원격 `news_event_outcomes`는 FOMC 270행·이벤트 30건·이벤트-ETF 쌍 90건이었다.
- 변경 내용: Federal Reserve 공식 FOMC 기록과 회의 일정을 근거로 2020년 긴급회의 1건과 2020~2025 정례회의의 누락 32건을 추가해 원장을 63건으로 확장했다. 기존 은행·금융 ETF 3종과 과거 1·3·6개월 총수익률·최대낙폭·동일 ETF군 중앙값 계산은 그대로 유지했다.
- 결정 및 근거: 자동 뉴스 제목 분류가 아니라 Federal Reserve의 2020년 역사 기록과 2021~2025 회의 일정에 명시된 발표일만 사용했다. 결과는 챗봇의 과거 설명 카드에만 사용하며 계획수익률·자동 비중 변경·주문·리밸런싱 신호에는 연결하지 않는다.
- 로컬 검증과 실제 결과: KIS 수정주가와 KIND 현금분배 결합 캐시로 63개 이벤트·189개 이벤트-ETF 쌍을 평가했다. 2020~2025 재계산 보고서는 검증된 horizon 441행을 만들었고, 2011~2019의 기존 원격 백필 126행은 유지했다. 원장 계약 테스트와 사후성과 엔진 테스트를 통과했고 Ruff·`git diff --check`를 실행했다.
- 원격 적용 여부와 migration version: schema 변경 없는 REMOTE-APPLIED 데이터 upsert다. `load_news_event_outcome_ledger.py --apply`가 441행을 멱등 처리했으며, Supabase 사후 조회에서 FOMC 결과 567행·이벤트 63건·이벤트-ETF 쌍 189건·horizon `[1, 3, 6]`·최초 `2011-08-09`·최신 `2025-12-10`을 확인했다.
- 남은 위험 또는 blocker: 이 원장은 통화정책의 공식 FOMC 사건만 확장한 범위다. 다른 주제는 같은 수준의 공식 발생일·테마별 비교 ETF군·총수익률 근거가 검토된 별도 원장이 생길 때만 추가한다.
- 다음 작업: 챗봇은 기존 전체 원장 조회·대표 행 표시를 그대로 사용한다. 새 공식 사건군을 추가할 때는 원장 계약 테스트·결측 감사·원격 행 수 검증을 같은 절차로 수행한다.

```markdown
### YYYY-MM-DD HH:mm KST

- 작업자/브랜치/커밋:
- 시작 상태:
- 변경 내용:
- 결정 및 근거:
- 로컬 검증과 실제 결과:
- 원격 적용 여부와 migration version:
- 남은 위험 또는 blocker:
- 다음 작업:
```
