from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WINDOWS_SCRIPTS = _ROOT / "scripts" / "windows"
_DEV_SCRIPT = _ROOT / "scripts" / "dev.py"


def _read(name: str) -> str:
    return (_WINDOWS_SCRIPTS / name).read_text(encoding="utf-8")


def test_repo_root_is_resolved_after_parameter_binding_for_windows_powershell() -> None:
    for name in (
        "start-chatbot.ps1",
        "stop-chatbot.ps1",
        "install-chatbot-shortcuts.ps1",
    ):
        script = _read(name)
        assert '[string]$RepoRoot = (Resolve-Path' not in script
        assert "if ([string]::IsNullOrWhiteSpace($RepoRoot))" in script


def test_start_launcher_is_local_main_only_and_hides_server_windows() -> None:
    script = _read("start-chatbot.ps1")

    assert 'branch -ne "main"' in script
    assert '"--host", "127.0.0.1"' in script
    assert "0.0.0.0" not in script
    assert "WindowStyle Hidden" in script
    assert "DATABASE_URL" in script
    assert 'ChatUrl = "$FrontendUrl/#guide"' in script
    assert 'LauncherErrorLog = Join-Path $LogRoot "launcher-error.log"' in script


def test_stop_launcher_only_uses_recorded_pid_and_start_time() -> None:
    script = _read("stop-chatbot.ps1")

    assert "server-processes.json" in script
    assert "recorded_at" not in script
    assert "started_at" in script
    assert "Stop-ProcessTree" in script
    assert "Get-Process -Id" in script


def test_shortcut_installer_keeps_non_main_access_explicitly_development_only() -> None:
    script = _read("install-chatbot-shortcuts.ps1")

    assert '[Environment]::GetFolderPath("Desktop")' in script
    assert "Pension Copilot Chatbot" in script
    assert "Pension Copilot Stop" in script
    assert "Pension Copilot Chatbot DEV" in script
    assert "[switch]$IncludeDevelopmentShortcut" in script
    assert "if ($IncludeDevelopmentShortcut)" in script
    assert '-AdditionalArguments " -AllowNonMain"' in script
    assert script.count("AllowNonMain") == 1


def test_dev_launcher_uses_one_origin_and_requires_database_configuration() -> None:
    script = _DEV_SCRIPT.read_text(encoding="utf-8")

    assert 'WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"' in script
    assert 'CHAT_URL = f"{WEB_ORIGIN}/#guide"' in script
    assert "http://localhost" not in script
    assert "DATABASE_URL" in script
    assert "return None" in script
