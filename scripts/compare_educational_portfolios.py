"""Compare educational-portfolio report outputs while ignoring generation time."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    report.pop("generated_at", None)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()

    before = _load(args.before)
    after = _load(args.after)
    identical = before == after
    print(json.dumps({"identical": identical}, ensure_ascii=False))
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
