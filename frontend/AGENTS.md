# 연금 코파일럿 프론트 세션 진입점

> 적용 범위: `frontend/` 하위 전체(React + TypeScript + Vite PWA).
> 이 파일과 같은 폴더의 `AGENTS.md`·`CLAUDE.md`는 내용 동기화 대상이다. 한쪽을 바꾸면 같은 커밋에서 다른 쪽도 바꾼다.
> 최종 갱신: 2026-07-19

## 임무

모바일 연금계좌 운용 가이드의 PWA 화면을 책임진다. 계산·판단·수치 생성은 전부 백엔드(규칙 엔진) 몫이고, 프론트는 검증된 응답을 표시만 한다. 모든 수치엔 출처 칩을 유지한다.

## 세션 시작 규칙

- 루트 `CLAUDE.md`/`AGENTS.md` → 헌장 → 이 파일 순서로 읽는다.
- `git fetch origin main` 후 뒤처졌으면 리베이스한다(트리가 더티면 소유자 확인 → 본인 것만 커밋/스태시).
- 다른 세션의 WIP를 수정·stash·reset·checkout하지 않는다.
- 작업은 `front/` 접두사 브랜치에서 하고 PR로 낸다. `main` 직접 push 금지.

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

## 검증 명령

```powershell
cd frontend
npm run build    # TypeScript 컴파일 + 번들 — 타입 계약 위반이 여기서 잡힌다
npm test         # vitest
```

- 백엔드 연동 확인이 필요하면 루트에서 `uv run python scripts/dev.py`(또는 `.claude/launch.json`의 dev 서버)로 로컬 기동.
- 표시 규칙: 미래 수익 예측·확정 표현 금지, 성향 밖 상품 제안 금지, 출처 칩 항상 표시.

## 핸드오프

- PR 본문에: 변경 요약 / 계약 변경 여부 / build·test 결과 / 스크린샷(화면 변경 시) / 금지 경로 미수정 확인.
