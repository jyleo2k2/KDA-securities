import argparse
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import Settings

from ._files import atomic_write_bytes, atomic_write_json, sha256_hex
from ._retry import retry_with_backoff
from ._secrets import require_secret
from .kis_adjusted_prices import load_pension_etf_universe
from .kis_client import (
    KIS_BASE_URL,
    KIS_KSD_DIVIDEND_ENDPOINT,
    KisApiError,
    fetch_ksd_dividend_schedule,
    issue_access_token,
    parse_ksd_dividend_payload,
)

MAX_RETRIES = 3


def _iso_date(value: str) -> str | None:
    value = value.strip()
    if value in {"", "00000000"}:
        return None
    return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}").isoformat()


def _raw_path(root: Path, start_date: date, end_date: date, code: str) -> Path:
    return root / f"{start_date:%Y%m%d}_{end_date:%Y%m%d}" / f"{code}.json"


def _fetch_with_retry(fetch: Any):
    return retry_with_backoff(
        fetch,
        exceptions=KisApiError,
        is_retryable=lambda error: error.retryable,
        max_retries=MAX_RETRIES,
    )


def collect_kis_dividend_schedules(
    *,
    app_key: str,
    app_secret: str,
    universe_path: Path,
    start_date: date,
    end_date: date,
    raw_root: Path,
    output_root: Path,
    delay_seconds: float = 0.12,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("from-date must not be after to-date")
    products = load_pension_etf_universe(universe_path)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        products = products[:limit]

    events = []
    evidence = []
    failures = []
    with httpx.Client(
        base_url=KIS_BASE_URL,
        timeout=httpx.Timeout(30.0),
        headers={
            "Accept": "application/json",
            "User-Agent": "pension-copilot-kis-dividend/0.1",
        },
    ) as client:
        token = issue_access_token(client, app_key=app_key, app_secret=app_secret)
        for product in products:
            path = _raw_path(raw_root, start_date, end_date, product["isu_code"])
            try:
                if path.exists() and not force:
                    raw_content = path.read_bytes()
                    response = parse_ksd_dividend_payload(
                        json.loads(raw_content), raw_content=raw_content
                    )
                    status = "skipped_existing"
                else:
                    isu_code = product["isu_code"]
                    response = _fetch_with_retry(
                        lambda isu_code=isu_code: fetch_ksd_dividend_schedule(
                            client,
                            app_key=app_key,
                            app_secret=app_secret,
                            access_token=token.value,
                            start_date=start_date.strftime("%Y%m%d"),
                            end_date=end_date.strftime("%Y%m%d"),
                            isu_code=isu_code,
                        )
                    )
                    atomic_write_bytes(path, response.raw_content)
                    status = "fetched"
                    if delay_seconds:
                        time.sleep(delay_seconds)
                rows = response.payload.get("output1", [])
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows:
                    events.append(
                        {
                            "isu_code": row["sht_cd"],
                            "isu_name": product["isu_name"],
                            "record_date": _iso_date(row["record_date"]),
                            "payment_date": _iso_date(row["divi_pay_dt"]),
                            "cash_per_share_krw": row["per_sto_divi_amt"],
                            "dividend_kind": row["divi_kind"],
                        }
                    )
                evidence.append(
                    {
                        "isu_code": product["isu_code"],
                        "status": status,
                        "row_count": len(rows),
                        "raw_path": path.as_posix(),
                        "sha256": sha256_hex(response.raw_content),
                    }
                )
            except (KisApiError, OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append({"isu_code": product["isu_code"], "error": str(exc)})

    report = {
        "report_type": "kis_ksd_dividend_schedule",
        "source": "Korea Investment & Securities Open Trading API",
        "endpoint": KIS_KSD_DIVIDEND_ENDPOINT,
        "requested_from": start_date.isoformat(),
        "requested_to": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "universe_path": universe_path.as_posix(),
        "requested_product_count": len(products),
        "successful_product_count": len(evidence),
        "failure_count": len(failures),
        "event_count": len(events),
        "evidence": evidence,
        "failures": failures,
        "events": sorted(
            events,
            key=lambda event: (event["record_date"], event["isu_code"]),
        ),
    }
    output_path = output_root / (
        f"ksd_dividend_schedule_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    atomic_write_json(output_path, report)
    report["output_path"] = output_path.as_posix()
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect KIS KSD dividend schedules.")
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--raw-output", type=Path, default=Path("data/raw/kis/ksd_dividend")
    )
    parser.add_argument("--output", type=Path, default=Path("data/cache/kis"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--delay-seconds", type=float, default=0.12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings(_env_file=args.env_file)
    result = collect_kis_dividend_schedules(
        app_key=require_secret(settings.kis_app_key, "KIS_APP_KEY and KIS_APP_SECRET"),
        app_secret=require_secret(
            settings.kis_app_secret, "KIS_APP_KEY and KIS_APP_SECRET"
        ),
        universe_path=args.universe,
        start_date=args.from_date,
        end_date=args.to_date,
        raw_root=args.raw_output,
        output_root=args.output,
        delay_seconds=args.delay_seconds,
        limit=args.limit,
        force=args.force,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "events"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if result["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
