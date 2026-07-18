# 연금 코파일럿 DB 관리 세션 가이드

> DB·Supabase 전담 세션이 매번 같은 절차로 시작·변경·검증·인계하기 위한 운영 런북이다.
> 변하지 않는 절차는 이 문서, 현재 원격 상태와 작업 로그는 [`DB_HANDOFF.md`](./DB_HANDOFF.md)가 SSOT다.

## 1. 문서 책임 분리

- 이 문서: 시작 순서, 승인 경계, migration 작성법, 검증 체크리스트.
- [`DB_HANDOFF.md`](./DB_HANDOFF.md): 현재 브랜치·HEAD·원격 수치·작업 상태·실행 결과.
- [`AGENTS.md`](./AGENTS.md)·[`CLAUDE.md`](./CLAUDE.md): `supabase/` 작업의 절대 규칙과 폴더 경계. 두 파일은 항상 같은 내용으로 유지한다.
- 동적 수치를 이 문서에 복제하지 않는다. 수치가 바뀌면 `DB_HANDOFF.md`만 갱신한다.

## 2. 세션 시작 순서

1. `C:\Users\jyleo\.Codex\projects\KDA-securities\memory\MEMORY.md`를 확인한다. 없으면 `확인 불가`로 기록한다.
2. 루트 `AGENTS.md` → `docs/team/_공통_AI규칙.md` → `docs/30_스펙/아키텍처.md`를 읽는다.
3. `supabase/AGENTS.md` → 이 문서 → `supabase/DB_HANDOFF.md`를 읽는다.
4. 모든 migration을 시간순으로 읽고 `supabase/seed.sql`을 확인한다.
5. 원래 작업 폴더와 DB 전용 worktree의 `git status`, HEAD, branch, worktree 목록을 확인한다.
6. `git fetch origin --prune` 후 GitHub PR·CI 상태를 실제 조회한다.
7. Supabase MCP로 프로젝트 상태, migration history, public 테이블·RLS, 역할별 GRANT를 실제 조회한다.
8. 기존 보고와 조회 결과가 다르면 조회값을 우선하고 `DB_HANDOFF.md`를 고친다.

연결 대상 프로젝트 ref는 `fdltrpabebayuwcnqqfy`다. ref는 공개 식별자이며 API key·DB URL·비밀번호는 아니다.

## 3. 작업 격리

- 원래 `C:\dev\KDA-securities`의 다른 세션 WIP를 수정·stash·reset·checkout하지 않는다.
- DB 변경은 최신 `origin/main`에서 만든 별도 branch와 worktree에서 수행한다.
- 다른 worktree가 dirty면 소유자를 추정하지 않는다. 읽기만 하고 별도 worktree를 만든다.
- 루트 `AGENTS.md`·`CLAUDE.md`는 이재용만 수정한다.
- `supabase/AGENTS.md`와 `supabase/CLAUDE.md` 중 하나를 바꾸면 같은 커밋에서 다른 하나도 동일하게 바꾼다.

## 4. 승인 경계

- 로컬 변경: 계획·영향 범위·성공 조건을 먼저 제시하고 사용자 승인을 받는다.
- 원격 migration 적용: 이재용의 명시적 승인 후에만 수행한다.
- PR 머지와 main push: 이재용의 명시적 승인 후에만 수행한다.
- `migration repair`, `db reset --linked`, 적용 완료 migration 수정, destructive SQL은 금지한다.
- 확인하지 않은 migration을 `REMOTE-APPLIED`로 기록하지 않는다.

## 5. Migration 작성 절차

1. Supabase 최신 changelog와 관련 공식 문서를 확인한다.
2. 변경 전 실패하는 계약 테스트를 작성하고 실패 원인을 확인한다.
3. CLI 명령은 현재 도움말을 먼저 확인한다.

```powershell
npx.cmd --yes supabase --version
npx.cmd --yes supabase --help
npx.cmd --yes supabase migration new --help
```

4. 새 파일은 CLI로만 생성한다.

```powershell
npx.cmd --yes supabase migration new <descriptive_name>
```

5. 최소 SQL만 작성한다. 기존 적용 migration은 수정하지 않는다.
6. 스키마·데이터·권한 변경을 한 migration에 불필요하게 섞지 않는다.
7. SQL 계약 테스트와 `pglast` 파싱으로 구문을 검증한다.
8. 원격 적용 전 migration 파일, 영향 범위, 롤포워드 방식, 검증 쿼리를 이재용에게 제시한다.
9. 인증된 linked CLI를 사용할 수 있으면 로컬 migration version을 보존하는 적용 경로를 우선한다. MCP `apply_migration`을 사용하면 실행 시각 버전이 부여될 수 있으므로 적용 직후 로컬·원격 이름과 버전을 비교한다.
10. 버전이 달라져도 `migration repair`로 이력을 조작하지 않는다. SQL 내용과 SHA-256을 보존한 채 미적용 로컬 파일명을 실제 원격 버전에 맞추고 branch → PR로 반영한다.

## 6. 원격 읽기 검증 기준

Supabase MCP의 `get_project`, `list_migrations`, `list_tables`, `execute_sql`, `get_advisors`를 우선 사용한다. SQL은 읽기 전용 `SELECT`만 실행한다.

### public 테이블·RLS

```sql
select
  count(*) filter (where c.relkind in ('r', 'p')) as public_tables,
  count(*) filter (
    where c.relkind in ('r', 'p') and c.relrowsecurity
  ) as rls_enabled_tables
from pg_catalog.pg_class as c
join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public';
```

### 역할별 테이블 권한

```sql
with roles(grantee) as (
  values ('anon'), ('authenticated'), ('service_role')
), grants as (
  select grantee, table_name
  from information_schema.role_table_grants
  where table_schema = 'public'
    and grantee in ('anon', 'authenticated', 'service_role')
)
select roles.grantee, count(distinct grants.table_name) as table_count
from roles
left join grants on grants.grantee = roles.grantee
group by roles.grantee
order by roles.grantee;
```

### Migration 이력 본문 보존 여부

```sql
select
  version,
  name,
  statements is null as statements_is_null,
  coalesce(cardinality(statements), 0) as statement_count
from supabase_migrations.schema_migrations
order by version;
```

`20260715165614_fix_embedding_dimension_bge_m3`의 statement count 0은 과거 legacy 예외다. 실제 `vector(1024)` 타입·non-null 차원·HNSW 인덱스를 확인하고, 과거 이력을 repair하거나 조작하지 않는다.

### Auth 보안 설정

`get_advisors(type=security)`에서 `auth_leaked_password_protection`을 확인한다. 유출 비밀번호 보호는 인증된 Supabase Dashboard 또는 Management API에서만 변경하고, 비밀번호·access token을 요청하거나 출력하지 않는다. 인증 세션이 없으면 설정을 우회하지 않고 `BLOCKED`로 기록한다.

### 컬럼 설명

```sql
select
  columns.table_name,
  columns.column_name,
  pg_catalog.col_description(
    (quote_ident(columns.table_schema) || '.' || quote_ident(columns.table_name))::regclass::oid,
    columns.ordinal_position
  ) as column_comment
from information_schema.columns as columns
where columns.table_schema = 'public'
order by columns.table_name, columns.ordinal_position;
```

## 7. 검증 명령

```powershell
uv run pytest tests/test_schema_contract.py tests/test_embedded_sql.py
uv run pytest
uv run ruff check .
git diff --check
```

- 테스트 결과는 명령·종료 코드·통과 건수를 `DB_HANDOFF.md`에 남긴다.
- 원격 런타임 회귀는 비밀값이 있는 프로젝트 루트에서 `uv run python <DB_WORKTREE>/scripts/verify_auth_rls_e2e.py`로 실행한다. 이 스크립트는 임시 Auth 사용자·채팅 세션을 정리하고 NAVER 쓰기 SQL은 rollback-only 트랜잭션으로 검증하며, 자격 증명은 출력하지 않는다.
- 원격 적용 후에는 migration history, 실제 카탈로그 상태, RLS, GRANT, 데이터 불변식을 다시 조회한다.
- 확인하지 못한 항목은 `확인 불가`로 기록한다.

## 8. 종료·인계 체크리스트

1. `DB_HANDOFF.md`의 최종 확인 시각, branch, HEAD, dirty 상태를 갱신한다.
2. 상태표를 `LOCAL-DRAFT`, `LOCAL-VERIFIED`, `REMOTE-APPLIED`, `BLOCKED` 중 하나로 갱신한다.
3. 실행한 테스트·MCP 쿼리·Advisor 결과와 원격 적용 여부를 작업 로그 맨 위에 추가한다.
4. 원격 미적용 migration은 버전과 승인 대기 상태를 명시한다.
5. branch → 명시적 stage → commit → push → Draft PR 순서로 반영한다.
6. PR과 원격 적용은 별개다. PR이 있어도 승인 전에는 원격 DB에 쓰지 않는다.

이 운영 절차가 바뀔 때만 이 문서를 갱신한다. 현재 DB 수치만 바뀐 경우에는 `DB_HANDOFF.md`만 갱신한다.
