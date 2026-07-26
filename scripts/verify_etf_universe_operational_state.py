"""Verify that the promoted ETF universe is complete without copying price files.

The PostgreSQL ETF dataset is the durable serving store for the large
total-return history.  The compact private Storage cache is verified
separately; this command verifies the corresponding promoted database rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.etf_universe_database import (
    PortfolioUniverseLoadError,
    audit_latest_portfolio_universe,
)
from backend.app.settings import Settings


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def main() -> int:
    settings = Settings()
    database_url = _secret_value(settings.database_url)
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1
    try:
        audit = audit_latest_portfolio_universe(database_url)
    except (PortfolioUniverseLoadError, ValueError) as error:
        print(f"ETF universe database audit failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(audit.as_json(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
