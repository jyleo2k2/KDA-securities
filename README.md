# 연금 코파일럿

> 키움 디지털 아카데미 1차 프로젝트 · 최신 `main` 기준 / 엔진·챗봇·ETF·RAG·인증·연금계산기·전략·User Pick 화면 통합 완료 / 원격 배포 복구·골든패스 E2E 완료 (2026-07-26)

**세 연금계좌의 통합 포트폴리오를 보여주고, 출처 기반 시장·상품 정보와 익명 벤치마킹으로 이용자의 연금 투자 판단을 돕는 AI 연금가이드.**

AI는 설명과 제안만 하며, 계산은 규칙 엔진이 담당한다. 실제 상품 선택·주문은 이용자가 금융회사 공식 채널에서 직접 수행한다.

## 먼저 읽기

| 순서 | 문서 | 역할 |
|---|---|---|
| 1 | [AGENTS.md](./AGENTS.md) / [CLAUDE.md](./CLAUDE.md) | AI 작업 규칙 |
| 2 | [기획서](./docs/10_기획/기획서.md) | 제품·MVP SSOT |
| 2-1 | [기능정의서](./docs/10_기획/기능정의서.html) | 현재 기능·상태·수용 기준·구현 근거를 한눈에 보는 HTML |
| 3 | [연금 기초](./docs/20_리서치/연금_기초.md) | 계좌·제도 사실 (RAG 코퍼스 — 공식 사실만) |
| 3-1 | [엔진 설계근거](./docs/10_기획/엔진_설계근거.md) | 그 사실이 어느 엔진 규칙이 되는지 (내부 해석) |
| 4 | [아키텍처](./docs/30_스펙/아키텍처.md) | 기술·엔진 계약 |
| 5 | [컴플라이언스](./docs/40_규제/컴플라이언스.md) | 규제·표현 경계 |

## 핵심 기능

1. **내 연금 포트폴리오 홈** — 통합 원그래프, 일일 가이드, 주간 이상 매크로 가이드
2. **연금가이드 챗봇** — 상품 설명·비교, 종목·상품 외부 리서치, 성향 기반 자산군 전략
3. **공개 포트폴리오** — 익명 탐색과 내 포트폴리오 차이 보기

상세 화면은 [화면·유저 플로우](./docs/10_기획/화면_유저플로우.md), 이후 아이디어는 [확장 아이디어](./docs/10_기획/확장_아이디어.md)에서 관리한다.

## 문서 지도

| 폴더 | 역할 | 주요 문서 |
|---|---|---|
| **docs/10_기획** | 무엇을 만들지 | [기획서](./docs/10_기획/기획서.md) · [기능정의서](./docs/10_기획/기능정의서.html) · [화면 흐름](./docs/10_기획/화면_유저플로우.md) · 확장 아이디어 |
| **docs/20_리서치** | 왜 필요한지 | [시장·경쟁](./docs/20_리서치/시장_경쟁.md) · [키움 동향](./docs/20_리서치/키움_동향.md) · [SWOT](./docs/20_리서치/SWOT.md) |
| **docs/30_스펙** | 어떻게 계산할지 | [아키텍처](./docs/30_스펙/아키텍처.md) · [코드베이스 지도](./docs/30_스펙/코드베이스_지도.md)(AI 세션용 파일별 구현 캐시) · [수익률 가정](./docs/30_스펙/수익률_가정_모델.md) · [거시지표 검토](./docs/30_스펙/거시지표_계획가정_검토.md) · [데이터 품질](./docs/30_스펙/데이터_품질_계약.md) · [ETF 적격성](./docs/30_스펙/연금계좌_ETF_적격성_계약.md) · [총수익률·비용](./docs/30_스펙/ETF_총수익률_비용_마스터_계약.md) · [종목 이벤트](./docs/30_스펙/ETF_종목_이벤트_마스터_계약.md) · [교육용 포트폴리오](./docs/30_스펙/교육용_포트폴리오_엔진_계약.md) · [연금 계산기](./docs/30_스펙/연금계산기_엔진_계약.md) · [챗봇 테스트](./docs/30_스펙/챗봇_테스트_가이드.md) · [LLM 모델 비교](./docs/30_스펙/LLM_모델_비교.md)(3사 5모델 비용·속도·답변 실측) |
| **docs/40_규제** | 어디까지 가능한지 | [컴플라이언스](./docs/40_규제/컴플라이언스.md) |
| **docs/team** | 협업 규칙 | [AI 공통 규칙](./docs/team/_공통_AI규칙.md) |
| **data/knowledge** | 승인 RAG 코퍼스 운영 | [승인 목록·검토·원격 동기화 절차](./data/knowledge/README.md) |
| **참고파일** | 하네스·도구 안내 | 팀 시작가이드·플레이북 |

## 확정 원칙

- 대상 계좌: DC형 퇴직연금·IRP·연금저축
- DC형·IRP 규칙과 연금저축 적격성 규칙을 분리
- 규칙 엔진이 계산하고 LLM은 설명·Q&A만 수행
- 시장·상품은 공식 실데이터, 사용자 계좌는 목데이터 3종
- 모든 수치에 출처·기준일 또는 가정 표시
- 실제 계좌 연결·주문·자동운용은 MVP 제외

## 서비스 로컬 실행

### 1. 최초 준비

Python 3.11 이상, [uv](https://docs.astral.sh/uv/), Node.js와 npm이 필요하다.
프로젝트 루트에서 의존성과 환경 파일을 준비한다.

```powershell
uv sync
Copy-Item .env.example .env
```

루트 `.env`의 `DATABASE_URL`에는 실제 PostgreSQL 연결 문자열을 입력해야 한다.
Supabase 로그인을 시험하려면 `VITE_SUPABASE_URL`과
`VITE_SUPABASE_PUBLISHABLE_KEY`도 입력한다. 로컬 BGE-M3 임베딩이 필요한 작업만
선택 의존성을 추가한다.

```powershell
uv sync --group embeddings
```

시크릿은 출력하거나 커밋하지 않는다. 프론트엔드용 별도 `.env`는 만들지 않는다.

### 2. 가장 쉬운 실행 — Windows

프로젝트 루트에서 실행기를 호출한다. 더블클릭해도 된다.

```powershell
.\dev.bat
```

실행기는 다음 순서로 동작한다.

1. npm, 루트 `.env`, 비어 있지 않은 `DATABASE_URL`, 8000·5173 포트를 확인한다.
2. `frontend/node_modules`가 없으면 `npm install`을 한 번 실행한다.
3. FastAPI와 Vite를 함께 실행하고 로그에 각각 `[api]`, `[web]`을 붙인다.
4. API와 화면이 준비되면 `http://127.0.0.1:5173/#guide`를 연다.
5. 실행 창에서 `Ctrl+C`를 누르거나 창을 닫으면 두 서버를 함께 종료한다.

준비 대기는 최대 120초다. `localhost`와 `127.0.0.1`은 Supabase 로그인 저장
공간이 다르므로 문서와 실행기가 사용하는 `127.0.0.1`로 통일한다.

### 3. 서버를 따로 실행

백엔드만 실행하려면 프로젝트 루트에서 다음 명령을 사용한다.

```powershell
uv run uvicorn backend.app.main:app --reload
```

프론트엔드는 새 터미널에서 실행한다. 최초 실행이거나 의존성이 바뀌었을 때만
`npm install`을 먼저 실행한다.

```powershell
Set-Location frontend
npm install
npm run dev
```

프론트엔드는 기본적으로 `http://127.0.0.1:8000`의 API에 연결한다. 다른 주소를
쓰려면 루트 `.env`의 `VITE_API_BASE_URL`과 서버 `CORS_ORIGINS`를 함께 바꾼다.

### 4. 원격 배포 운영

원격 운영 주소와 환경변수·재배포·검증 절차는 [배포 운영 가이드](./docs/30_스펙/배포_운영_가이드.md)를 정본으로 사용한다.

- 프론트: `https://kda-securities-lzix-zeta.vercel.app`
- API: `https://kda-securities.onrender.com` (Render 서비스 `KDA-securities`)
- Vercel Production: `VITE_API_BASE_URL=https://kda-securities.onrender.com`
- Render: `CORS_ORIGINS`에 실제 사용하는 Vercel Production alias를 JSON 배열로 설정

`https://pension-copilot-api.onrender.com`은 2026-07-21 이전 코드가 떠 있는 폐기된 옛 서비스다. 살아 있으면서 HTTP 200을 반환하므로 상태 확인에 사용하지 않는다.

2026-07-26 실측에서 원격 배포 복구와 골든패스 E2E를 완료했다. Render `/health` 200, API 경로 43개가 로컬 `main`과 일치하고, Production alias CORS preflight가 통과하며, Vercel 배포 번들의 API 주소도 `kda-securities.onrender.com`으로 교체됐다. 운영 프론트는 `zeta` alias 단일 운영이므로 **외부 공유·시연에는 항상 `zeta` 주소를 사용한다**(프로젝트 기본 alias인 `kda4`는 Vercel SSO로 302를 반환하며 운영에 쓰지 않는다).

### 5. API 확인

서버 실행 후 `http://127.0.0.1:8000/docs`에서 다음 API를 바로 시험할 수 있다.

| API | 역할 |
|---|---|
| `POST /chat/stream` | 인증 자연어 질문 → SSE(`phase`·`answer_delta`·선택적 `narration_update`·`response`) + 대화 저장·Idempotency-Key 재생 |
| `GET /chat/capabilities` | 인증 사용자용 현재 지원·조건부·미지원 기능 확인 |
| `GET /chat/scenarios` | 인증 사용자용 발표 목계좌 시나리오 6종 확인 |
| `GET /chat/heroes` | 인증 사용자용 목시나리오 대표 6명 확인 |
| `POST /engine/pension-tax-credit` | 연금저축·IRP 당해연도 납입액의 세액공제 교육용 추정 |
| `POST /engine/non-pension-withdrawal-estimate` | 연금외수령 시 기타소득 원천징수 최대 추정 |
| `GET /market/etfs` | KRX 기준일 전체 상장 ETF 거래량·거래대금 조회 |
| `GET /market/etfs/{isu_code}/volume-history` | 종목별 적재된 일별 거래량 이력 조회 |

`POST /chat/stream` 요청 본문 예시(Authorization Bearer token과 UUID `Idempotency-Key` 필요):

```json
{
  "message": "IRP와 연금저축의 위험자산 한도 차이를 알려줘"
}
```

- DB 없이도 검증 문서 검색과 목시나리오 규칙 엔진은 동작한다.
- `DATABASE_URL`이 있고 원격 실적재가 끝나면 FSS 회사·사업자 공시와 저장 뉴스 조회가 활성화된다. 증시 뉴스는 최근 5일의 요약 완료 기사 중 임의 3건을 `3줄 요약 → 원문 링크` 순서로 제공한다.
- `ANTHROPIC_API_KEY`는 일일 수집기의 뉴스 원문 3줄 요약, 일반 검증 답변의 선택적 Claude 재서술, `UNSUPPORTED` 질문의 선택적 Claude 재분류에 사용한다. 재분류는 `ENABLE_CLAUDE_TOPIC_GUARD=true`일 때만 `ANTHROPIC_TOPIC_GUARD_MODEL`(기본 Haiku 4.5)로 실행하며 짧은 구조화 값만 받는다. 뉴스 답변은 저장된 요약을 다시 LLM에 보내지 않고 결정론적으로 조립한다.
- 연금세액 질문은 화면의 구조화 입력 패널 값을 규칙 엔진에 전달하며, 사용자 입력은 RAG나 공시 데이터로 취급하지 않는다. Claude는 같은 읽기·계산 Tool을 호출한 뒤 결과를 설명만 한다.
- fixture는 공시 답변에 사용하지 않으며 개별 상품 비교, 미래 수익 예측, 주문은 차단한다.
- 스트림은 먼저 결정론 답변을 `answer_delta`로 보내고, Claude 내레이션이 검증을 통과했을 때만 `narration_update`로 답변 전문을 교체한다. DB·저장 응답 손상 등 스트림 도중 오류는 `error` 이벤트로 전달한다.

브라우저에서 `http://127.0.0.1:5173/#guide`를 열고 추천 질문과 직접 입력으로 챗봇을 시험할 수 있다. 사이드바(햄버거 메뉴)에서 목계좌 시나리오를 선택하면 질문과 함께 해당 `scenario_code`가 전달된다.

- 환경변수는 **루트 단일 `.env`**로 통일했다. Vite는 `envDir`로 루트를 참조하고 `VITE_` 접두사 변수만 브라우저에 노출한다. 새 환경변수는 루트 `.env.example`에만 추가한다.
- 사이드바에서 Supabase Auth 데모 계정으로 로그인하면 대화가 세션·메시지로 저장되고, 저장된 대화 목록과 데모 사용자 금융 컨텍스트(`/me/pension-context`)를 불러온다.
- 답변 화면은 사실·서비스 해석·한계, 수치 근거와 출처를 구분해 표시한다.
- 자동 테스트·curl·화면 점검 절차는 [챗봇 테스트 가이드](./docs/30_스펙/챗봇_테스트_가이드.md)를 따른다.

## 현재 상태와 다음 단계

- **검증 기준**: 2026-07-24 `main`(`8aadd15`, PR #251)에서 백엔드 `1151 passed, 1 skipped`, 프론트 `104 passed`, TypeScript 검사와 Vite production build를 통과했다.
- **통합 완료**: Supabase Auth 세션 게이트, 소유자 연금계좌 조회·집계, 저장 투자성향, 메인 홈, SSE 챗봇·RAG·뉴스·ETF 테마, 연금계산기, 전략 탐색·상세, User Pick 화면, 리밸런싱 알림, 과거 위험·스트레스 정책, Vercel/Render 설정 파일이 `main`에 있다.
- **최근 완료**: PR #239~#251에서 챗봇 웰컴 카드 CLS 스켈레톤, 벤치마킹 상세→목록 뒤로가기, ETF 3행 캐러셀·좌측 정렬, 계좌가 없을 때 연그미 마스코트·동전 선명도, 로그인·홈·전략·데스크톱 프리뷰 공통 `StatusBar`, 시연 계정 투자성향 무기록 허용목록을 반영했다.
- **부분 구현**: 계좌 연동은 동의·표시용이며 실제 금융사/MyData 연결이 아니다. User Pick은 현재 정적 benchmark iframe이라 로그인 사용자를 제외한 대표고객 5명 동적 조립은 화면에 연결되지 않았다. 전략 화면은 탐색·설명까지이며 실제 주문이나 적용 초안 저장은 없다.
- **시각 수용 완료**: 상단바 신호·Wi-Fi·배터리를 Figma 원본 path로 교체하고 전역 svg stroke 상속을 차단해 2026-07-26 사용자 검수를 통과했다. PR #249~#251은 모두 `main`에 병합됐다.
- **원격 배포 복구·골든패스 E2E 완료**: 2026-07-26 실측에서 Render `/health` 200과 API 경로 43개를 확인했고, Render LLM 환경변수 확인과 로그인 이후 화면·챗봇 골든패스 E2E를 마쳤다. 운영 프론트는 `zeta` alias 단일 운영이며 절차는 [배포 운영 가이드](./docs/30_스펙/배포_운영_가이드.md)를 따른다.
- **다음**: 리뷰 대기 PR(#362·#364) 정리, Supabase Auth 유출 비밀번호 보호 활성화·Security Advisor 확인. RAG 재청킹·재임베딩은 측정된 품질 저하가 있을 때만 검토한다.

기능별 상태·수용 기준·코드와 테스트 근거는 [기능정의서](./docs/10_기획/기능정의서.html), 기술 상세는 [아키텍처 §9~10](./docs/30_스펙/아키텍처.md#9-구현검증-상태)을 따른다.
