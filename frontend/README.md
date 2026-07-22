# frontend — React + TypeScript + Vite PWA 골격

> 담당: 최호택·진재현 (헌장 §5). 이 골격은 아키텍처 경계·REST 계약을 잡기 위한
> 초기 스캐폴드이며, 화면 구현은 담당자가 이어받는다.

## 실행

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

백엔드는 저장소 루트에서 실행한다 (홈 탭의 연결 배지가 `/health`를 호출):

```bash
uv run uvicorn backend.app.main:app --reload
```

빌드 검증: `npm run build` (tsc 타입검사 + vite build).

환경변수는 **레포 루트의 단일 `.env`** 를 참조한다(`vite.config.ts`의 `envDir:".."`).
프론트 전용 `.env`는 두지 않으며, 브라우저에 노출되는 값은 `VITE_` 접두사만 사용한다
(`VITE_API_BASE_URL`·`VITE_SUPABASE_URL`·`VITE_SUPABASE_PUBLISHABLE_KEY`). 템플릿: 루트 `.env.example`.

## 구조·의도

- `src/api/types.ts` — FastAPI REST 계약 타입. **백엔드 Decimal 필드는 JSON
  문자열**이므로 금액·비율 타입이 `string`이다(계약임, 실수 아님).
- `src/api/client.ts` — 최소 fetch 래퍼(`VITE_API_BASE_URL`, 기본
  `http://127.0.0.1:8000`).
- `src/pages/` — 하단탭 4개(홈·연금가이드·벤치마크·프로필) 플레이스홀더.
- **상태관리 라이브러리는 의도적으로 미도입** — 화면 상태는 각 React 컴포넌트의
  `useState`/`useEffect`가 소유한다. 로그인 전환·사용자 전환 시 사용자별 화면 상태와
  `pension-copilot:*` localStorage 키를 비우며, 장기 보관이 필요한 투자성향·계좌·대화는
  서버가 SSOT다. Supabase는 로그인 세션만 유지하고, URL hash는 현재 화면 위치만 보존한다.
- PWA 매니페스트는 `vite.config.ts`의 `VitePWA` 설정에 있다.

## PWA 상태·캐시 정책

- Cache Storage에는 Vite가 revision을 붙인 정적 앱 자산만 precache한다. 새 배포는
  `autoUpdate`로 갱신한다.
- FastAPI `GET`/`POST`/`DELETE`, 인증 요청, 계좌·투자성향·대화 데이터 및 챗봇 SSE는
  모두 `cache: "no-store"`다. 서비스 워커에도 API runtime cache 규칙을 두지 않는다.
  따라서 로그아웃·사용자 전환 뒤 이전 사용자의 응답이 브라우저 캐시에서 재사용되지 않는다.
- 챗봇의 스트리밍 답변과 임시 입력은 메모리 상태이며 새로고침 시 복원하지 않는다. 저장된
  대화는 인증된 서버 API로 다시 조회한다.
- API 응답의 TTL, 재검증, 무효화는 클라이언트 캐시가 아니라 서버 데이터·인증 갱신에 따른다.
  성능상 별도 캐시가 필요해지면 인증 경계, 소유자 전환, 명시적인 무효화 조건을 포함한
  별도 계약을 먼저 추가한다.

## 지켜야 할 경계 (헌장)

- 의존 방향: frontend → FastAPI REST만. 엔진·DB 직접 접근 금지.
- 계산은 규칙 엔진 결과를 표시만 한다. 프론트에서 수익률·한도 재계산 금지.
- 모든 수치에 출처 칩·기준일 표시. `service_role`/secret 키 사용 금지
  (Auth는 publishable key만).
- 공유 계약(`src/api/types.ts`) 변경 시 PR에 `계약 변경` 명시.
