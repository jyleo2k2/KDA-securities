from __future__ import annotations

import argparse
import copy
import io
from pathlib import Path
from typing import Any

import pytest

from scripts.check_pr_session_policy import (
    GitHubApi,
    branch_name_is_valid,
    hotspot_files,
    missing_body_fields,
    validate_pull_request,
)
from scripts.git_session_manager import (
    SessionError,
    _guard_shell_command,
    _hook_input_from_stdin,
    _local_conflicts,
    command_guard,
    matching_hotspots,
    path_overlaps,
    validate_branch_name,
)

POLICY: dict[str, Any] = {
    "default_branch": "main",
    "minimum_pr_number": 140,
    "grandfathered_pr_numbers": [143],
    "branch_pattern": (
        r"^(front|back|chat|db|engine|rag|integration|codex)/"
        r"[a-z0-9._-]+/[a-z0-9][a-z0-9._-]*$"
    ),
    "branch_example": "front/jaehyun/strategy-screen",
    "integration_owner": "jyleo2k2",
    "owner_only_paths": ["AGENTS.md", "CLAUDE.md"],
    "grandfathered_branches": [],
    "overlap_override_label": "hotspot-approved",
    "required_pr_body_fields": ["담당자", "작업 범위", "공유 핫스팟", "계약 변경"],
    "hotspots": ["frontend/src/App.tsx", "frontend/src/api/types.ts"],
}


class FakeApi:
    def __init__(
        self,
        *,
        reused: bool = False,
        overlap: bool = False,
        label_actor: str | None = "jyleo2k2",
        current_files: list[str] | None = None,
    ):
        self.reused = reused
        self.overlap = overlap
        self.label_actor = label_actor
        self.current_files = current_files or [
            "frontend/src/App.tsx",
            "frontend/src/pages/NewPage.tsx",
        ]

    def closed_pulls_for_branch(self, owner: str, branch: str) -> list[dict[str, Any]]:
        assert owner == "jyleo2k2"
        assert branch == "front/jaehyun/strategy-screen"
        return [{"number": 120}] if self.reused else []

    def pull_files(self, number: int) -> list[str]:
        if number == 140:
            return self.current_files
        if number == 141 and self.overlap:
            return ["frontend/src/App.tsx"]
        return []

    def open_pulls(self) -> list[dict[str, Any]]:
        return [{"number": 140}, {"number": 141}]

    def label_was_applied_by(self, number: int, label: str, owner: str) -> bool:
        assert number == 140
        assert label == "hotspot-approved"
        return self.label_actor == owner


def event(*, labels: list[str] | None = None, number: int = 140) -> dict[str, Any]:
    return {
        "pull_request": {
            "number": number,
            "body": (
                "- 담당자: 진재현\n"
                "- 작업 범위: frontend/src/pages/StrategyExploreScreen.tsx\n"
                "- 공유 핫스팟: frontend/src/App.tsx\n"
                "- 계약 변경: 없음\n"
            ),
            "head": {
                "ref": "front/jaehyun/strategy-screen",
                "repo": {"owner": {"login": "jyleo2k2"}},
            },
            "base": {"ref": "main"},
            "user": {"login": "jaehyun"},
            "labels": [{"name": label} for label in labels or []],
        }
    }


def test_branch_policy_requires_area_owner_and_unique_task() -> None:
    assert branch_name_is_valid("front/jaehyun/strategy-screen", POLICY)
    assert not branch_name_is_valid("front/login-flow", POLICY)
    assert not branch_name_is_valid("챗봇브랜치", POLICY)
    validate_branch_name("chat/hoyeon/etf-theme", POLICY)
    with pytest.raises(SessionError):
        validate_branch_name("chat/etf-theme", POLICY)


def test_path_overlap_and_hotspot_matching() -> None:
    assert path_overlaps("frontend/src", "frontend/src/App.tsx")
    assert not path_overlaps("frontend/src", "backend/app")
    assert matching_hotspots(["frontend/src"], POLICY) == {
        "frontend/src/App.tsx",
        "frontend/src/api/types.ts",
    }
    assert hotspot_files(
        ["frontend/src/App.tsx", "frontend/src/pages/NewPage.tsx"],
        POLICY["hotspots"],
    ) == {"frontend/src/App.tsx"}


def test_pr_body_requires_non_placeholder_values() -> None:
    assert (
        missing_body_fields(
            event()["pull_request"]["body"], POLICY["required_pr_body_fields"]
        )
        == []
    )
    body = event()["pull_request"]["body"].replace("진재현", "TODO")
    assert missing_body_fields(body, POLICY["required_pr_body_fields"]) == ["담당자"]


def test_pr_policy_blocks_reused_branch_and_unapproved_hotspot_overlap() -> None:
    errors = validate_pull_request(event(), POLICY, FakeApi(reused=True, overlap=True))
    assert any("이미 사용" in error for error in errors)
    assert any("PR #141" in error for error in errors)


def test_hotspot_label_allows_coordinated_overlap() -> None:
    errors = validate_pull_request(
        event(labels=["hotspot-approved"]), POLICY, FakeApi(overlap=True)
    )
    assert errors == []


def test_hotspot_label_requires_authenticated_integration_owner() -> None:
    errors = validate_pull_request(
        event(labels=["hotspot-approved"]),
        POLICY,
        FakeApi(overlap=True, label_actor="someone-else"),
    )
    assert any("직접 적용" in error for error in errors)


def test_owner_only_files_require_integration_owner_as_pr_author() -> None:
    errors = validate_pull_request(
        event(), POLICY, FakeApi(current_files=["AGENTS.md"])
    )
    assert any("총괄 전용" in error for error in errors)


def test_stale_and_starting_claims_still_block_overlap(tmp_path: Path) -> None:
    registry = {
        "sessions": [
            {
                "status": "active",
                "branch": "front/other/stale",
                "owner": "other",
                "worktree": str(tmp_path / "missing"),
                "paths": ["frontend/src/App.tsx"],
            },
            {
                "status": "starting",
                "branch": "chat/other/pending",
                "owner": "other",
                "worktree": str(tmp_path / "pending"),
                "paths": ["backend/app/chat"],
            },
        ]
    }
    assert len(_local_conflicts(registry, ["frontend/src"], "front/me/task")) == 1
    assert len(_local_conflicts(registry, ["backend/app"], "back/me/task")) == 1


def test_hook_input_is_fail_closed_and_supports_notebooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{"))
    with pytest.raises(SessionError, match="JSON"):
        _hook_input_from_stdin()
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO('{"tool_input":{"notebook_path":"analysis/demo.ipynb"}}'),
    )
    assert _hook_input_from_stdin() == ("analysis/demo.ipynb", None)


def test_shell_guard_blocks_direct_writes_and_git_coordination() -> None:
    with pytest.raises(SessionError, match="직접 파일 쓰기"):
        _guard_shell_command("Set-Content -Path AGENTS.md -Value bad")
    with pytest.raises(SessionError, match="Git ref"):
        _guard_shell_command("git worktree remove C:/dev/other")


def test_github_pagination_and_rename_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GitHubApi("owner/repo", "token")
    pages = iter(
        [
            ([{"id": 1}], {"Link": '<https://api.github.test/page2>; rel="next"'}),
            ([{"id": 2}], {}),
        ]
    )
    monkeypatch.setattr(api, "_request", lambda url: next(pages))
    assert api.get_all("/pulls?per_page=100") == [{"id": 1}, {"id": 2}]
    monkeypatch.setattr(api, "pull", lambda number: {"changed_files": 1})
    monkeypatch.setattr(
        api,
        "get_all",
        lambda endpoint: [
            {
                "filename": "frontend/src/AppShell.tsx",
                "previous_filename": "frontend/src/App.tsx",
            }
        ],
    )
    assert api.pull_files(140) == [
        "frontend/src/App.tsx",
        "frontend/src/AppShell.tsx",
    ]


def test_workflow_checks_out_trusted_base() -> None:
    workflow = Path(".github/workflows/session-policy.yml").read_text(encoding="utf-8")
    assert "github.event.pull_request.base.sha" in workflow
    assert "persist-credentials: false" in workflow


def test_old_pull_request_is_grandfathered() -> None:
    old_event = copy.deepcopy(event(number=138))
    old_event["pull_request"]["head"]["ref"] = "front/login-flow"
    old_event["pull_request"]["body"] = ""
    assert validate_pull_request(old_event, POLICY, FakeApi()) == []


def test_current_legacy_pull_request_is_explicitly_grandfathered() -> None:
    legacy = event(number=143)
    legacy["pull_request"]["head"]["ref"] = "front/presentation-account-dashboard"
    legacy["pull_request"]["body"] = ""
    assert validate_pull_request(legacy, POLICY, FakeApi()) == []


def test_pull_request_must_target_main() -> None:
    stacked = event()
    stacked["pull_request"]["base"]["ref"] = "front/another/task"
    errors = validate_pull_request(stacked, POLICY, FakeApi())
    assert any("PR base" in error for error in errors)


def test_edit_guard_blocks_default_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.git_session_manager.repo_root", lambda: tmp_path)
    monkeypatch.setattr("scripts.git_session_manager.load_policy", lambda root: POLICY)
    monkeypatch.setattr(
        "scripts.git_session_manager.current_branch", lambda root: "main"
    )
    args = argparse.Namespace(hook_input=False, file="frontend/src/App.tsx")
    with pytest.raises(SessionError, match="main 관제 워크트리"):
        command_guard(args)
