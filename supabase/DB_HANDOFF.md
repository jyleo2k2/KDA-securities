# 연금 코파일럿 DB 작업 핸드오프

> DB 작업의 단일 현황판이자 인수인계 문서다. 작업자는 시작 전 읽고, 의미 있는 변경을 마칠 때마다 이 문서를 최신화한다.
>
> 최종 확인: 2026-07-15 17:21 KST
> 확인 기준: `main` / `bccaae3` / dirty worktree
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

2026-07-15 17:12 KST에 `.env`의 URL을 출력하지 않고 읽기 전용 SQL로 확인했다.

| 항목 | 원격 상태 |
|---|---|
| public 기본 테이블 | 24개 |
| 적용 마이그레이션 | `20260715005435`, `20260715021243` |
| RLS | 24/24 활성화 |
| `anon` 테이블 권한 | 없음 |
| `authenticated` 권한 | 사용자 소유 엔진 결과·채팅 관련 5개 테이블 |
| `service_role` 권한 | 24개 테이블 |
| `knowledge_chunks.embedding` 타입 | 차원 미고정 `vector` |
| HNSW 인덱스 | 없음 |

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

### 현재 24개 테이블의 역할

| 영역 | 테이블 |
|---|---|
| 출처·수집 | `data_sources`, `ingestion_runs` |
| 금융기관·공시 | `financial_institutions`, `institution_aliases`, `pension_savings_provider_stats`, `retirement_provider_stats` |
| 자산·목계좌 | `asset_classes`, `mock_scenarios`, `mock_accounts`, `mock_holdings` |
| 목 벤치마크 | `mock_public_profiles`, `mock_public_portfolios`, `mock_public_portfolio_holdings` |
| 규칙·감사 | `rule_sets`, `pension_rules`, `engine_runs`, `engine_run_evidence` |
| RAG·뉴스 | `knowledge_documents`, `knowledge_chunks`, `news_items`, `curated_contents` |
| 채팅 | `chat_sessions`, `chat_messages`, `chat_message_evidence` |

## 4. 현재 작업트리의 진행 중 작업

다음 변경은 이 핸드오프 문서를 만든 작업이 아니라 다른 팀원의 진행 중 작업이다. 소유자를 확인하기 전 수정·삭제·되돌리기 금지.

### 수정 파일

- `backend/app/api/deps.py`
- `backend/app/chat/narrator.py`
- `backend/app/retrieval/repository.py`
- `docs/30_스펙/아키텍처.md`
- `pyproject.toml`
- `tests/test_embedded_sql.py`
- `tests/test_chat_mvp.py`
- `tests/test_schema_contract.py`
- `uv.lock`

### 신규 파일

- `backend/app/ingestion/embeddings.py`
- `scripts/apply_embedding_migration.py`
- `scripts/embed_knowledge_chunks.py`
- `supabase/migrations/20260715165614_fix_embedding_dimension_bge_m3.sql`
- `tests/test_embeddings.py`

### 임베딩 마이그레이션 주의사항

- 로컬 마이그레이션 `20260715165614_fix_embedding_dimension_bge_m3.sql`은 원격에 아직 적용되지 않았다.
- 원격 컬럼은 차원 미고정 `vector`이고 HNSW 인덱스가 없다.
- 원격에는 이미 1024차원 embedding 1건이 있다. 마이그레이션의 "기존 embedding 값은 전부 null" 주석은 현재 원격 사실과 다르다.
- 적용 전 모든 non-null embedding의 차원이 1024인지 검사하고, 잘못된 주석을 소유자와 협의해 수정해야 한다.
- `scripts/apply_embedding_migration.py`는 SQL을 직접 실행하고 `supabase_migrations.schema_migrations`를 수동 기록한다. 이재용 직접 실행용으로 명시돼 있으므로 소유자 승인과 SQL·history 기록 검토 없이 실행하지 않는다.
- 이 임베딩 변경과 사용자 계좌 도메인 변경은 서로 다른 PR·마이그레이션으로 유지한다.

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

아래 이름과 분할은 구현 권장안이다. DDL 작성 전 담당자와 이재용의 승인이 필요하다.

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
| `community_reviews` | 공개 포트폴리오 리뷰 | owner, portfolio FK, rating 1~5, `deleted_at` soft delete |

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

1. 현재 dirty 파일의 소유자와 임베딩 PR 상태를 확인한다. 소유자 확인 전 해당 변경을 건드리지 않는다.
2. Supabase 최신 changelog와 관련 공식 문서를 확인한다.
3. CLI를 사용할 경우 `supabase --help`로 실제 명령을 확인한다. 현재 이 셸에는 Supabase CLI가 설치되어 있지 않았다.
4. 새 마이그레이션 파일은 CLI의 `supabase migration new <name>`으로 생성한다. 적용된 두 마이그레이션은 수정하지 않는다.
5. 첫 PR은 additive DDL, 인덱스, RLS, GRANT, reference seed만 포함한다.
6. backfill은 사전 건수·합계 기록, 트랜잭션, 사후 동등성 검증을 포함한다.
7. 저장소를 dual-read 또는 fallback 방식으로 연결하고 기존·신규 결과를 비교한다.
8. 원격 적용 전 SQL 구문·테스트·보안 정책·advisors를 확인하고 이재용 승인을 받는다.
9. 원격 적용 후 migration history, 테이블·정책·권한·인덱스·행 수·API E2E를 다시 조회한다.
10. 삭제는 별도 cleanup PR과 마이그레이션으로 수행한다.

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
| DB-00 | BGE-M3 1024차원·HNSW 마이그레이션 | `LOCAL-DRAFT` | 소유자 확인, 주석·원격 데이터 사전검사, 테스트, 원격 적용 | 진행 중 변경 소유자 확인 |
| DB-01 | PDF 기반 사용자·성향·계좌 스키마 승인 | `PROPOSED` | 테이블명·범위·open decision 승인 | 이재용·백엔드·엔진 담당 리뷰 |
| DB-02 | Additive domain migration | `NOT-STARTED` | DDL·RLS·GRANT·인덱스·계약 테스트 통과 | DB-01 후 생성 |
| DB-03 | 문항·목계좌 backfill | `NOT-STARTED` | 3/6/10 및 금액·엔진 결과 동등 | DB-02 후 수행 |
| DB-04 | Postgres repository·API 연결 | `NOT-STARTED` | DB 우선·JSON fallback·E2E 통과 | DB-03 후 수행 |
| DB-05 | 기존 mock account tables 정리 | `NOT-STARTED` | 코드·SQL 참조 0, 별도 승인·복구 계획 | DB-04 안정화 후 수행 |
| DB-06 | 커뮤니티 리뷰 | `DEFERRED` | 포트폴리오 FK·RLS·soft delete 승인 | 핵심 계좌 연동 후 검토 |

## 13. 미결정 사항

- DB 작업의 실명 담당자와 폴더 소유권: `TODO: 확인 필요`.
- `user_profiles`와 `customers` 중 최종 명칭: `user_profiles` 권장, 승인 필요.
- 실제 계좌 연동 방식과 provider import 원천: `TODO: 확인 필요`. 현재 사용자 계좌는 목데이터만 허용된다.
- 3단계 목시나리오 성향과 5단계 진단 성향 매핑: 팀 승인 전 미구현.
- `account_cash_flows`를 첫 스키마에 포함할지 실계좌 연동 시점으로 미룰지: 현재 수익률 엔진 정합성상 포함 권장.
- 상품 마스터를 제공할 공식 product-level API: 현재 FSS 데이터는 provider-level이므로 별도 확인 필요.
- 커뮤니티 리뷰의 실제 사용자 대상 공개 시점과 보존·신고 정책: 후속 결정.

## 14. 작업 로그

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
