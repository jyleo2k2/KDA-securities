from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WINDOWS_SCRIPTS = _ROOT / "scripts" / "windows"


def _read(name: str) -> str:
    return (_WINDOWS_SCRIPTS / name).read_text(encoding="utf-8")


def test_start_launcher_is_local_main_only_and_hides_server_windows() -> None:
    script = _read("start-chatbot.ps1")

    assert 'branch -ne "main"' in script
    assert '"--host", "127.0.0.1"' in script
    assert "0.0.0.0" not in script
    assert "WindowStyle Hidden" in script
    assert "DATABASE_URL" in script
    assert 'ChatUrl = "$FrontendUrl/#guide"' in script


def test_stop_launcher_only_uses_recorded_pid_and_start_time() -> None:
    script = _read("stop-chatbot.ps1")

    assert "server-processes.json" in script
    assert "recorded_at" not in script
    assert "started_at" in script
    assert "Stop-ProcessTree" in script
    assert "Get-Process -Id" in script


def test_shortcut_installer_uses_actual_windows_desktop() -> None:
    script = _read("install-chatbot-shortcuts.ps1")

    assert '[Environment]::GetFolderPath("Desktop")' in script
    assert "Pension Copilot Chatbot" in script
    assert "Pension Copilot Stop" in script
    assert "AllowNonMain" not in script
