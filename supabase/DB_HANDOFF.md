# 연금 코파일럿 DB 작업 핸드오프

> DB 작업의 단일 현황판이자 인수인계 문서다. 작업자는 시작 전 읽고, 의미 있는 변경을 마칠 때마다 이 문서를 최신화한다.
>
> 최종 확인: 2026-07-16 09:21 KST
> 확인 기준: `codex/db-handoff-integration` / 최신 `main` `f01934e` 위 DB 통합 변경
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
4. 이 문서
5. [`migrations/`](./migrations) 전체를 시간순으로 읽고 [`seed.sql`](./seed.sql) 확인
6. DB 변경과 맞닿는 엔진 모델·저장소·API·테스트 확인

참고 설계 원본: [`연금_코파일럿_DB_설계.pdf`](../연금_코파일럿_DB_설계.pdf)

## 3. 현재 원격 상태

2026-07-16 KST에 연결된 Supabase 프로젝트를 읽기 전용으로 재확인했다.

| 항목 | 원격 상태 |
|---|---|
| public 기본 테이블 | 25개 |
| 적용 마이그레이션 | `20260715005435`, `20260715021243`, `20260715103332`, `20260715103542`, `20260715165614` |
| RLS | 25/25 활성화 |
| `anon` 테이블 권한 | 없음 |
| `authenticated` 권한 | 사용자 소유 엔진 결과·채팅 관련 5개 테이블 |
| `service_role` 권한 | 25개 테이블 |
| `knowledge_chunks.embedding` 타입 | `vector(1024)` |
| HNSW 인덱스 | `knowledge_chunks_embedding_hnsw_idx` 존재 |
| PostgreSQL / 프로젝트 상태 | 17.6 / `ACTIVE_HEALTHY` |

### 원격 주요 행 수

| 테이블 | 행 수 |
|---|---:|
| `pension_savings_provider_stats` | 88 |
| `retirement_provider_stats` | 126 |
| `financial_institutions` | 102 |
| `news_items` | 10 |
| `knowledge_documents` | 1 |
| `knowledge_chunks` | 1 |
| `mock_scenarios` | 3 |
| `mock_accounts` | 6 |
| `mock_holdings` | 10 |

`knowledge_chunks` 1건은 이미 `embedding_dimensions=1024`이며 embedding 값도 존재한다.

### 현재 25개 테이블의 역할

| 영역 | 테이블 |
|---|---|
| 출처·수집 | `data_sources`, `ingestion_runs` |
| 금융기관·공시 | `financial_institutions`, `institution_aliases`, `pension_savings_provider_stats`, `retirement_provider_stats` |
| 자산·목계좌 | `asset_classes`, `mock_scenarios`, `mock_accounts`, `mock_holdings` |
| 목 벤치마크 | `mock_public_profiles`, `mock_public_portfolios`, `mock_public_portfolio_holdings` |
| 규칙·감사 | `rule_sets`, `pension_rules`, `engine_runs`, `engine_run_evidence` |
| RAG·뉴스 | `knowledge_documents`, `knowledge_chunks`, `news_items`, `curated_contents` |
| 채팅 | `chat_sessions`, `chat_messages`, `chat_message_evidence`, `chat_request_idempotency` |

## 4. 현재 작업트리의 진행 중 작업

`codex/db-handoff-integration`에서 다음 범위만 작업한다.

- 최신 `main`의 `20260715103332`, `20260715103542` 파일이 원격 migration history와 일치하는지 유지·검증한다.
- `20260716001737_add_user_pension_domain.sql`에 승인된 사용자·성향·계좌 도메인을 additive DDL로 추가한다.
- 기존 `mock_accounts`, `mock_holdings`, 목시나리오, 공시·RAG·채팅 데이터는 수정하거나 삭제하지 않는다.
- 신규 도메인 마이그레이션은 로컬 검증과 PR까지만 진행한다. 원격 적용은 이재용 승인 후 별도 수행한다.

### 임베딩 마이그레이션 주의사항

- `20260715165614_fix_embedding_dimension_bge_m3.sql`은 이미 원격 적용됐다.
- 원격 non-null embedding은 1건이고 1024차원이며, HNSW 인덱스도 존재한다.
- 적용된 파일의 "기존 embedding 값은 전부 null" 주석은 원격 적용 직전 사실과 달랐지만, 적용 이력 파일은 수정하지 않는다. 이 문서에 사실 차이만 기록한다.
- 현재 원격 상태는 `vector(1024)` 1건, 비정상 차원 0건이다.

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

- 세 시나리오, 6개 계좌, 10개 보유내역을 신규 공통 계좌 구조로 backfill한다.
- 기존 `mock_accounts.balance_krw`와 holdings 합계가 일치하는지 마이그레이션 전후에 검증한다.
- 목상품은 synthetic 출처를 명확히 남기거나 product FK가 아직 없을 때 raw instrument name을 보존한다.
- 필수 reference data와 backfill SQL은 원격에도 적용되도록 마이그레이션에 포함하고, 로컬 reset용 `seed.sql`도 멱등하게 맞춘다.

### 제거 후보

- `mock_accounts`, `mock_holdings`만 최종 제거 후보이다.
- 첫 마이그레이션에서는 삭제하지 않는다.
- 신규 저장소 전환, 세 시나리오 엔진 결과 동등성, 전체 참조 제거를 확인한 뒤 별도 cleanup 마이그레이션에서 삭제한다.
- `data/mock/chatbot_scenarios.json`은 DB 미연결 개발·테스트 fallback으로 유지하되 실행 시점의 두 번째 SSOT가 되지 않게 한다.

## 8. 백엔드 연동 계획

현재 `/engine/mock-scenario/{scenario_code}`와 챗봇은 `LocalScenarioRepository`를 통해 `data/mock/chatbot_scenarios.json`을 읽는다.

1. `ScenarioRepository` 프로토콜을 정의한다.
2. `PostgresScenarioRepository`를 추가해 신규 DB 행을 기존 `ScenarioPortfolioInput`으로 변환한다.
3. API와 챗 서비스에서 저장소를 직접 생성하지 않고 dependency injection으로 받는다.
4. DB 연결 시 Postgres 저장소를 사용하고, DB 미연결 개발 환경에서는 `LocalScenarioRepository`를 사용한다.
5. 사용자 계좌 조회 저장소는 DB 행을 `AccountInput`·`AggregationInput`으로 변환한다.
6. 성향 저장 API는 입력을 `ProfileSurveyInput`으로 검증한 뒤 규칙 엔진 결과와 버전을 저장한다.
7. 규칙 엔진은 순수 함수로 유지하고 Supabase 의존성을 추가하지 않는다.
8. 계산 결과·규칙·출처 연결은 기존 `engine_runs`·`engine_run_evidence`를 재사용한다.

공유 REST·엔진 I/O·상품 테이블 계약을 바꾸는 PR에는 `계약 변경`을 명시하고 관련 담당자의 합의를 받는다.

## 9. 마이그레이션 절차

1. 작업 시작 시 최신 `main`, dirty 파일, 원격 migration history를 확인한다.
2. Supabase 최신 changelog와 관련 공식 문서를 확인한다.
3. 로컬 전역 CLI가 없으면 `npx.cmd --yes supabase`를 사용하고 실제 명령 도움말을 확인한다.
4. 새 마이그레이션 파일은 CLI의 `supabase migration new <name>`으로 생성한다. 적용된 다섯 마이그레이션은 수정하지 않는다.
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
- 3개 목시나리오의 계좌 합계, 위험자산 비율, 한도 판정, 자산군 비중이 이전 결과와 동일하다.
- 5단계 성향 코드와 현재 6개 질문 코드가 Python 모델·seed·DB CHECK에서 동일하다.
- 사용자 A가 사용자 B의 프로필·계좌·진단을 읽거나 변경할 수 없는지 검증한다.
- 수익률 계산은 현금흐름 전후 케이스를 포함한다.

### 원격

- migration history에 승인된 버전만 존재한다.
- RLS, role별 GRANT, 정책 predicate, FK, CHECK, unique index를 카탈로그에서 재검증한다.
- backfill 전후 3/6/10 건수와 금액 합계가 일치한다.
- FastAPI를 통한 Auth 사용자 경로와 목시나리오 fallback을 각각 E2E 검증한다.
- `supabase db advisors` 또는 MCP advisors 결과의 보안·성능 경고를 검토한다.

## 12. 작업 상태표

| ID | 작업 | 상태 | 완료 조건 | 다음 행동 |
|---|---|---|---|---|
| DB-00 | BGE-M3 1024차원·HNSW 마이그레이션 | `REMOTE-APPLIED` | 원격 1024차원·HNSW·migration history 확인 | 적용 파일 수정 금지 |
| DB-01 | 사용자·성향·계좌 스키마 승인 | `LOCAL-VERIFIED` | `user_profiles`, 현금흐름 포함, 커뮤니티 제외, 매핑 보류 확정 | PR 리뷰 |
| DB-02 | Additive domain migration | `LOCAL-VERIFIED` | DDL·RLS·GRANT·인덱스·계약 테스트 통과 | 이재용 승인 후 원격 적용 |
| DB-03 | 문항·목계좌 backfill | `LOCAL-DRAFT` | 3/6/10 및 금액·엔진 결과 동등 | 별도 migration 작성 |
| DB-04 | Postgres repository·API 연결 | `LOCAL-DRAFT` | DB 우선·JSON fallback·E2E 통과 | DB-03 후 구현 |
| DB-05 | 기존 mock account tables 정리 | `BLOCKED` | 코드·SQL 참조 0, 별도 승인·복구 계획 | DB-04 안정화 전 삭제 금지 |
| DB-06 | 커뮤니티 리뷰 | `BLOCKED` | 포트폴리오 FK·RLS·신고·보존 정책 승인 | 핵심 계좌 연동 후 검토 |

## 13. 미결정 사항

- DB 작업의 실명 담당자와 폴더 소유권: `TODO: 확인 필요`.
- 사용자 프로필 명칭은 `user_profiles`로 확정.
- 실제 계좌 연동 방식과 provider import 원천: `TODO: 확인 필요`. 현재 사용자 계좌는 목데이터만 허용된다.
- 3단계 목시나리오 성향과 5단계 진단 성향 매핑: 팀 승인 전 미구현.
- `account_cash_flows`는 과거 수익률 계산의 현금흐름 입력을 위해 첫 스키마에 포함.
- 상품 마스터를 제공할 공식 product-level API: 현재 FSS 데이터는 provider-level이므로 별도 확인 필요.
- 커뮤니티 리뷰의 실제 사용자 대상 공개 시점과 보존·신고 정책: 후속 결정.

## 14. 작업 로그

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
