from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

import pytest

from scripts.git_session_manager import (
    LOCAL_SESSION_RULES,
    BranchIdentity,
    SessionError,
    _ensure_claim_identity,
    build_parser,
    command_check_start,
    command_guard,
    command_release,
    parse_branch_identity,
    validate_session_identity,
)


def test_new_branch_policy_accepts_only_tool_worker_task() -> None:
    assert LOCAL_SESSION_RULES["allowed_tools"] == ["codex", "claude"]
    assert LOCAL_SESSION_RULES["allowed_workers"] == [
        "이재용",
        "이호연",
        "최호택",
        "진재현",
        "김태형",
        "정인성",
    ]
    assert parse_branch_identity(
        "codex/이재용/pr-173-conflict", LOCAL_SESSION_RULES
    ) == BranchIdentity("codex", "이재용", "pr-173-conflict")
    assert parse_branch_identity(
        "claude/정인성/pension_ui.v2", LOCAL_SESSION_RULES
    ) == BranchIdentity("claude", "정인성", "pension_ui.v2")

    invalid = [
        "front/이재용/task",
        "codex/이태호/task",
        "codex/이재용/Task",
        "codex/이재용/~task",
        "codex/이재용/task/name",
        "codex/이재용/-task",
    ]
    for branch in invalid:
        with pytest.raises(SessionError):
            parse_branch_identity(branch, LOCAL_SESSION_RULES)


def test_branch_and_requested_session_identity_must_match() -> None:
    assert validate_session_identity(
        "codex/김태형/risk-policy",
        tool="codex",
        worker="김태형",
        task="risk-policy",
        policy=LOCAL_SESSION_RULES,
    ) == BranchIdentity("codex", "김태형", "risk-policy")

    with pytest.raises(SessionError, match="세션 등록 정보"):
        validate_session_identity(
            "codex/김태형/risk-policy",
            tool="claude",
            worker="김태형",
            task="risk-policy",
            policy=LOCAL_SESSION_RULES,
        )
    with pytest.raises(SessionError, match="세션 등록 정보"):
        validate_session_identity(
            "codex/김태형/risk-policy",
            tool="codex",
            worker="이재용",
            task="risk-policy",
            policy=LOCAL_SESSION_RULES,
        )


def test_registered_claim_identity_must_match_branch_identity() -> None:
    identity = BranchIdentity("codex", "이재용", "harness-policy")
    _ensure_claim_identity(
        {"tool": "codex", "worker": "이재용", "task": "harness-policy"},
        identity,
    )
    with pytest.raises(SessionError, match="세션 등록 정보"):
        _ensure_claim_identity(
            {"tool": "claude", "worker": "이재용", "task": "harness-policy"},
            identity,
        )
    with pytest.raises(SessionError, match="legacy-registration"):
        _ensure_claim_identity({"owner": "jyleo2k2"}, identity)


def test_edit_guard_blocks_mismatched_registration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.git_session_manager.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch",
        lambda root: "codex/이재용/harness-policy",
    )
    monkeypatch.setattr(
        "scripts.git_session_manager._claim_for_worktree",
        lambda root: {
            "tool": "claude",
            "worker": "이재용",
            "task": "harness-policy",
            "paths": ["scripts"],
        },
    )
    args = argparse.Namespace(hook_input=False, file="scripts/example.py")
    with pytest.raises(SessionError, match="세션 등록 정보"):
        command_guard(args)


def test_session_start_blocks_legacy_and_mismatched_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.git_session_manager.repo_root", lambda: tmp_path)
    monkeypatch.setattr("scripts.git_session_manager._git", lambda *args, **kwargs: "")

    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch",
        lambda root: "front/jyleo2k2/legacy-task",
    )
    with pytest.raises(SessionError, match="새 작업"):
        command_check_start(argparse.Namespace())

    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch",
        lambda root: "codex/이재용/harness-policy",
    )
    monkeypatch.setattr(
        "scripts.git_session_manager._claim_for_worktree",
        lambda root: {
            "tool": "codex",
            "worker": "정인성",
            "task": "harness-policy",
            "paths": ["scripts"],
        },
    )
    with pytest.raises(SessionError, match="세션 등록 정보"):
        command_check_start(argparse.Namespace())


def test_legacy_branch_can_only_be_released(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = {
        "version": 1,
        "sessions": [
            {
                "id": "front--jyleo2k2--legacy-task",
                "owner": "jyleo2k2",
                "branch": "front/jyleo2k2/legacy-task",
                "worktree": str(tmp_path),
                "paths": ["frontend/src"],
                "status": "active",
                "updated_at": "2026-07-22T00:00:00+00:00",
            }
        ],
    }
    saved: dict[str, object] = {}
    monkeypatch.setattr("scripts.git_session_manager.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch",
        lambda root: "front/jyleo2k2/legacy-task",
    )
    monkeypatch.setattr("scripts.git_session_manager._git", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "scripts.git_session_manager._registry_lock",
        lambda root: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        "scripts.git_session_manager._load_registry", lambda root: registry
    )
    monkeypatch.setattr(
        "scripts.git_session_manager._save_registry",
        lambda root, value: saved.update(value),
    )

    assert command_release(argparse.Namespace()) == 0
    sessions = saved["sessions"]
    assert isinstance(sessions, list)
    assert sessions[0]["status"] == "released"


def test_session_start_allows_matching_new_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.git_session_manager.repo_root", lambda: tmp_path)
    monkeypatch.setattr("scripts.git_session_manager._git", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch",
        lambda root: "claude/최호택/pension-ui",
    )
    monkeypatch.setattr(
        "scripts.git_session_manager._claim_for_worktree",
        lambda root: {
            "tool": "claude",
            "worker": "최호택",
            "task": "pension-ui",
            "paths": ["frontend/src"],
        },
    )

    assert command_check_start(argparse.Namespace()) == 0


def test_cli_uses_tool_and_real_name_worker() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "start",
            "--tool",
            "codex",
            "--worker",
            "진재현",
            "--task",
            "pension-ui",
            "--path",
            "frontend/src",
        ]
    )
    assert args.tool == "codex"
    assert args.worker == "진재현"
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "start",
                "--owner",
                "jyleo2k2",
                "--area",
                "front",
                "--task",
                "pension-ui",
                "--path",
                "frontend/src",
            ]
        )


def test_codex_and_claude_skill_mirrors_match() -> None:
    pairs = [
        (
            Path(".agents/skills/git-session-manager/SKILL.md"),
            Path(".claude/skills/git-session-manager/SKILL.md"),
        ),
        (
            Path(
                ".agents/skills/git-session-manager/references/team-git-policy.md"
            ),
            Path(
                ".claude/skills/git-session-manager/references/team-git-policy.md"
            ),
        ),
        (
            Path(".agents/skills/git-session-manager/agents/openai.yaml"),
            Path(".claude/skills/git-session-manager/agents/openai.yaml"),
        ),
    ]
    for codex_path, claude_path in pairs:
        assert codex_path.read_text(encoding="utf-8") == claude_path.read_text(
            encoding="utf-8"
        )


def test_hooks_guard_edits_and_fail_closed_at_session_start() -> None:
    settings = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
    pre_tool = settings["hooks"]["PreToolUse"][0]
    session_start = settings["hooks"]["SessionStart"][0]
    assert pre_tool["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    assert "guard --hook-input" in pre_tool["hooks"][0]["command"]
    assert "check-start" in session_start["hooks"][0]["command"]


def test_entrypoint_documents_share_branch_policy() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    required = [
        "**브랜치 신원:** 신규 브랜치는 `<도구>/<작업자>/<작업명>` 형식이다.",
        "도구·실명 기반 브랜치 신원 검증과 구형 브랜치 편집 차단",
    ]
    for text in required:
        assert text in agents
        assert text in claude
