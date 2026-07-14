# Talk To Figma MCP — Windows 설치·실행 가이드

> 대상: Windows 10 1809 이상, Figma Desktop, Codex 또는 Claude Code 사용자  
> 검증 기준: 2026-07-14  
> 구현체: [`grab/cursor-talk-to-figma-mcp`](https://github.com/grab/cursor-talk-to-figma-mcp)

## 1. 무엇을 해결하는가

Talk To Figma MCP는 현재 Figma Desktop에서 열어 둔 문서를 AI 클라이언트가 Figma Plugin API를 통해 읽거나 수정하게 해준다.

```text
Codex / Claude Code
        │ STDIO MCP
        ▼
TalkToFigma MCP 서버
        │ WebSocket: localhost:3055
        ▼
Figma의 Talk To Figma MCP Plugin
        │ Figma Plugin API
        ▼
현재 열려 있는 Figma 문서
```

공식 Figma MCP의 읽기 제한 때문에 이 방식을 사용하는 경우에도 다음 제약은 남는다.

- Figma Desktop과 대상 문서를 열어 둬야 한다.
- 대상 문서에서 플러그인이 실행 중이어야 한다.
- 플러그인 설치 승인과 `Connect` 클릭은 Figma 화면에서 직접 해야 한다.
- 플러그인은 읽기뿐 아니라 생성·수정·삭제 도구도 제공한다. 처음에는 반드시 읽기 전용으로 요청한다.

## 2. 가장 빠른 설치: PowerShell 한 번 실행

### 사전 조건

- Codex CLI 또는 Claude Code 중 하나 이상이 설치되어 있어야 한다.
- Figma Desktop에 로그인할 수 있어야 한다.
- 회사 PC라면 GitHub, `bun.sh`, Figma Community 접근이 허용되어야 한다.

아래 블록은 다음 작업을 한 번에 수행한다.

1. Git이 없으면 `winget`으로 설치
2. Bun이 없으면 공식 설치 스크립트로 설치
3. `%USERPROFILE%\dev\tools\cursor-talk-to-figma-mcp`에 저장소 설치
4. 의존성 설치
5. Codex와 Claude Code에 `TalkToFigma`를 사용자 전역으로 등록
6. `localhost:3055` WebSocket 브리지를 숨김 창으로 실행
7. Figma Community 플러그인 페이지 열기

PowerShell을 일반 권한으로 열고 블록 전체를 한 번에 붙여넣는다.

```powershell
$ErrorActionPreference = 'Stop'

$repoUrl = 'https://github.com/grab/cursor-talk-to-figma-mcp.git'
$toolsRoot = Join-Path $env:USERPROFILE 'dev\tools'
$repo = Join-Path $toolsRoot 'cursor-talk-to-figma-mcp'
$server = Join-Path $repo 'src\talk_to_figma_mcp\server.ts'
$pluginUrl = 'https://www.figma.com/community/plugin/1485687494525374295/cursor-talk-to-figma-mcp-plugin'

Write-Host '[1/7] Git 확인'
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) {
    $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $wingetCommand) {
        throw 'Git과 winget이 없습니다. https://git-scm.com/download/win 에서 Git을 설치한 뒤 다시 실행하세요.'
    }

    winget install --id Git.Git -e --source winget `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Git 설치 실패: exit code $LASTEXITCODE"
    }

    $gitCandidates = @(
        (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe')
    )
    $gitPath = $gitCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $gitPath) {
        throw 'Git은 설치됐지만 현재 터미널에서 찾지 못했습니다. PowerShell을 다시 열고 이 블록을 재실행하세요.'
    }
} else {
    $gitPath = $gitCommand.Source
}

Write-Host '[2/7] Bun 확인'
$bunCommand = Get-Command bun -ErrorAction SilentlyContinue
if (-not $bunCommand) {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `
        "Invoke-RestMethod https://bun.sh/install.ps1 | Invoke-Expression"
    if ($LASTEXITCODE -ne 0) {
        throw "Bun 설치 실패: exit code $LASTEXITCODE"
    }
    $bunPath = Join-Path $env:USERPROFILE '.bun\bin\bun.exe'
} else {
    $bunPath = $bunCommand.Source
}
if (-not (Test-Path -LiteralPath $bunPath)) {
    throw "Bun 실행 파일을 찾을 수 없습니다: $bunPath"
}

Write-Host '[3/7] 저장소와 의존성 설치'
New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $repo)) {
    & $gitPath clone --depth 1 $repoUrl $repo
    if ($LASTEXITCODE -ne 0) {
        throw "저장소 복제 실패: exit code $LASTEXITCODE"
    }
} elseif (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    throw "대상 경로가 이미 존재하지만 Git 저장소가 아닙니다: $repo"
} else {
    Write-Host "기존 저장소를 재사용합니다: $repo"
}

Push-Location $repo
try {
    & $bunPath install
    if ($LASTEXITCODE -ne 0) {
        throw "의존성 설치 실패: exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
if (-not (Test-Path -LiteralPath $server)) {
    throw "MCP 서버 파일을 찾을 수 없습니다: $server"
}

Write-Host '[4/7] Codex 전역 MCP 등록'
$codexCommand = Get-Command codex -ErrorAction SilentlyContinue
if ($codexCommand) {
    & $codexCommand.Source mcp remove TalkToFigma 2>$null
    & $codexCommand.Source mcp add TalkToFigma -- $bunPath $server
    if ($LASTEXITCODE -ne 0) {
        throw "Codex MCP 등록 실패: exit code $LASTEXITCODE"
    }
} else {
    Write-Warning 'codex 명령이 없어 Codex 등록은 건너뜁니다.'
}

Write-Host '[5/7] Claude Code 사용자 전역 MCP 등록'
$claudeCommand = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCommand) {
    & $claudeCommand.Source mcp remove TalkToFigma --scope user 2>$null
    & $claudeCommand.Source mcp add --transport stdio --scope user TalkToFigma -- $bunPath $server
    if ($LASTEXITCODE -ne 0) {
        throw "Claude Code MCP 등록 실패: exit code $LASTEXITCODE"
    }
} else {
    Write-Warning 'claude 명령이 없어 Claude Code 등록은 건너뜁니다.'
}

if (-not $codexCommand -and -not $claudeCommand) {
    throw 'Codex CLI와 Claude Code를 모두 찾지 못했습니다. 사용할 AI 클라이언트를 설치한 뒤 다시 실행하세요.'
}

Write-Host '[6/7] localhost:3055 WebSocket 브리지 실행'
$listener = Get-NetTCPConnection -LocalPort 3055 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    $listenerProcess = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if (-not $listenerProcess -or $listenerProcess.ProcessName -notmatch '^bun$') {
        $processName = if ($listenerProcess) { $listenerProcess.ProcessName } else { '알 수 없음' }
        throw "3055 포트를 다른 프로세스가 사용 중입니다: PID $($listener.OwningProcess), $processName"
    }
    Write-Host "기존 Bun 브리지를 재사용합니다: PID $($listener.OwningProcess)"
} else {
    $stdoutLog = Join-Path $repo 'socket-current.log'
    $stderrLog = Join-Path $repo 'socket-current.err.log'
    $bridge = Start-Process -FilePath $bunPath `
        -ArgumentList @('run', 'src/socket.ts') `
        -WorkingDirectory $repo `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Start-Sleep -Seconds 2
    $listener = Get-NetTCPConnection -LocalPort 3055 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        Write-Host '--- stdout ---'
        Get-Content -LiteralPath $stdoutLog -Tail 20 -ErrorAction SilentlyContinue
        Write-Host '--- stderr ---'
        Get-Content -LiteralPath $stderrLog -Tail 20 -ErrorAction SilentlyContinue
        throw "WebSocket 브리지가 시작되지 않았습니다. 시작 PID: $($bridge.Id)"
    }
    Write-Host "WebSocket 브리지 실행 완료: PID $($listener.OwningProcess)"
}

Write-Host '[7/7] Figma 플러그인 페이지 열기'
Start-Process $pluginUrl

Write-Host ''
Write-Host '설치 자동화 완료' -ForegroundColor Green
Write-Host "저장소: $repo"
Write-Host '브리지: ws://localhost:3055'
if ($codexCommand) { & $codexCommand.Source mcp get TalkToFigma }
if ($claudeCommand) { & $claudeCommand.Source mcp get TalkToFigma }
Write-Host ''
Write-Host '다음 단계: Figma에서 플러그인 설치 → 대상 파일에서 실행 → 포트 3055로 Connect → Channel ID 복사'
Write-Host 'Codex/Claude는 새 MCP 설정을 읽도록 완전히 재시작하세요.'
```

### 자동화 범위의 한계

Figma Community 플러그인 설치는 Figma 계정 권한과 사용자 승인이 필요하므로 PowerShell이 대신 클릭하지 않는다. 위 스크립트는 플러그인 페이지까지 자동으로 연다.

이미 같은 이름의 `TalkToFigma` MCP가 있으면 해당 항목만 현재 PC의 경로로 다시 등록한다. 다른 MCP 설정은 변경하지 않는다. 기존 도구 저장소가 있으면 자동 `pull`하지 않고 그대로 재사용한다.

## 3. Figma에서 연결하기

1. 자동으로 열린 Community 페이지에서 **Install**을 누른다.
2. Figma Desktop에서 읽을 파일을 연다.
3. **Plugins → Talk To Figma MCP Plugin**을 실행한다.
4. 포트가 `3055`인지 확인하고 **Connect**를 누른다. 플러그인이 자동 연결을 시도했다면 연결 상태만 확인한다.
5. 화면에 표시되는 임의의 **Channel ID**를 복사한다.
6. Codex 또는 Claude Code를 완전히 재시작한다. Codex 앱·CLI·IDE 확장은 같은 Codex MCP 설정을 공유하지만, 새 설정 적용에는 재시작이 필요하다.

## 4. 첫 읽기 테스트

AI 클라이언트에 다음 문장을 붙여넣고 `<채널 ID>`만 바꾼다.

```text
TalkToFigma의 join_channel 도구로 채널 <채널 ID>에 연결해.
그다음 get_document_info와 get_selection만 호출해서 현재 문서 구조와 선택 항목을 요약해.
지금은 읽기 전용 조사이므로 생성·수정·삭제 도구는 호출하지 마.
```

성공 기준은 다음과 같다.

- `join_channel`: 성공
- `get_document_info`: 현재 Figma 문서의 페이지·노드 구조 반환
- `get_selection`: 현재 선택 항목 반환
- Figma 문서에 변경사항이 생기지 않음

큰 문서는 한 번에 전체 내용을 읽기보다 페이지나 프레임의 node ID를 먼저 찾고 `get_node_info`로 나눠 읽는다.

## 5. 재부팅 후 다시 실행

전역 MCP 등록과 저장소 설치는 유지되지만 3055 브리지는 재부팅하면 종료된다. 다음 블록만 실행하면 된다.

```powershell
$repo = Join-Path $env:USERPROFILE 'dev\tools\cursor-talk-to-figma-mcp'
$bun = Join-Path $env:USERPROFILE '.bun\bin\bun.exe'
$listener = Get-NetTCPConnection -LocalPort 3055 -State Listen -ErrorAction SilentlyContinue

if (-not $listener) {
    Start-Process -FilePath $bun `
        -ArgumentList @('run', 'src/socket.ts') `
        -WorkingDirectory $repo `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $repo 'socket-current.log') `
        -RedirectStandardError (Join-Path $repo 'socket-current.err.log')
    Start-Sleep -Seconds 2
}

Get-NetTCPConnection -LocalPort 3055 -State Listen
```

그다음 Figma 대상 파일에서 플러그인을 다시 실행하고 새로 표시된 Channel ID로 `join_channel`을 호출한다.

## 6. 상태 확인과 종료

### 설치 상태

```powershell
bun --version
codex mcp get TalkToFigma
claude mcp get TalkToFigma
```

설치되지 않은 AI 클라이언트의 명령은 생략한다.

### 포트와 로그

```powershell
Get-NetTCPConnection -LocalPort 3055 -State Listen

$repo = Join-Path $env:USERPROFILE 'dev\tools\cursor-talk-to-figma-mcp'
Get-Content -LiteralPath (Join-Path $repo 'socket-current.log') -Tail 30
Get-Content -LiteralPath (Join-Path $repo 'socket-current.err.log') -Tail 30
```

### 브리지 종료

먼저 프로세스가 Bun인지 확인한 뒤 종료한다.

```powershell
$connection = Get-NetTCPConnection -LocalPort 3055 -State Listen -ErrorAction Stop |
    Select-Object -First 1
Get-Process -Id $connection.OwningProcess

# 위 출력의 ProcessName이 bun인 것을 확인한 다음 실행
Stop-Process -Id $connection.OwningProcess
```

## 7. 문제 해결

### `bun` 명령을 찾지 못함

현재 터미널을 닫고 새 PowerShell을 연다. 그래도 안 되면 직접 실행해 확인한다.

```powershell
& "$env:USERPROFILE\.bun\bin\bun.exe" --version
```

직접 실행은 되지만 `bun`만 실패한다면 사용자 PATH에 `%USERPROFILE%\.bun\bin`을 추가하고 터미널을 다시 연다. 자세한 내용은 [Bun Windows 설치 문서](https://bun.sh/docs/installation)를 참고한다.

### `TalkToFigma`가 MCP 목록에 없음

```powershell
codex mcp list
claude mcp list
```

등록돼 있는데 현재 세션에서 도구가 보이지 않으면 Codex 앱·IDE 확장 또는 Claude Code를 완전히 종료한 뒤 다시 시작한다.

### 플러그인이 `localhost:3055`에 연결되지 않음

```powershell
Get-NetTCPConnection -LocalPort 3055 -State Listen
```

출력이 없으면 §5의 재실행 블록을 사용한다. VPN·보안 프로그램이 로컬 WebSocket을 차단하는지도 확인한다.

### `Must join a channel before sending commands`

Figma 플러그인 화면의 Channel ID를 정확히 복사해 먼저 `join_channel`을 호출한다. Figma 플러그인을 다시 열면 채널이 바뀔 수 있다.

### 포트 3055가 이미 사용 중

```powershell
$connection = Get-NetTCPConnection -LocalPort 3055 -State Listen |
    Select-Object -First 1
Get-Process -Id $connection.OwningProcess
```

기존 Talk To Figma용 Bun이면 그대로 사용한다. 다른 프로그램이면 그 프로그램의 용도를 확인한 뒤 종료하거나 포트 구성을 별도로 맞춰야 한다.

### Figma 문서를 읽지만 응답이 너무 큼

`get_document_info`로 전체 구조만 확인한 다음 필요한 페이지·프레임의 node ID를 지정해 `get_node_info`로 나눠 읽는다. 텍스트 탐색은 chunking을 지원하는 도구를 사용한다.

## 8. 보안 수칙

- 네이티브 Windows에서는 `src/socket.ts`의 hostname을 `0.0.0.0`으로 바꾸지 않는다. 기본 `localhost`를 유지한다.
- 회사 기밀 디자인은 사내 정책상 허용된 AI 계정과 PC에서만 연다.
- 첫 요청에는 항상 `읽기 전용`, `수정 금지`를 명시한다.
- 수정이 필요할 때도 대상 node ID와 변경 범위를 먼저 확인하고, 변경 후 `get_node_info`로 검증한다.
- 알 수 없는 MCP 저장소나 변조된 플러그인 대신 아래 원 저장소와 공식 Community 페이지를 사용한다.

## 9. 참고 자료

- [Talk To Figma MCP 원 저장소](https://github.com/grab/cursor-talk-to-figma-mcp)
- [Figma Community 플러그인](https://www.figma.com/community/plugin/1485687494525374295/cursor-talk-to-figma-mcp-plugin)
- [Bun Windows 설치](https://bun.sh/docs/installation)
- [Codex MCP 설정](https://learn.chatgpt.com/docs/extend/mcp)
- [Claude Code MCP 설정](https://code.claude.com/docs/en/mcp)

