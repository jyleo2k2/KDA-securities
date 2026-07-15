# Claude Code CLI 설치 가이드 (팀원용)

> 대상: 이 프로젝트(`finance-project-1`)에서 Claude Code를 처음 쓰는 팀원. 순서대로 따라오면 끝.

## 1. Node.js 확인

터미널에서:
```
node -v
```
`v18` 이상이면 통과. 없거나 낮으면 [nodejs.org](https://nodejs.org)에서 LTS 버전 설치.

## 2. Claude Code 설치

```
npm install -g @anthropic-ai/claude-code
```

확인:
```
claude --version
```

## 3. 로그인

```
claude
```
처음 실행하면 로그인 안내가 뜸. Anthropic 계정(Claude Pro/Max) 또는 API 키로 로그인.

## 4. 프로젝트 열기

```
git clone <이 저장소 주소>
cd finance-project-1
claude
```

**여기서 별도로 할 일 없음.** 아래 항목은 저장소에 이미 들어있어서 `claude` 실행하는 순간 자동 적용됨:
- `CLAUDE.md` — 프로젝트 규칙(세션 시작 시 자동으로 읽힘)
- `.claude/settings.json` — `.py` 파일 수정 시 자동 ruff 검사, 턴 종료 시 자동 pytest
- `.claude/skills/user-flow-diagram` — 유저 플로우 다이어그램 스킬

## 5. 우리 팀이 쓰는 플러그인 (선택 설치)

`claude` 실행 중에 슬래시 명령으로 설치. 마켓플레이스 추가 → 플러그인 설치, 2줄이면 됨.

| 플러그인 | 용도 | 설치 명령 |
|---|---|---|
| **superpowers** (권장) | 브레인스토밍·TDD·체계적 디버깅 등 작업 프로세스 스킬 모음 | `/plugin marketplace add anthropics/claude-plugins-official` → `/plugin install superpowers@claude-plugins-official` |
| **harness** (권장) | 이 프로젝트가 쓰는 하네스(전문 에이전트/스킬 구성) 메타 스킬 | `/plugin marketplace add revfactory/harness` → `/plugin install harness@harness-marketplace` |
| **claude-mem** | 세션 넘어서도 이전 작업 기억·검색 | `/plugin marketplace add thedotmack/claude-mem` → `/plugin install claude-mem@thedotmack` |
| **figma** | 프론트엔드 작업 시 Figma 디자인 연동 | `/plugin marketplace add anthropics/claude-plugins-official` (이미 추가했으면 생략) → `/plugin install figma@claude-plugins-official` |
| **andrej-karpathy-skills** | 과설계 방지, 코드 리뷰 가이드라인 | `/plugin marketplace add forrestchang/andrej-karpathy-skills` → `/plugin install andrej-karpathy-skills@karpathy-skills` |
| **claude-dashboard** | 터미널 상태바에 AI CLI 사용량(토큰/한도) 표시 (개인 취향) | `/plugin marketplace add uppinote20/claude-dashboard` → `/plugin install claude-dashboard@claude-dashboard` |

> `code-review`, `verify`, `run`, `init` 같은 스킬은 Claude Code에 기본 내장이라 설치 불필요.

## 6. 설치 확인

`claude` 안에서:
```
/plugin
```
설치된 플러그인 목록이 뜨면 정상.

## 7. 다음

- Python/uv 등 개발 환경 세팅은 [README.md](../../README.md) 참고
- 프로젝트 규칙·절대 규칙은 `claude` 켜면 `CLAUDE.md`가 자동으로 알려주니 따로 외울 필요 없음
