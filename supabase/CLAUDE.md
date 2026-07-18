# 연금 코파일럿 DB 작업 진입점

> 적용 범위: `supabase/` 하위의 마이그레이션, seed, 설정, DB 운영 문서.
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 다른 쪽도 같은 커밋에서 바꾼다.
> 최종 갱신: 2026-07-19

## 임무

현재 Supabase 데이터 기반과 적용 이력을 보존하면서 사용자·투자성향·연금계좌·보유상품 설계를 Python 엔진과 FastAPI 계약에 맞게 단계적으로 통합한다. DB 작업의 동적 상태·검증·결정은 [`DB_HANDOFF.md`](./DB_HANDOFF.md)에만 기록한다.

## READ-FIRST

1. 루트 [`AGENTS.md`](../AGENTS.md) 또는 [`CLAUDE.md`](../CLAUDE.md)
2. [`docs/team/_공통_AI규칙.md`](../docs/team/_공통_AI규칙.md)
3. [`docs/30_스펙/아키텍처.md`](../docs/30_스펙/아키텍처.md)
4. [`DB_SESSION_GUIDE.md`](./DB_SESSION_GUIDE.md) — DB 세션 고정 운영 절차
5. [`DB_HANDOFF.md`](./DB_HANDOFF.md) — 현재 상태·작업 로그 SSOT
6. [`migrations/`](./migrations)을 시간순으로 읽고 [`seed.sql`](./seed.sql) 확인
7. `git status`, 현재 diff, 원격 migration history 확인

루트 `AGENTS.md`·`CLAUDE.md`는 이재용만 수정한다. 이 작업을 이유로 두 파일을 편집하지 않는다.

## 작업 시작 규칙

- 먼저 현재 브랜치·HEAD·dirty 파일 소유자를 확인한다. 다른 팀원의 변경을 수정·삭제·되돌리지 않는다.
- 현재 작업·원격 적용 상태는 추정하지 않고 [`DB_HANDOFF.md`](./DB_HANDOFF.md)와 실제 Git·Supabase 조회로 재확인한다.
- Supabase 기능을 구현하기 전 최신 changelog와 공식 문서를 확인한다.
- 시크릿을 읽어 출력하지 않는다. `.env`, DB URL, API key, service role key를 로그·문서·커밋에 남기지 않는다.
- 계획과 영향 범위를 먼저 제시하고 승인받은 뒤 수정한다.
- `main` 직접 push 금지. 브랜치, PR, 이재용 머지 승인 절차를 따른다.

## 마이그레이션 규칙

- 원격 migration history에 존재하는 모든 적용 완료 migration은 수정하지 않는다.
- 새 파일은 `supabase migration new <descriptive_name>`으로 생성한다. CLI 명령은 먼저 `--help`로 확인한다.
- `scripts/apply_embedding_migration.py`는 SQL과 migration history를 직접 기록하는 이재용 실행용 스크립트다. 명시적 승인과 사전 검토 없이 실행하지 않는다.
- 첫 단계는 additive migration이다. 컬럼·테이블 삭제와 이름 변경을 같은 마이그레이션에 섞지 않는다.
- 필수 reference data와 원격 backfill은 migration에 포함한다. 로컬 reset용 `seed.sql`도 멱등하게 맞춘다.
- destructive 변경은 사전 건수·합계·참조 검색, 백업·복구안, backfill 동등성, 코드 전환 후 별도 migration으로 수행한다.
- migration 상태를 `LOCAL-DRAFT`, `LOCAL-VERIFIED`, `REMOTE-APPLIED`로 구분한다. 원격 카탈로그를 조회하지 않고 적용 완료라 쓰지 않는다.
- 원격 적용은 이재용 승인 후 수행한다. 적용 직후 migration history, RLS, GRANT, 정책, 인덱스, 행 수를 다시 검증한다.

## 스키마 불변식

- public의 모든 테이블에 RLS를 활성화한다. Data API `GRANT`와 RLS를 각각 검증한다.
- 기본 접근은 FastAPI 경유다. `anon` 권한은 기본적으로 부여하지 않는다.
- 사용자 소유 정책은 `TO authenticated`와 `(select auth.uid()) = owner_id`를 함께 사용한다.
- UPDATE 정책에는 `USING`과 `WITH CHECK`를 모두 둔다.
- 브라우저에 `service_role` 또는 secret key를 노출하지 않는다.
- public view는 `security_invoker = true`를 우선 사용한다. 권한 오류를 숨기기 위한 public `SECURITY DEFINER` 함수 금지.
- `CUSTOMER.login_id/password_hash`를 public에 만들지 않는다. Supabase Auth의 `auth.users(id)`를 참조하는 프로필만 둔다.
- 계좌 유형은 `dc`, `irp`, `pension_savings`로 고정한다.
- 투자성향은 `stable`, `stable_seeking`, `risk_neutral`, `active`, `aggressive` 5단계다. 목시나리오 3단계와 임의 매핑 금지.
- 상품 위험처리는 `capital_preservation`, `general_risky`, `statutory_exception`과 명시적 예외 `eligible_tdf`, `default_option`을 사용한다.
- 실/목 데이터, 기준일, 출처, 수집 또는 입력 주체를 모든 사용자 계좌 수치에 연결한다.
- FSS provider stats와 financial product master를 같은 모집단으로 취급하지 않는다.
- 계산·판단은 Python 규칙 엔진이 한다. DB와 LLM이 독자적으로 수익률·진단·추천 수치를 만들지 않는다.
- 개인 계좌·성향·대화 데이터는 RAG embedding에 넣지 않는다.

## 코드 경계

- `supabase/migrations/`: DDL, constraint, index, RLS, GRANT, backfill.
- `supabase/seed.sql`: 로컬 reset용 멱등 seed.
- `backend/app/engine/`: 순수 규칙 엔진. DB 의존성 추가 금지. 변경 시 엔진 담당 합의 필요.
- `backend/app/chat/scenarios.py` 및 신규 repository: DB 행을 기존 Pydantic 입력으로 변환하는 경계.
- `backend/app/api/`: Auth와 repository를 오케스트레이션. 직접 계산 금지.
- `tests/test_schema_contract.py`: 테이블·RLS·권한·마이그레이션 계약.
- `tests/test_embedded_sql.py`: 코드 내 SQL 구문 계약.
- 공유 REST·엔진 I/O·상품 스키마 변경은 PR에 `계약 변경`을 표시하고 담당자 합의를 받는다.

## 핸드오프 갱신 의무

작업 시작 시 [`DB_HANDOFF.md`](./DB_HANDOFF.md)의 다음 항목을 확인하고 틀리면 먼저 고친다.

- 최종 확인 시각, 브랜치, HEAD, dirty 상태
- 원격 migration history와 테이블·RLS 상태
- 진행 중 작업과 파일 소유자
- 작업 상태표와 미결정 사항

의미 있는 작업을 마칠 때마다 다음을 갱신한다.

- 상태표의 상태와 완료 조건
- 실제 실행한 테스트·쿼리와 결과
- 원격 적용 여부와 migration version
- 새 결정, 위험, blocker, 다음 작업
- 작업 로그의 새 항목

검증하지 않은 수치와 완료 표시는 금지한다. 로그 기록만 하고 실제 작업을 생략해서도 안 된다.

## 검증 명령

```powershell
uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py
uv run pytest
uv run ruff check .
git diff --check
```

- Python은 `uv run python`만 사용한다.
- SQL·한국어 Markdown은 UTF-8로 다룬다. PowerShell·sed 일괄치환으로 한국어 파일을 수정하지 않는다.
- Supabase CLI가 필요하면 설치·버전을 확인하고 `supabase --help`부터 실행한다.
- 원격 읽기 검증 시 연결 문자열 자체는 출력하지 않는다.
- Supabase advisors를 실행할 수 있으면 보안·성능 경고를 검토하고 결과를 핸드오프에 남긴다.

## 완료 기준

- 요청한 DDL·seed·backend adapter가 같은 데이터 계약을 사용한다.
- 로컬 전체 테스트와 관련 보안·SQL 계약 테스트가 통과한다.
- 승인된 backfill의 사전·사후 건수·금액·엔진 결과가 동일하다.
- 신규 public 테이블의 RLS·GRANT·소유권 격리를 실제 역할로 검증한다.
- 원격 적용 후 migration history와 E2E를 재검증한다.
- [`DB_HANDOFF.md`](./DB_HANDOFF.md)가 실제 최종 상태와 일치한다.
