# 연금 코파일럿 DB 작업 핸드오프

> DB 작업의 단일 현황판이자 인수인계 문서다. 작업자는 시작 전 읽고, 의미 있는 변경을 마칠 때마다 이 문서를 최신화한다.
>
> 최종 확인: 2026-07-19 01:21 KST
> 확인 기준: `codex/supabase-current-state-docs` / `origin/main` `c7e097f` / Supabase MCP·원격 FastAPI E2E 재검증
> 원격 프로젝트: `KDA-securities`
> 담당자: `TODO: 확인 필요`
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

2026-07-19 KST에 승인된 COMMENT migration을 적용한 뒤 연결된 Supabase 프로젝트를 읽기 전용으로 재확인했다.

| 항목 | 원격 상태 |
|---|---|
| public 기본 테이블 | 43개 |
| 적용 마이그레이션 | 16개(`20260715005435` ~ `20260718154819`) |
| RLS | 43/43 활성화 |
| `anon` 테이블 권한 | 없음 |
| `authenticated` 권한 | 사용자 소유 엔진 결과·채팅 관련 5개 테이블 |
| `service_role` 권한 | 43개 테이블 |
| `knowledge_chunks.embedding` 타입 | `vector(1024)` |
| HNSW 인덱스 | `knowledge_chunks_embedding_hnsw_idx` 존재 |
| PostgreSQL / 프로젝트 상태 | 17.6 / `ACTIVE_HEALTHY` |
| Supabase MCP 현재 연결 | 마지막 정리 조회에서 `401 token_revoked`; 재인증 필요 |

### 원격 주요 행 수

| 테이블 | 행 수 |
|---|---:|
| `pension_savings_provider_stats` | 88 |
| `retirement_provider_stats` | 126 |
| `financial_institutions` | 102 |
| `news_items` | 15 |
| `knowledge_documents` | 10 |
| `knowledge_chunks` | 45 |
| `mock_scenarios` | 6 |
| `mock_accounts` | 13 |
| `mock_holdings` | 26 |
| `demo_user_financial_context` | 6 |
| `benchmark_mock_users` | 10,000 |
| `benchmark_mock_accounts` | 16,900 |
| `benchmark_mock_holdings` | 79,381 |
| `profile_question_sets` / `profile_questions` / `profile_question_options` | 1 / 6 / 30 |
| `pension_accounts` / `account_snapshots` / `account_cash_flows` / `financial_products` / `account_holding_snapshots` | 모두 0 |

원격에서 직접 수정된 시나리오 설명 5건과 대표 고객 납입액 5건은 `20260718131917_sync_modified_mock_data.sql`로 migration history에 정식 반영했다. 적용 전후 값과 `updated_at`이 모두 같아 데이터 재기록 없이 이력만 정상 추가됐음을 확인했다.

원격 컬럼 설명 3건(`pension_savings_provider_stats.fee_rate_1y`, `retirement_provider_stats.response_division`, `knowledge_chunks.embedding`)은 `20260718154819_repair_corrupted_column_comments.sql`로 교정했다. 실제 설명을 재조회해 목표 문구와 일치하고 U+FFFD 대체문자가 없음을 확인했다. 테이블·컬럼·데이터·RLS·GRANT는 바뀌지 않았다.

### 현재 43개 테이블의 역할

| 영역 | 테이블 |
|---|---|
| 출처·수집 | `data_sources`, `ingestion_runs` |
| 금융기관·공시 | `financial_institutions`, `institution_aliases`, `pension_savings_provider_stats`, `retirement_provider_stats` |
| 자산·목계좌 | `asset_classes`, `mock_scenarios`, `mock_accounts`, `mock_holdings` |
| 목 벤치마크 | `mock_public_profiles`, `mock_public_portfolios`, `mock_public_portfolio_holdings` |
| 규칙·감사 | `rule_sets`, `pension_rules`, `engine_runs`, `engine_run_evidence` |
| RAG·뉴스 | `knowledge_documents`, `knowledge_chunks`, `news_items`, `curated_contents` |
| 채팅 | `chat_sessions`, `chat_messages`, `chat_message_evidence`, `chat_request_idempotency` |
| 사용자·성향·계좌 | `user_profiles`, `profile_question_sets`, `profile_questions`, `profile_question_options`, `investment_profile_assessments`, `investment_profile_answers`, `pension_accounts`, `account_snapshots`, `account_cash_flows`, `financial_products`, `account_holding_snapshots` |
| ETF 유니버스 | `etf_dataset_versions`, `etf_universe_products`, `etf_return_histories` |

## 4. 현재 작업트리의 진행 중 작업

`codex/supabase-current-state-docs` 브랜치의 `C:\dev\kda-supabase-comments` 전용 worktree에서 원격 적용 후 버전 정합화, 런타임 E2E, 문서 최신화를 작업한다.

- MCP가 실행 시각 버전 `20260718154819`를 부여해 로컬 파일명을 같은 버전으로 정합화했다. SQL SHA-256 `DF0E4E...25E6925DF`는 변경 전후 같다.
- `20260718154819_repair_corrupted_column_comments.sql`은 `COMMENT ON COLUMN` 3문만 포함하며 이미 원격 적용됐다.
- [`DB_SESSION_GUIDE.md`](./DB_SESSION_GUIDE.md)는 고정 운영 절차, 이 문서는 동적 상태 SSOT로 분리한다.
- 원격 migration 적용 승인은 이번 요청으로 충족했지만 PR 머지는 별도 명시적 승인 전까지 금지한다.

### 임베딩 마이그레이션 주의사항

- `20260715165614_fix_embedding_dimension_bge_m3.sql`은 이미 원격 적용됐다.
- 원격 non-null embedding은 45건이고 모두 1024차원이며, HNSW 인덱스도 존재한다.
- 적용된 파일의 "기존 embedding 값은 전부 null" 주석은 원격 적용 직전 사실과 달랐지만, 적용 이력 파일은 수정하지 않는다. 이 문서에 사실 차이만 기록한다.
- 원격 migration history의 해당 버전은 statements 배열이 비어 있다(statement count 0). 과거 이력을 repair하거나 조작하지 않는 legacy 예외로 유지한다.
- 현재 원격 상태는 `vector(1024)` 45건, 비정상 차원 0건이다.

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
| DB-03 | 공통 계좌 구조 backfill | `LOCAL-DRAFT` | 기존 6/13/26을 `pension_accounts`·snapshot·holding 구조로 이관하고 금액·엔진 결과 동등 | 별도 additive migration·계약 테스트 작성 |
| DB-03A | 생애주기 대표 고객·Auth 준비 | `REMOTE-APPLIED` | 시나리오 6·계좌 13·보유 26, synthetic demo Auth 사용자 6개 존재 | 데모 로그인 smoke는 다음 인증 가능 세션에서 재검증 |
| DB-03B | 원격 직접 수정 목데이터 Git 동기화 | `REMOTE-APPLIED` | `20260718131917`, 시나리오 설명 5건·대표 고객 납입액 5건 일치·재적용 시 무변경 확인 | 적용 파일 수정 금지 |
| DB-04 | 챗봇 Postgres scenario repository 연결 | `LOCAL-VERIFIED` | DB 우선·JSON fallback과 원격 채팅 저장·replay E2E 통과 | `/engine/mock-scenario` DB 전환 여부 별도 결정 |
| DB-04A | 사용자 연금계좌 repository·API 연결 | `LOCAL-DRAFT` | 신규 공통 계좌 구조 조회·Auth 소유권·엔진 입력 변환 E2E | DB-03 backfill 후 구현 |
| DB-05 | 기존 mock account tables 정리 | `BLOCKED` | 코드·SQL 참조 0, 별도 승인·복구 계획 | DB-04 안정화 전 삭제 금지 |
| DB-06 | 커뮤니티 리뷰 | `BLOCKED` | 포트폴리오 FK·RLS·신고·보존 정책 승인 | 핵심 계좌 연동 후 검토 |
| DB-07 | ETF 포트폴리오 유니버스 스키마·조회 연결 | `REMOTE-APPLIED` | `20260717054500`, 상품 2,507행·이력 217,833행·RLS/권한·120개 동등성·API E2E 확인 | 적용 파일 수정 금지, 다음 데이터 버전 적재 시 ready 전환 계약 유지 |
| DB-08 | 손상된 컬럼 설명 3건 교정 | `REMOTE-APPLIED` | `20260718154819`, COMMENT 3문 전용·실제 설명·불변식 재조회 | 적용 파일 수정 금지 |
| DB-09 | Auth 유출 비밀번호 보호 | `BLOCKED` | Security Advisor의 `auth_leaked_password_protection` WARN 제거 | Supabase Dashboard 또는 CLI 로그인 후 `password_hibp_enabled` 활성화·Advisor 재조회 |
| DB-10 | main 원격 DB 런타임 회귀 | `LOCAL-VERIFIED` | Auth/RLS·채팅 persist/replay·RAG·뉴스·공시·ETF·NAVER rollback-only SQL E2E 통과 | main 변경 시 재실행 |

## 13. 미결정 사항

- DB 작업의 실명 담당자와 폴더 소유권: `TODO: 확인 필요`.
- 사용자 프로필 명칭은 `user_profiles`로 확정.
- 실제 계좌 연동 방식과 provider import 원천: `TODO: 확인 필요`. 현재 사용자 계좌는 목데이터만 허용된다.
- 3단계 목시나리오 성향과 5단계 진단 성향 매핑: 팀 승인 전 미구현.
- `account_cash_flows`는 과거 수익률 계산의 현금흐름 입력을 위해 첫 스키마에 포함.
- 상품 마스터를 제공할 공식 product-level API: 현재 FSS 데이터는 provider-level이므로 별도 확인 필요.
- 커뮤니티 리뷰의 실제 사용자 대상 공개 시점과 보존·신고 정책: 후속 결정.

## 14. 작업 로그

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

## 15. 작업 로그 템플릿

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
