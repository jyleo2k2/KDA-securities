"""Validate pull requests against the repository's parallel-session policy."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def branch_name_is_valid(branch: str, policy: dict[str, Any]) -> bool:
    if branch in policy.get("grandfathered_branches", []):
        return True
    return re.fullmatch(str(policy["branch_pattern"]), branch) is not None


def missing_body_fields(body: str, fields: list[str]) -> list[str]:
    missing: list[str] = []
    for field in fields:
        match = re.search(rf"(?mi)^\s*[-*]?\s*{re.escape(field)}\s*:\s*(.+?)\s*$", body)
        if not match or match.group(1).strip().lower() in {"", "todo", "tbd", "미정"}:
            missing.append(field)
    return missing


def hotspot_files(files: list[str], patterns: list[str]) -> set[str]:
    return {
        file_path
        for file_path in files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in patterns)
    }


class GitHubApi:
    def __init__(self, repository: str, token: str):
        self.repository = repository
        self.token = token
        self._pull_cache: dict[int, dict[str, Any]] = {}

    def _request(self, url: str) -> tuple[Any, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pension-copilot-session-policy",
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response), response.headers
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise
                if attempt == 2:
                    raise
            except urllib.error.URLError:
                if attempt == 2:
                    raise
            time.sleep(min(2**attempt, 4))
        raise RuntimeError("GitHub API 재시도 한도를 초과했습니다.")

    def get(self, endpoint: str) -> Any:
        result, _ = self._request(
            f"https://api.github.com/repos/{self.repository}{endpoint}"
        )
        return result

    def get_all(self, endpoint: str) -> list[dict[str, Any]]:
        url: str | None = f"https://api.github.com/repos/{self.repository}{endpoint}"
        items: list[dict[str, Any]] = []
        while url:
            result, headers = self._request(url)
            if not isinstance(result, list):
                raise RuntimeError(
                    f"페이지 API가 목록을 반환하지 않았습니다: {endpoint}"
                )
            items.extend(result)
            link = headers.get("Link", "")
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return items

    def pull(self, number: int) -> dict[str, Any]:
        if number not in self._pull_cache:
            self._pull_cache[number] = self.get(f"/pulls/{number}")
        return self._pull_cache[number]

    def pull_files(self, number: int) -> list[str]:
        pull = self.pull(number)
        if int(pull.get("changed_files", 0)) > 3000:
            raise RuntimeError(
                f"PR #{number}은 변경 파일이 3,000개를 넘어 수동 검토가 필요합니다."
            )
        result = self.get_all(f"/pulls/{number}/files?per_page=100")
        paths = {
            path
            for item in result
            for path in (item.get("filename"), item.get("previous_filename"))
            if path
        }
        return sorted(paths)

    def open_pulls(self) -> list[dict[str, Any]]:
        return self.get_all("/pulls?state=open&per_page=100")

    def closed_pulls_for_branch(self, owner: str, branch: str) -> list[dict[str, Any]]:
        head = urllib.parse.quote(f"{owner}:{branch}")
        return self.get_all(f"/pulls?state=closed&head={head}&per_page=100")

    def label_was_applied_by(self, number: int, label: str, owner: str) -> bool:
        events = self.get_all(f"/issues/{number}/events?per_page=100")
        matching = [
            item
            for item in events
            if item.get("event") in {"labeled", "unlabeled"}
            and (item.get("label") or {}).get("name") == label
        ]
        if not matching:
            return False
        latest = matching[-1]
        return (
            latest.get("event") == "labeled"
            and (latest.get("actor") or {}).get("login") == owner
        )


def validate_pull_request(
    event: dict[str, Any], policy: dict[str, Any], api: GitHubApi
) -> list[str]:
    pull = event["pull_request"]
    number = int(pull["number"])
    if number < int(policy.get("minimum_pr_number", 0)) or number in set(
        policy.get("grandfathered_pr_numbers", [])
    ):
        print(f"[session-policy] PR #{number} is grandfathered.")
        return []

    errors: list[str] = []
    base = pull["base"]["ref"]
    if base != policy["default_branch"]:
        errors.append(
            f"PR base는 {policy['default_branch']}이어야 합니다: 현재 {base}"
        )
    branch = pull["head"]["ref"]
    if not branch_name_is_valid(branch, policy):
        errors.append(
            f"브랜치 이름 '{branch}'이 규약과 맞지 않습니다. "
            f"예: {policy['branch_example']}"
        )

    body = pull.get("body") or ""
    missing = missing_body_fields(body, list(policy["required_pr_body_fields"]))
    if missing:
        errors.append(f"PR 본문 필수 필드가 비었습니다: {', '.join(missing)}")

    owner = pull["head"]["repo"]["owner"]["login"]
    reused = [
        item
        for item in api.closed_pulls_for_branch(owner, branch)
        if int(item["number"]) != number
    ]
    if reused:
        old_numbers = ", ".join(f"#{item['number']}" for item in reused)
        errors.append(
            f"브랜치 '{branch}'은 이전 PR {old_numbers}에서 이미 사용됐습니다. "
            "후속 작업은 새 브랜치로 시작하십시오."
        )

    current_files = api.pull_files(number)
    protected = set(policy.get("owner_only_paths", [])) & set(current_files)
    author = (pull.get("user") or {}).get("login")
    integration_owner = str(policy["integration_owner"])
    if protected and author != integration_owner:
        errors.append(
            f"총괄 전용 파일은 {integration_owner}의 PR에서만 변경할 수 있습니다: "
            f"{', '.join(sorted(protected))}"
        )
    current_hotspots = hotspot_files(current_files, list(policy["hotspots"]))
    labels = {item["name"] for item in pull.get("labels", [])}
    override = str(policy["overlap_override_label"])
    overlaps: list[tuple[int, set[str]]] = []
    if current_hotspots:
        for other in api.open_pulls():
            other_number = int(other["number"])
            if other_number == number:
                continue
            overlap = current_hotspots & set(api.pull_files(other_number))
            if overlap:
                overlaps.append((other_number, overlap))
    if overlaps:
        if override not in labels:
            for other_number, overlap in overlaps:
                errors.append(
                    f"PR #{other_number}와 공유 핫스팟이 겹칩니다: "
                    f"{', '.join(sorted(overlap))}. 이재용 조율 후 '{override}' "
                    "라벨을 추가하십시오."
                )
        elif not api.label_was_applied_by(number, override, integration_owner):
            errors.append(
                f"'{override}' 라벨은 {integration_owner}가 직접 적용한 "
                "기록이 있어야 합니다."
            )
    return errors


def main() -> int:
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN이 없어 세션 정책을 검사할 수 없습니다.", file=sys.stderr)
        return 2
    event = load_json(event_path)
    policy = load_json(Path(".github/session-policy.json"))
    api = GitHubApi(repository, token)
    number = int(event["pull_request"]["number"])
    event["pull_request"] = api.pull(number)
    errors = validate_pull_request(event, policy, api)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("[session-policy] branch, ownership, reuse, and hotspot checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
