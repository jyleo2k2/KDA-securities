"""Create and guard isolated Git worktree sessions for parallel development."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REGISTRY_NAME = "codex-sessions.json"
LOCK_NAME = "codex-sessions.lock"
LOCAL_SESSION_RULES: dict[str, Any] = {
    "default_branch": "main",
    "branch_pattern": (
        r"^(front|back|chat|db|engine|rag|integration|codex)/"
        r"[a-z0-9._-]+/[a-z0-9][a-z0-9._-]*$"
    ),
    "branch_example": "front/jaehyun/strategy-screen",
    "integration_owner": "jyleo2k2",
    "owner_only_paths": ["AGENTS.md", "CLAUDE.md"],
    "grandfathered_branches": [
        "front/login-flow",
        "codex/pr-138-conflict-resolution",
        "chat/legacy-mock-account-read-cutover",
        "chat/etf-and-calculator-intents",
    ],
    "hotspots": [],
}


class SessionError(RuntimeError):
    """Raised when a local session guard fails."""


def _run(
    command: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = _run(["git", *args], cwd=cwd, check=check)
    return result.stdout.strip()


def repo_root(cwd: Path | None = None) -> Path:
    return Path(_git("rev-parse", "--show-toplevel", cwd=cwd)).resolve()


def common_git_dir(root: Path) -> Path:
    raw = Path(_git("rev-parse", "--git-common-dir", cwd=root))
    return (root / raw).resolve() if not raw.is_absolute() else raw.resolve()


def local_session_rules() -> dict[str, Any]:
    """Return local worktree rules without a PR-enforcing remote policy file."""
    return LOCAL_SESSION_RULES


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def current_branch(root: Path) -> str:
    branch = _git("branch", "--show-current", cwd=root)
    if not branch:
        raise SessionError("detached HEAD에서는 작업 세션을 등록할 수 없습니다.")
    return branch


def normalize_repo_path(root: Path, value: str) -> str:
    candidate = Path(value)
    absolute = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise SessionError(f"작업 범위가 워크트리 밖입니다: {value}") from exc
    normalized = relative.as_posix().rstrip("/")
    return normalized or "."


def path_overlaps(left: str, right: str) -> bool:
    left = left.strip("/") or "."
    right = right.strip("/") or "."
    if left == "." or right == ".":
        return True
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def scope_contains(scope: str, file_path: str) -> bool:
    if any(character in scope for character in "*?["):
        return fnmatch.fnmatch(file_path, scope)
    return path_overlaps(scope, file_path)


def matching_hotspots(paths: Iterable[str], policy: dict[str, Any]) -> set[str]:
    matches: set[str] = set()
    for path in paths:
        for hotspot in policy.get("hotspots", []):
            if scope_contains(path, hotspot) or fnmatch.fnmatch(path, hotspot):
                matches.add(hotspot)
    return matches


def validate_branch_name(branch: str, policy: dict[str, Any]) -> None:
    if branch in policy.get("grandfathered_branches", []):
        return
    pattern = str(policy["branch_pattern"])
    if not re.fullmatch(pattern, branch):
        example = policy.get("branch_example", "front/owner/task")
        raise SessionError(
            f"브랜치 이름이 세션 규약과 맞지 않습니다: {branch}. 예: {example}"
        )


def _registry_path(root: Path) -> Path:
    return common_git_dir(root) / REGISTRY_NAME


def _load_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.exists():
        return {"version": 1, "sessions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"세션 등록부를 읽을 수 없습니다: {path}: {exc}") from exc
    if not isinstance(data.get("sessions"), list):
        raise SessionError(f"세션 등록부 형식이 잘못됐습니다: {path}")
    return data


@contextlib.contextmanager
def _registry_lock(root: Path, timeout_seconds: float = 10.0):
    lock_path = common_git_dir(root) / LOCK_NAME
    deadline = time.monotonic() + timeout_seconds
    lock_path.touch(exist_ok=True)
    handle = lock_path.open("r+b")
    if lock_path.stat().st_size == 0:
        handle.write(b"\0")
        handle.flush()
    acquired = False
    try:
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise SessionError(
                        f"다른 Git 관제 작업이 진행 중입니다: {lock_path}"
                    ) from None
                time.sleep(0.1)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _save_registry(root: Path, registry: dict[str, Any]) -> None:
    target = _registry_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        json.dump(registry, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, target)


def _claim_is_live(claim: dict[str, Any]) -> bool:
    if claim.get("status") != "active":
        return False
    worktree = Path(str(claim.get("worktree", "")))
    if not worktree.exists():
        return False
    result = _run(
        ["git", "branch", "--show-current"], cwd=worktree, check=False
    )
    return result.returncode == 0 and result.stdout.strip() == claim.get("branch")


def blocking_claims(root: Path) -> list[dict[str, Any]]:
    return [
        claim
        for claim in _load_registry(root)["sessions"]
        if claim.get("status") in {"starting", "active"}
    ]


def _local_conflicts(
    registry: dict[str, Any], scopes: list[str], branch: str
) -> list[str]:
    conflicts: list[str] = []
    for claim in registry["sessions"]:
        if claim.get("status") not in {"starting", "active"}:
            continue
        if claim.get("branch") == branch:
            continue
        collisions = sorted(
            {
                path
                for path in scopes
                for other in claim.get("paths", [])
                if path_overlaps(path, other)
            }
        )
        if collisions:
            conflicts.append(
                f"local {claim['branch']} ({claim['owner']}): {', '.join(collisions)}"
            )
    return conflicts


def _gh_open_prs(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    if shutil.which("gh") is None:
        return [], "gh가 없어 원격 PR 겹침 검사를 생략했습니다. CI에서 다시 검사합니다."
    listed = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,headRefName,url",
        ],
        cwd=root,
        check=False,
    )
    if listed.returncode != 0:
        return [], "열린 PR을 조회하지 못해 로컬 claim만 검사했습니다."
    pulls: list[dict[str, Any]] = json.loads(listed.stdout or "[]")
    enriched: list[dict[str, Any]] = []
    for pull in pulls:
        viewed = _run(
            ["gh", "pr", "view", str(pull["number"]), "--json", "files"],
            cwd=root,
            check=False,
        )
        if viewed.returncode != 0:
            continue
        files = json.loads(viewed.stdout).get("files", [])
        enriched.append({**pull, "files": [item["path"] for item in files]})
    return enriched, None


def find_overlaps(
    root: Path, scopes: list[str], branch: str
) -> tuple[list[str], list[str]]:
    local_conflicts = _local_conflicts(_load_registry(root), scopes, branch)

    remote_conflicts: list[str] = []
    pulls, warning = _gh_open_prs(root)
    if warning:
        print(f"[session] 경고: {warning}", file=sys.stderr)
    for pull in pulls:
        if pull.get("headRefName") == branch:
            continue
        collisions = sorted(
            {
                file_path
                for file_path in pull.get("files", [])
                if any(scope_contains(scope, file_path) for scope in scopes)
            }
        )
        if collisions:
            remote_conflicts.append(
                f"PR #{pull['number']} {pull['headRefName']}: {', '.join(collisions)}"
            )
    return local_conflicts, remote_conflicts


def _register_claim(
    root: Path,
    *,
    worktree: Path,
    branch: str,
    owner: str,
    paths: list[str],
) -> None:
    with _registry_lock(root):
        registry = _load_registry(root)
        conflicts = _local_conflicts(registry, paths, branch)
        if conflicts:
            detail = "\n  - ".join(conflicts)
            raise SessionError(
                "작업 범위가 활성 세션과 겹칩니다. 기존 claim을 조정하거나 "
                "release하세요."
                f"\n  - {detail}"
            )
        for claim in registry["sessions"]:
            if claim.get("status") in {"starting", "active"} and (
                claim.get("branch") == branch
                or Path(str(claim.get("worktree", ""))) == worktree
            ):
                claim.update(
                    owner=owner,
                    paths=paths,
                    status="active",
                    updated_at=utc_now(),
                )
                _save_registry(root, registry)
                return
        registry["sessions"].append(
            {
                "id": branch.replace("/", "--"),
                "owner": owner,
                "branch": branch,
                "worktree": str(worktree),
                "paths": paths,
                "status": "active",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        _save_registry(root, registry)


def _reserve_starting_claim(
    root: Path,
    *,
    worktree: Path,
    branch: str,
    owner: str,
    paths: list[str],
) -> None:
    with _registry_lock(root):
        registry = _load_registry(root)
        conflicts = _local_conflicts(registry, paths, branch)
        if conflicts:
            detail = "\n  - ".join(conflicts)
            raise SessionError(
                "작업 범위가 활성 세션과 겹칩니다. 기존 claim을 조정하거나 "
                "release하세요."
                f"\n  - {detail}"
            )
        duplicate = any(
            item.get("status") in {"starting", "active"}
            and (
                item.get("branch") == branch
                or Path(str(item.get("worktree", ""))) == worktree
            )
            for item in registry["sessions"]
        )
        if duplicate:
            raise SessionError(f"이미 예약된 브랜치 또는 워크트리입니다: {branch}")
        registry["sessions"].append(
            {
                "id": branch.replace("/", "--"),
                "owner": owner,
                "branch": branch,
                "worktree": str(worktree),
                "paths": paths,
                "status": "starting",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        _save_registry(root, registry)


def _cancel_starting_claim(root: Path, branch: str) -> None:
    with _registry_lock(root):
        registry = _load_registry(root)
        registry["sessions"] = [
            item
            for item in registry["sessions"]
            if not (item.get("branch") == branch and item.get("status") == "starting")
        ]
        _save_registry(root, registry)


def _preflight_claim(
    root: Path,
    branch: str,
    scopes: list[str],
    policy: dict[str, Any],
    approved_by: str | None,
) -> None:
    validate_branch_name(branch, policy)
    if approved_by:
        raise SessionError(
            "로컬 --approved-by 자기선언은 허용하지 않습니다. 기존 claim을 "
            "분할·release한 "
            "뒤, 원격 PR 겹침은 integration owner가 GitHub 라벨로 승인해야 합니다."
        )
    local_conflicts, remote_conflicts = find_overlaps(root, scopes, branch)
    conflicts = [*local_conflicts, *remote_conflicts]
    if conflicts:
        detail = "\n  - ".join(conflicts)
        raise SessionError(
            "작업 범위가 활성 세션 또는 PR과 겹칩니다. 범위를 분할하거나 기존 claim을 "
            f"release하십시오.\n  - {detail}"
        )


def command_claim(args: argparse.Namespace) -> int:
    root = repo_root()
    policy = local_session_rules()
    branch = current_branch(root)
    if branch == policy["default_branch"]:
        raise SessionError(
            "main은 관제 전용입니다. 별도 브랜치·워크트리를 사용하십시오."
        )
    scopes = [normalize_repo_path(root, value) for value in args.path]
    _preflight_claim(root, branch, scopes, policy, args.approved_by)
    _register_claim(
        root,
        worktree=root,
        branch=branch,
        owner=args.owner,
        paths=scopes,
    )
    print(f"[session] claimed {branch}: {', '.join(scopes)}")
    return 0


def command_start(args: argparse.Namespace) -> int:
    root = repo_root()
    policy = local_session_rules()
    if current_branch(root) != policy["default_branch"]:
        raise SessionError("start는 깨끗한 main 관제 워크트리에서만 실행하십시오.")
    if _git("status", "--porcelain", cwd=root):
        raise SessionError("main 관제 워크트리가 더티합니다. 먼저 원인을 확인하십시오.")
    branch = args.branch or f"{args.area}/{args.owner}/{args.task}"
    scopes = [normalize_repo_path(root, value) for value in args.path]
    _preflight_claim(root, branch, scopes, policy, args.approved_by)
    _git("fetch", "origin", policy["default_branch"], cwd=root)
    existing = _run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    if existing.returncode == 0:
        raise SessionError(f"로컬 브랜치가 이미 존재합니다: {branch}")
    worktree = (
        Path(args.worktree).resolve()
        if args.worktree
        else root.parent / f"{root.name}-{args.task}"
    )
    if worktree.exists():
        raise SessionError(f"워크트리 경로가 이미 존재합니다: {worktree}")
    _reserve_starting_claim(
        root,
        worktree=worktree,
        branch=branch,
        owner=args.owner,
        paths=scopes,
    )
    try:
        _git(
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree),
            f"origin/{policy['default_branch']}",
            cwd=root,
        )
        _register_claim(
            root,
            worktree=worktree,
            branch=branch,
            owner=args.owner,
            paths=scopes,
        )
    except Exception:
        _cancel_starting_claim(root, branch)
        raise
    print(f"[session] created {branch}\n[session] worktree {worktree}")
    return 0


def _claim_for_worktree(root: Path) -> dict[str, Any] | None:
    resolved = root.resolve()
    branch = current_branch(root)
    return next(
        (
            claim
            for claim in blocking_claims(root)
            if claim.get("status") == "active"
            and Path(str(claim["worktree"])).resolve() == resolved
            and claim.get("branch") == branch
        ),
        None,
    )


def _hook_file_from_stdin() -> str:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        raise SessionError("hook 입력 JSON을 읽지 못했습니다.") from None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise SessionError("hook 입력에 tool_input 객체가 없습니다.")
    raw_file = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
    )
    if raw_file is not None and not isinstance(raw_file, str):
        raise SessionError("hook 파일 경로 형식이 올바르지 않습니다.")
    if not raw_file:
        raise SessionError("hook 입력에서 파일 경로를 찾지 못했습니다.")
    return raw_file


def _changed_paths(root: Path) -> set[str]:
    commands = (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    return {
        path.replace("\\", "/")
        for command in commands
        for path in _git(*command, cwd=root).split("\0")
        if path
    }


def command_guard(args: argparse.Namespace) -> int:
    root = repo_root()
    policy = local_session_rules()
    branch = current_branch(root)
    raw_file = _hook_file_from_stdin() if args.hook_input else args.file
    if branch == policy["default_branch"]:
        raise SessionError("main 관제 워크트리에서는 파일을 수정할 수 없습니다.")
    validate_branch_name(branch, policy)
    claim = _claim_for_worktree(root)
    if claim is None:
        raise SessionError(
            "등록되지 않은 작업 세션입니다. 수정 전에 "
            "git-session-manager claim을 실행하십시오."
        )
    outside = sorted(
        path
        for path in _changed_paths(root)
        if not any(scope_contains(scope, path) for scope in claim["paths"])
    )
    if outside:
        raise SessionError(
            "claim 범위 밖 변경이 감지됐습니다: "
            f"{', '.join(outside)}; 범위={claim['paths']}"
        )
    if raw_file:
        relative = normalize_repo_path(root, raw_file)
        if not any(scope_contains(scope, relative) for scope in claim["paths"]):
            raise SessionError(
                f"claim 범위 밖 파일입니다: {relative}; 범위={claim['paths']}"
            )
        if (
            relative in policy.get("owner_only_paths", [])
            and claim.get("owner") != policy.get("integration_owner")
        ):
            raise SessionError(
                "총괄 전용 파일은 "
                f"{policy.get('integration_owner')} 세션만 수정합니다: "
                f"{relative}"
            )
    last = dt.datetime.fromisoformat(claim["updated_at"])
    if dt.datetime.now(dt.UTC) - last > dt.timedelta(minutes=1):
        with _registry_lock(root):
            registry = _load_registry(root)
            for item in registry["sessions"]:
                if item.get("id") == claim.get("id"):
                    item["updated_at"] = utc_now()
            _save_registry(root, registry)
    return 0


def command_check_start(_: argparse.Namespace) -> int:
    root = repo_root()
    policy = local_session_rules()
    branch = current_branch(root)
    dirty = bool(_git("status", "--porcelain", cwd=root))
    if branch == policy["default_branch"]:
        state = "dirty" if dirty else "clean"
        print(f"[하네스] main 관제 워크트리({state})입니다. 파일 수정은 차단됩니다.")
        return 0
    try:
        validate_branch_name(branch, policy)
    except SessionError as exc:
        print(f"[하네스] 경고: {exc}")
    claim = _claim_for_worktree(root)
    if claim is None:
        print("[하네스] 수정 전에 git-session-manager claim이 필요합니다.")
    else:
        print(
            f"[하네스] active session: {claim['owner']} / {branch} / {claim['paths']}"
        )
    return 0


def command_heartbeat(_: argparse.Namespace) -> int:
    root = repo_root()
    claim = _claim_for_worktree(root)
    if claim is None:
        raise SessionError("현재 워크트리에 활성 claim이 없습니다.")
    with _registry_lock(root):
        registry = _load_registry(root)
        for item in registry["sessions"]:
            if item.get("id") == claim.get("id"):
                item["updated_at"] = utc_now()
        _save_registry(root, registry)
    print(f"[session] heartbeat {claim['branch']}")
    return 0


def command_release(_: argparse.Namespace) -> int:
    root = repo_root()
    branch = current_branch(root)
    if _git("status", "--porcelain", cwd=root):
        raise SessionError("dirty 워크트리는 claim을 release할 수 없습니다.")
    with _registry_lock(root):
        registry = _load_registry(root)
        changed = False
        for item in registry["sessions"]:
            if item.get("branch") == branch and item.get("status") == "active":
                item["status"] = "released"
                item["updated_at"] = utc_now()
                changed = True
        if not changed:
            raise SessionError(f"활성 claim이 없습니다: {branch}")
        _save_registry(root, registry)
    print(f"[session] released {branch}; 병합 후 git-pr-cleanup으로 정리하십시오.")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = repo_root()
    registry = _load_registry(root)
    sessions = [
        {**item, "live": _claim_is_live(item)} for item in registry["sessions"]
    ]
    if args.json:
        print(json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2))
        return 0
    if not sessions:
        print("[session] 등록된 세션이 없습니다.")
        return 0
    for item in sessions:
        print(
            f"[{item['status']}] live={item['live']} owner={item['owner']} "
            f"branch={item['branch']} paths={','.join(item['paths'])} "
            f"updated={item['updated_at']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create an isolated branch/worktree")
    start.add_argument("--owner", required=True)
    start.add_argument("--area", required=True)
    start.add_argument("--task", required=True)
    start.add_argument("--path", action="append", required=True)
    start.add_argument("--branch")
    start.add_argument("--worktree")
    start.add_argument("--approved-by")
    start.set_defaults(func=command_start)

    claim = subparsers.add_parser("claim", help="claim paths in the current worktree")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--path", action="append", required=True)
    claim.add_argument("--approved-by")
    claim.set_defaults(func=command_claim)

    guard = subparsers.add_parser("guard", help="validate the current edit session")
    guard.add_argument("--file")
    guard.add_argument("--hook-input", action="store_true")
    guard.set_defaults(func=command_guard)

    check_start = subparsers.add_parser("check-start")
    check_start.set_defaults(func=command_check_start)
    heartbeat = subparsers.add_parser("heartbeat")
    heartbeat.set_defaults(func=command_heartbeat)
    release = subparsers.add_parser("release")
    release.set_defaults(func=command_release)
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except SessionError as exc:
        print(f"[session] BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
