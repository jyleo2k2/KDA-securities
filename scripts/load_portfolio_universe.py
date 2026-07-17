"""ETF 포트폴리오 유니버스 캐시를 Supabase로 적재한다(아키텍처.md §10).

전제: `data/cache/returns`·`data/cache/kis/adjusted_prices`·`data/cache/events`에
계좌 3종(dc·irp·pension_savings) 최신 cost-return 마스터가 이미 있어야 한다
(`backend/app/etf_cost_return_report.py` 산출물). 이 스크립트는 값을 재계산하지
않고 그대로 옮긴다.

실행:

    uv run python scripts/load_portfolio_universe.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.etf_universe_database import (
    PortfolioUniverseLoadError,
    load_portfolio_universe,
)
from backend.app.settings import get_settings


def main() -> int:
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        print("DATABASE_URL이 비어 있습니다 (.env 확인)", file=sys.stderr)
        return 1

    try:
        summary = load_portfolio_universe(database_url)
    except (FileNotFoundError, PortfolioUniverseLoadError) as exc:
        print(f"적재 실패: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "as_of": summary.as_of.isoformat(),
                "version_id": summary.version_id,
                "product_rows": summary.product_rows,
                "history_rows": summary.history_rows,
                "account_product_counts": summary.account_product_counts,
                "source_sha256": summary.source_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
