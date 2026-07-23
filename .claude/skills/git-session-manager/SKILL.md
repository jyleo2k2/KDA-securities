---
name: git-session-manager
description: 병렬 개발 세션의 브랜치·워크트리 생성, 작업 범위 claim, 활성 세션 상태, 공유 핫스팟과 열린 PR 겹침, heartbeat, release를 관리하는 Git 오케스트레이터. 새 코드 작업 시작, 새 브랜치·워크트리 생성, 여러 Claude/Codex 세션 병렬 실행, 팀원 PR 충돌 예방, 세션 상태 확인, 후속 작업 재개·업데이트·수정·보완 요청 시 반드시 사용한다. 단순 Git 이력 조회만 필요하거나 병합 완료 대상을 삭제하는 작업은 git-pr-cleanup을 사용한다.
---

# Git Session Manager

병렬 작업이 서로의 워크트리와 공유 파일을 침범하지 않도록 Git 세션을 단일 관제한다.

## 실행 모드: 감독자·단일 Git 작성자

Git ref와 worktree 메타데이터는 저장소 전체가 공유한다. 여러 에이전트가 동시에 생성·삭제하면 경합하므로 `git-coordinator` 한 명만 세션 생성·release·정리를 수행한다. 구현 워커는 할당받은 워크트리와 claim 범위에서만 작업한다.

## Phase 0: 컨텍스트 확인

1. `uv run python scripts/git_session_manager.py status`를 실행한다.
2. `git status --short --branch`와 `git worktree list`를 확인한다.
3. 현재 워크트리가 기존 active claim이면 후속 실행으로 판단하고 heartbeat 후 계속한다.
4. claim이 없으면 새 세션 또는 기존 워크트리 등록 절차로 이동한다.
5. 다른 세션의 dirty 파일은 수정·stash·reset·checkout하지 않는다.

## Phase 1: 작업 세션 확보

### 새 작업

깨끗한 `main` 관제 워크트리에서 실행한다.

```powershell
uv run python scripts/git_session_manager.py start \
  --tool <codex|claude> \
  --worker <팀원-실명> \
  --task <ascii-task-slug> \
  --path <예상-수정-경로>
```

경로가 여러 개면 `--path`를 반복한다. 생성된 워크트리로 이동한 뒤에만 수정한다.

### 이미 존재하는 작업 워크트리

```powershell
uv run python scripts/git_session_manager.py claim \
  --tool <codex|claude> \
  --worker <팀원-실명> \
  --path <예상-수정-경로>
```

브랜치는 `<도구>/<작업자>/<작업명>` 형식을 사용한다.

- 도구: `codex`, `claude`만 허용한다.
- 작업자: `이재용`, `이태호`, `최호성`, `진재현`, `김태형`, `정인성`만 허용한다.
- 작업명: 영문 소문자 또는 숫자로 시작하고 영문 소문자·숫자·`-_.`만 사용한다. `~`는 예시 표기에도 실제 브랜치에는 넣지 않는다.
- 브랜치에서 파싱한 도구·작업자와 세션 등록 정보가 다르면 세션 시작과 파일 편집을 모두 차단한다.
- 구형 브랜치는 `status`·`release` 등 정리 작업만 허용한다. 추가 작업은 최신 `main`에서 새 규칙 브랜치로 옮긴다.
- 병합된 브랜치를 후속 PR에 재사용하지 않는다.

## Phase 2: 충돌 예방

1. claim이 활성 로컬 세션 또는 열린 PR과 겹치면 작업을 중단한다.
2. 공유 핫스팟이 겹치면 이재용이 단일 작성자를 지정한다.
3. 로컬 claim 겹침은 승인 문자열로 우회하지 않는다. 기존 범위를 분할하거나 release한다.
4. 원격 PR 핫스팟 겹침은 이재용이 GitHub에서 직접 `hotspot-approved` 라벨을 붙인 경우에만 허용한다.
5. 상세 핫스팟과 역할 분리는 [team-git-policy.md](references/team-git-policy.md)를 따른다.
6. 프론트 팀원은 신규 화면·컴포넌트를 독립 구현하고, `App.tsx` 등 공용 연결은 통합 오너의 별도 PR로 넘긴다.
7. 백엔드·프론트 계약 변경은 계약 PR → 백엔드 → 프론트 → 통합 연결 순으로 병합한다.

## Phase 3: 작업과 PR

1. claim 범위 안에서만 수정한다. 범위가 늘면 먼저 claim을 갱신한다.
2. 첫 의미 있는 커밋을 push한 직후 Draft PR을 만든다.
3. PR 템플릿의 담당자, 작업 범위, 공유 핫스팟, 계약 변경을 채운다.
4. Ready 전과 의존 계약 PR 병합 직후에만 최신 `main`을 반영한다.
5. `main`에 직접 commit·push하지 않는다.
6. 세션을 장시간 유지하면 heartbeat를 기록한다.

```powershell
uv run python scripts/git_session_manager.py heartbeat
```

## Phase 4: 종료와 정리

작업을 넘겼거나 PR을 병합한 뒤 claim을 release한다.

```powershell
uv run python scripts/git_session_manager.py release
```

release는 파일·브랜치·워크트리를 삭제하지 않는다. 병합 완료 정리는 `git-pr-cleanup`을 사용하여 PR 병합, `origin/main` 조상, clean worktree, ignored 산출물 보고를 재검증한 뒤 수행한다.

## 에러 핸들링

- `main` 수정 차단: 새 작업 워크트리를 생성한다.
- 브랜치 이름 거부: 재사용하지 않은 `<도구>/<작업자>/<작업명>` 이름으로 다시 만든다.
- 구형 브랜치 또는 세션 신원 불일치: 작업을 중단하고 최신 `main`에서 새 규칙 브랜치를 만든다.
- 로컬 claim 겹침: 기존 세션 소유자와 범위를 분할한다.
- 열린 PR 겹침: 신규 모듈과 공용 연결 PR을 분리한다.
- GitHub 조회 실패: 로컬 claim만 유지하고 PR 생성 전 CI 정책 검사를 반드시 통과한다.
- worktree/registry 잠금: Git 관제 작업을 병렬로 재시도하지 말고 기존 작업이 끝난 뒤 다시 실행한다.

## 테스트 시나리오

### 정상 흐름

1. 프론트 신규 화면 작업 요청을 받는다.
2. `codex/진재현/strategy-screen`과 전용 워크트리를 생성한다.
3. 신규 화면 경로만 claim하고 Draft PR을 연다.
4. 통합 오너가 별도 브랜치에서 `App.tsx` 연결을 수행한다.
5. 두 PR 병합 후 release하고 `git-pr-cleanup`으로 정리한다.

### 충돌 흐름

1. 두 세션이 `frontend/src/App.tsx`를 claim한다.
2. 두 번째 claim을 차단하고 기존 세션·PR을 표시한다.
3. 이재용이 단일 작성자를 지정한다.
4. 다른 세션은 신규 컴포넌트만 남기도록 범위를 축소한다.
