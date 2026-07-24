# 연금 코파일럿 프론트 세션 진입점

> 적용 범위: `frontend/` 하위 전체(React + TypeScript + Vite PWA).
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-23

## 임무

모바일 연금계좌 운용 가이드의 PWA 화면을 책임진다. 계산·판단·수치 생성은 전부 백엔드(규칙 엔진) 몫이고, 프론트는 검증된 응답을 표시만 한다. 모든 수치엔 출처 칩을 유지한다.

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- 파일 수정 전에 `git-session-manager`로 담당자와 예상 수정 경로를 claim한다. 루트 `main` 관제 워크트리에서는 수정하지 않는다.
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다.
- 작업은 최신 `origin/main`에서 만든 `front/<owner>/<task>` 브랜치·전용 워크트리에서 하고 첫 커밋 후 Draft PR을 연다. 병합 브랜치 재사용과 `main` 직접 push는 금지한다.
- `App.tsx`·`api/types.ts`·`GuidePage.tsx`·`MainHomeScreen.tsx`는 공유 핫스팟이다. 다른 active claim/PR과 겹치면 이재용이 단일 작성자를 지정하기 전까지 수정하지 않는다.
- **라우트 지도 동기화**: 화면·라우팅 구조를 바꾸면(`App.tsx`의 `<Route>` 추가·삭제, `pages/*` 화면 신설·삭제·역할 변경, 진입 경로·데이터 출처 변경) [docs/30_스펙/프론트_라우트_화면_지도.html](../docs/30_스펙/프론트_라우트_화면_지도.html)를 같은 PR에서 갱신한다. CSS·문구 등 구조와 무관한 변경은 예외다. CI `route-map-sync`가 이를 강제하며(변경 diff 기준), 정당한 예외 PR에는 `route-map-exempt` 라벨을 붙인다.

## 소유·금지 경계

| 구분 | 경로 |
|---|---|
| 소유(수정 가능) | `frontend/**` |
| 백엔드 전체(읽기만) | `backend/**`, `supabase/**`, `tests/**` — API 동작이 이상하면 수정하지 말고 계약 절차로 해당 세션에 요청 |
| 공유 파일(최소 diff + PR 명시) | `.env.example` (환경변수는 루트 단일 `.env`, `VITE_` 접두사만 브라우저 노출 — frontend 별도 `.env` 만들지 않는다) |

## 세션 간 계약 (변경 시 PR에 `계약 변경` 표시 + 상대 세션·이재용 합의)

- **챗봇과**: SSE 이벤트(`phase`/`answer_delta`/`response`/`error`) 파싱(`src/api/client.ts`), `src/api/types.ts` ↔ 백엔드 `backend/app/chat/models.py` 스키마 동기.
- **백엔드 API 전반**: 엔드포인트 추가·응답 필드 변경이 필요하면 임의로 백엔드를 고치지 말고 계약 변경으로 요청한다.
- 화면 설계 근거: [docs/10_기획/기획서.md](../docs/10_기획/기획서.md).

## 화면 프레임·상단바 규칙 (신규·수정 화면 강제)

라우트로 노출되는 **모든 화면은 main-home 프레임 규격에 픽셀 단위로 고정**하고 **Figma 상단바를 갖는다**. 예외 없이 아래를 지킨다.

- **프레임(크기)**: 화면 최상위를 `app-phone-stage`(무대) + `app-phone-frame`(폰 프레임)으로 감싼다. 치수·라운드·그림자는 `src/index.css`의 `--phone-frame-*` 변수(SSOT)만 값의 출처다. `width`/`height`/`border-radius`를 개별 화면 CSS에 하드코딩하지 않는다(특히 `min(844px, …)` 리터럴 금지). 화면 고유 레이아웃(예: `display:flex` 내부 컬럼)은 별도 클래스로 덧붙이되 치수는 건드리지 않는다.
- **상단바**: 화면 프레임 최상단에 `<StatusBar />`(`src/components/StatusBar.tsx`)를 렌더한다. 상단바는 Figma StatusBar(다이나믹 아일랜드 + 셀룰러·Wi‑Fi·배터리)를 재현하며 임의로 아이콘을 빼거나 크기를 바꾸지 않는다.
- **iframe 화면(profile-html·slangi 등 100vh iframe)**: 프레임과 상단바를 iframe 내부 HTML이 소유한다. 이때도 내부 HTML은 같은 프레임 규격(`min(844px, calc(100dvh - 80px))`, radius 44, 상단바 54px)을 따른다. 이 목록은 `src/phoneFrameContract.test.ts`의 허용 목록과 일치시킨다.
- **강제(게이트)**: `src/phoneFrameContract.test.ts`가 위 규칙을 검사한다. 새 화면이 공용 프레임을 쓰지 않거나 치수를 하드코딩하면 `npm test`가 실패한다. 새 라우트 화면을 추가하면 이 테스트를 통과시키거나(권장) iframe 위임 화면이면 허용 목록에 등록한다.

## 검증 명령

```powershell
cd frontend
npm run build    # TypeScript 컴파일 + 번들 — 타입 계약 위반이 여기서 잡힌다
npm test         # vitest
```

- 백엔드 연동 확인이 필요하면 루트에서 `uv run python scripts/dev.py`(또는 `.claude/launch.json`의 dev 서버)로 로컬 기동.
- 표시 규칙: 미래 수익 예측·확정 표현 금지, 성향 밖 상품 제안 금지, 출처 칩 항상 표시.

## 핸드오프

- PR 본문에: 변경 요약 / 계약 변경 여부 / build·test 결과 / 스크린샷(화면 변경 시) / 라우트·화면 변경 시 라우트 지도 HTML 갱신 / 금지 경로 미수정 확인.
