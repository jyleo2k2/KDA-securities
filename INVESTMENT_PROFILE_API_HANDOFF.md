# 투자성향 저장·조회 API 작업 핸드오프

> 이 문서는 다음 Codex 백엔드 세션에 그대로 전달할 실행 프롬프트다.
> 작성 기준일: 2026-07-20

## 역할

너는 연금 코파일럿 프로젝트의 백엔드 세션이다. 목표는 피그마의 "투자자정보 확인서" 화면이 요구하는 투자성향 진단 저장·조회 경로를 여는 것이다.

이 작업은 **조사 완료 → 미결정 사항 승인 → 테스트 우선 구현 → 검증 → PR** 순서로 진행한다. 승인되지 않은 정책이나 데이터를 그럴듯하게 만들지 마라.

## 시작 전 필독

다음 순서대로 읽는다.

1. 루트 `AGENTS.md`
2. `docs/team/_공통_AI규칙.md`
3. `docs/30_스펙/아키텍처.md`
4. `docs/30_스펙/코드베이스_지도.md`
5. `supabase/AGENTS.md`
6. `supabase/DB_SESSION_GUIDE.md`
7. `supabase/DB_HANDOFF.md`
8. `backend/app/engine/AGENTS.md` — 엔진 파일은 읽기만 하고 수정하지 않는다.

`karpathy-guidelines`와 Supabase 관련 스킬을 적용한다. 범위를 작게 유지하고, 모든 변경은 이 작업의 요구사항으로 직접 설명할 수 있어야 한다.

## 현재까지 확인한 사실

### Git

2026-07-20 조사 시점에는 다음 상태였다. 새 세션에서는 반드시 다시 확인한다.

- 현재 브랜치: `main`
- `HEAD == origin/main == c4d84a635f282f01d7581db6255315dbbdefb803`
- 작업 트리 깨끗함
- `backend/app/engine/profile.py`에 미커밋 변경 없음

작업 시작 전에 `git status --short --branch`와 `git fetch origin main`으로 재확인한다. 다른 세션의 변경이 생겼으면 건드리지 말고 별도 worktree를 사용한다.

### 로컬·원격 DB

기존 마이그레이션은 `supabase/migrations/20260716001737_add_user_pension_domain.sql`이다. 아래 스키마를 **다시 만들지 마라**.

- `public.investment_profile_assessments`
- `public.investment_profile_answers`
- `public.profile_question_sets`
- `public.profile_questions`
- `public.profile_question_options`

2026-07-20 원격 프로젝트 `fdltrpabebayuwcnqqfy`를 읽기 전용으로 확인한 결과:

- 관련 테이블 6개 모두 RLS 활성화
- 활성 문항 세트 1개
- 문항 6개
- 선택지 30개
- assessment 0건
- answer 0건
- `user_profiles` 0건
- 만료일 컬럼 없음
- 투자권유 희망 여부 컬럼 없음
- 투자자정보 제공 여부 컬럼 없음
- 전체 `public` 컬럼명 검색에서도 위 토글·만료에 해당하는 저장 위치가 없음

RLS는 다음 조건을 이미 만족한다.

- `TO authenticated`
- assessment는 `(select auth.uid()) = owner_id`
- answer는 소유 assessment를 `exists`로 확인
- UPDATE 정책에는 `USING`과 `WITH CHECK`가 모두 있음
- 최신 진단 조회용 `(owner_id, assessed_at desc)` 인덱스가 있음

원격 스키마나 데이터를 다시 확인할 때는 읽기 전용 쿼리만 사용한다. 원격 migration 적용은 이재용의 명시적 승인 전에는 금지한다.

### 현재 코드 계약

- `POST /engine/profile`은 stateless 채점만 한다.
- `backend/app/engine/profile.py`의 `ProfileSurveyInput`은 `answers` 6개만 받는다.
- 각 답변은 `question_code`, `selected_score`만 가진다.
- `evaluate_profile()`이 점수, 백분율, 5단계 `RiskProfile`, 엔진·규칙 버전을 계산한다.
- API나 repository가 점수를 다시 계산하면 안 된다.
- `RiskProfile.value`와 DB check 값은 소문자다.
  - `stable`
  - `stable_seeking`
  - `risk_neutral`
  - `active`
  - `aggressive`
- `data/mock/users.csv`의 성향은 `STABLE`, `RISK_NEUTRAL`처럼 대문자다. 목데이터 값을 이 저장 API에 직접 넣지 말고, 불가피하게 경계를 통과할 때만 명시적으로 소문자 변환·검증한다.
- 프론트의 현재 `ProfileSurveyInput`과 `evaluateProfileSurvey()`도 `{ answers }`만 전송한다.

### 기존 패턴

- 소유자 스코프 repository: `backend/app/pension_accounts_repository.py`
- repository 의존성 생성: `backend/app/api/deps.py`
- 인증 함수의 실제 위치: `backend/app/auth.py`의 `require_supabase_user_id`
- 인증 router 사용 예시: `backend/app/api/pension_accounts.py`

주의: 최초 작업 지시에는 `backend/app/api/deps.py`의 인증 함수를 사용하라고 적혀 있지만, 실제 함수는 `backend/app/auth.py`에 있다. router는 기존 코드처럼 `auth.py`에서 인증 함수를 import하고, `deps.py`에는 새 repository provider만 추가한다.

## 목표 산출물

### POST `/me/investment-profile`

- Supabase 인증 필수
- 설문을 기존 `evaluate_profile()`로 채점
- assessment 1건과 answer 6건을 한 트랜잭션으로 저장
- 저장된 최신 결과를 반환
- `owner_id`는 요청 body에서 받지 않고 인증 사용자 UUID만 사용

### GET `/me/investment-profile`

- Supabase 인증 필수
- 인증 소유자의 최신 진단 1건과 문항별 답변 반환
- 승인된 유효기간 정책에 따라 만료일과 만료 여부 반환
- 다른 사용자의 데이터는 절대 반환하지 않음

### 테스트

- 인증 없는 요청 거부
- 소유자 UUID가 body가 아니라 인증 의존성에서 주입됨
- 다른 사용자의 assessment·answer 접근 불가
- 최신 진단 1건만 반환
- assessment와 answers 원자적 저장 및 실패 시 롤백
- 엔진 결과를 그대로 저장하고 API가 점수를 재계산하지 않음
- DB에는 `RiskProfile.value` 소문자만 저장
- 선택지의 value·label은 클라이언트가 만들지 않고 DB 원본을 스냅샷으로 저장
- 미진단 사용자의 승인된 empty 계약 검증

## 구현 전에 반드시 받을 승인

아래는 아직 확정되지 않았다. 다음 세션은 먼저 현재 코드·원격 상태가 위 내용과 같은지 짧게 재검증하고, 이재용에게 아래 항목을 한 번에 보고해 승인을 요청한다. 승인 전에는 구현·migration 생성·원격 적용을 하지 마라.

### 결정 1 — 유효기간

공식 근거:

- 금융투자협회 표준투자권유준칙(2026-04-09 개정)은 회사가 투자자의 동의를 받아 투자자정보 유효기간을 **12~24개월**로 정하도록 안내한다.
- 원문: <https://law.kofia.or.kr/service/law/lawFullScreenContent.do?historySeq=1787&seq=149>

권고안:

- 유효기간은 24개월
- DB 만료 컬럼은 추가하지 않고 `assessed_at`으로부터 계산
- 채점 엔진이 아니라 별도의 API/domain 정책 상수로 관리
- 정책 버전을 응답이나 문서에 명시
- 피그마의 `2026-01-13 → 2028-01-12` 표시는 `진단일 + 24개월 - 1일`을 마지막 유효일로 보는 방식
- 만료 판정 기준과 KST 날짜 변환을 테스트로 고정

승인 질문:

1. 24개월을 채택할지
2. 마지막 유효일을 `진단일 + 24개월 - 1일`로 계산할지
3. 엔진이 아닌 API/domain 정책으로 둘지

### 결정 2 — 두 토글의 의미와 저장 위치

화면 요구:

- 투자권유 희망/미희망
- 투자자정보 제공/미제공

이 값들은 단순 닉네임성 프로필이 아니라 확인 이력에 가깝다. 금융투자협회 준칙상 투자자정보를 제공하지 않으면 투자권유를 희망하는 투자자로 처리할 수 없으므로 다음 조합은 허용하면 안 된다.

```text
investor_information_provided = false
investment_advice_desired = true
```

권고안:

- `user_profiles`의 boolean 두 개를 덮어쓰는 방식 대신 별도 append-only 확인 이력 테이블 사용
- 최소 필드: `id`, `owner_id`, 두 상태, `confirmed_at`, 확인서/정책 버전
- 기록 없음과 명시적 `false`를 구분
- 테이블을 추가한다면 반드시 `supabase migration new <name>`으로 additive migration 생성
- `public` 테이블이면 RLS와 소유자 인덱스 포함
- UPDATE가 필요 없다면 불필요한 UPDATE 정책을 만들지 않는다.

승인 질문:

1. 별도 확인 이력 테이블을 추가할지
2. 두 상태를 진단 제출과 같은 트랜잭션에 저장할지
3. 위의 모순 조합을 422로 거부할지

### 결정 3 — POST body와 GET empty 계약

현재 `ProfileSurveyInput`에는 토글이 없으므로 기존 body를 그대로 받으면서 토글까지 저장할 수 없다.

권고 POST body:

```json
{
  "survey": {
    "answers": [
      {
        "question_code": "investment_horizon",
        "selected_score": 3
      }
    ]
  },
  "investment_advice_desired": true,
  "investor_information_provided": true
}
```

- API 전용 request model을 만들고 내부의 `survey`만 엔진으로 전달한다.
- `backend/app/engine/profile.py`의 `ProfileSurveyInput` 자체는 수정하지 않는다.
- 실제 구현에서는 반드시 6개 문항을 모두 보내야 한다. 위 JSON은 구조 예시일 뿐이다.

권고 GET empty 응답:

```json
{
  "assessment": null,
  "preferences": null
}
```

- 미진단은 정상적인 초기 상태이므로 404가 아닌 200 explicit empty를 사용한다.

승인 질문:

1. API 전용 wrapper body를 사용할지
2. 미진단 GET을 200 explicit empty로 고정할지

## 승인 후 구현 설계

승인을 받으면 먼저 `git fetch origin main` 후 최신 `origin/main`에서 `profile/investment-profile-api` 브랜치 또는 별도 worktree를 만든다. `main`에 직접 커밋하거나 push하지 않는다.

### 변경 예상 파일

필요한 파일만 변경한다. 이름은 기존 프로젝트 스타일에 맞추되, 대략 다음 범위다.

- 신규 `backend/app/investment_profile_repository.py`
- 신규 `backend/app/api/investment_profile.py`
- 수정 `backend/app/api/deps.py`
- 수정 `backend/app/main.py`
- 신규 `tests/test_investment_profile_repository.py`
- 신규/수정 API 테스트
- 필요 시 `tests/test_schema_contract.py`
- 승인된 경우에만 새 Supabase migration
- 정책 근거를 담을 적절한 `docs/30_스펙/` 계약 문서
- DB 상태가 실제로 바뀐 경우에만 `supabase/DB_HANDOFF.md`

루트 `AGENTS.md`와 `CLAUDE.md`는 잠금 파일이므로 수정하지 않는다. 구조 변경이 아니라면 `코드베이스_지도.md`도 불필요하게 고치지 않는다.

### repository 규칙

1. `PensionAccountRepository`의 connection/pool 패턴을 따른다.
2. 모든 읽기·쓰기 SQL에 인증된 `owner_id`를 명시적으로 넣는다.
3. 서버 DB 연결이 RLS를 우회할 수 있으므로 RLS만 믿지 않는다.
4. GET은 `where assessment.owner_id = %s`를 포함한다.
5. answer 조회는 assessment를 조인하고 같은 소유자 조건을 건다.
6. 최신 진단은 `assessed_at desc`를 기준으로 결정적으로 조회한다.
7. assessment와 answers 저장은 짧은 단일 트랜잭션으로 처리한다.
8. 엔진 호출과 Pydantic 검증은 가능한 한 DB 트랜잭션 밖에서 수행한다.
9. 활성 `profile_question_sets`와 문항·선택지를 읽어 엔진 이름·버전·규칙 버전 및 문항 코드가 일치하는지 확인한다.
10. 각 `selected_score`에 대응하는 DB option에서 `option_id`, `selected_value`, `selected_label`, `selected_score`를 가져와 answer 스냅샷을 만든다.
11. `risk_profile`에는 enum 이름이나 대문자 문자열이 아니라 `evaluation.risk_profile.value`를 저장한다.
12. 개인 성향·답변은 어떤 RAG 문서나 embedding에도 넣지 않는다.

### 오류 계약

기존 프로젝트 스타일을 확인해 최소한으로 정한다.

- 인증 없음/잘못된 토큰: 기존 인증 의존성의 401
- DB 미설정 또는 연결 불가: 503
- 활성 문항 세트와 엔진 계약 불일치: 데이터 계약 오류로 처리하고 저장하지 않음
- 허용되지 않는 토글 조합: 승인 시 422
- assessment 저장 후 answer 저장 실패: 전체 롤백

새로운 예외 계층이나 범용 프레임워크를 만들지 마라. 이 기능에 필요한 최소 예외만 둔다.

## 테스트 우선 순서

1. API route 등록 및 인증 테스트
2. POST가 인증 owner를 repository에 전달하는 테스트
3. 엔진 결과·문항 선택지 스냅샷 저장 테스트
4. assessment/answer 원자성 및 롤백 테스트
5. GET latest와 explicit empty 테스트
6. 두 owner 데이터를 준비해 상호 격리를 증명하는 테스트
7. 소문자 enum 저장 테스트
8. migration이 생긴 경우 RLS·인덱스·정책 계약 테스트
9. 승인된 만료 경계 직전·당일·다음 날 테스트

가짜 repository만으로 소유자 격리를 주장하지 마라. repository SQL이 owner 조건을 실제로 포함하는지 확인하고, 가능한 로컬 DB 통합 테스트가 있으면 두 사용자 행으로 격리를 검증한다. 원격 DB에 임의 테스트 데이터를 넣지 않는다.

## 완료 조건과 검증 명령

다음이 모두 충족되어야 완료다.

- POST가 기존 엔진으로만 채점하고 저장한다.
- assessment 1건과 answer 6건이 원자적으로 저장된다.
- GET은 자기 최신 진단만 반환한다.
- 미진단 계약과 만료 정책이 테스트로 고정된다.
- 토글 계약이 승인 내용대로 저장·검증된다.
- 대문자 mock enum이 DB 경계를 오염시키지 않는다.
- RAG에 개인 데이터를 넣는 변경이 없다.
- 기존 stateless `POST /engine/profile`은 깨지지 않는다.

검증:

```powershell
uv run pytest tests/test_schema_contract.py
uv run pytest
uv run ruff check .
```

Supabase migration이 생겼다면 CLI 명령을 추측하지 말고 먼저 `supabase --help`, 해당 하위 명령의 `--help`, `supabase --version`을 확인한다. 원격 적용 전에는 migration diff, RLS, 인덱스, grant를 검토하고 이재용에게 별도 승인을 요청한다.

## 보고 형식

승인 전 보고는 다음처럼 짧게 한다.

1. 재확인한 현재 상태
2. 위 3개 결정에 대한 권고안
3. 승인받아야 하는 항목
4. 승인 전에는 코드·DB를 변경하지 않았다는 사실

구현 후 보고에는 다음을 포함한다.

1. 무엇을 구현했는지
2. 승인된 정책이 코드 어디에 반영됐는지
3. 소유자 격리를 어떻게 검증했는지
4. 테스트·ruff의 실제 실행 결과
5. migration 유무와 원격 미적용/적용 상태
6. 변경 파일과 PR 링크

테스트를 실행하지 않았거나 실패했다면 숨기지 말고 정확히 적는다.
