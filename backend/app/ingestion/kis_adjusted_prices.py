import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import get_settings

from ._retry import retry_with_backoff
from ._secrets import require_secret
from .kis_client import (
    KIS_ADJUSTED_DAILY_PRICE_ENDPOINT,
    KIS_BASE_URL,
    KisApiError,
    KisApiResponse,
    fetch_adjusted_daily_item_prices,
    issue_access_token,
    parse_adjusted_daily_price_payload,
)

DEFAULT_START_DATE = date(2020, 1, 2)
DEFAULT_RAW_ROOT = Path("data/raw/kis")
DEFAULT_CACHE_ROOT = Path("data/cache/kis")
DEFAULT_UNIVERSE_ROOT = Path("data/cache/classification")
MAX_RETRIES = 3


@dataclass(frozen=True, slots=True)
class AdjustedPriceCollectionRecord:
    isu_code: str
    isu_name: str
    status: str
    page_count: int
    observation_count: int
    history_start: str | None
    history_end: str | None
    modified_observation_count: int
    cache_path: str | None
    retrieved_at: str | None
    error: str | None = None


def _latest_universe(root: Path) -> Path:
    candidates = sorted(root.glob("pension_account_eligible_etfs_*.json"))
    if not candidates:
        raise FileNotFoundError(f"no pension ETF universe found under {root}")
    return candidates[-1]


def load_pension_etf_universe(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        raise ValueError("pension ETF universe must contain products")
    normalized = []
    for position, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(f"pension ETF product {position} must be an object")
        code = product.get("isu_code")
        name = product.get("isu_name")
        if not isinstance(code, str) or not code:
            raise ValueError(f"pension ETF product {position} has no code")
        if not isinstance(name, str) or not name:
            raise ValueError(f"pension ETF product {position} has no name")
        normalized.append({"isu_code": code, "isu_name": name})
    if len({product["isu_code"] for product in normalized}) != len(normalized):
        raise ValueError("pension ETF universe contains duplicate codes")
    return sorted(normalized, key=lambda product: product["isu_code"])


def _raw_path(root: Path, code: str, requested_end: date) -> Path:
    return (
        root
        / "adjusted_daily_itemchartprice"
        / code
        / f"{requested_end:%Y%m%d}.json"
    )


def _product_cache_path(root: Path, as_of: date, code: str) -> Path:
    return root / "adjusted_prices" / as_of.isoformat() / f"{code}.json"


def _load_raw(path: Path) -> KisApiResponse:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KisApiError(f"cached KIS adjusted price is invalid: {path}") from exc
    return parse_adjusted_daily_price_payload(payload, raw_content=raw)


def _write_raw(path: Path, response: KisApiResponse) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(response.raw_content)
    temporary.replace(path)
    return hashlib.sha256(response.raw_content).hexdigest()


def _fetch_with_retry(fetch: Any) -> KisApiResponse:
    return retry_with_backoff(
        fetch,
        exceptions=KisApiError,
        is_retryable=lambda exc: exc.retryable,
        max_retries=MAX_RETRIES,
    )


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "date": date.fromisoformat(
            f"{row['stck_bsop_date'][:4]}-{row['stck_bsop_date'][4:6]}-"
            f"{row['stck_bsop_date'][6:8]}"
        ).isoformat(),
        "adjusted_close": row["stck_clpr"],
        "adjusted_open": row["stck_oprc"],
        "adjusted_high": row["stck_hgpr"],
        "adjusted_low": row["stck_lwpr"],
        "volume": row["acml_vol"],
        "trading_value_krw": row["acml_tr_pbmn"],
        "modified": row["mod_yn"],
        "split_rate": row["prtt_rate"],
        "revaluation_reason": row["revl_issu_reas"],
    }


def _write_product_cache(
    *,
    cache_root: Path,
    as_of: date,
    product: dict[str, str],
    start_date: date,
    observations: list[dict[str, str]],
    page_evidence: list[dict[str, Any]],
) -> Path:
    path = _product_cache_path(cache_root, as_of, product["isu_code"])
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        **product,
        "source": "Korea Investment & Securities Open Trading API",
        "endpoint": KIS_ADJUSTED_DAILY_PRICE_ENDPOINT,
        "requested_from": start_date.isoformat(),
        "requested_to": as_of.isoformat(),
        "price_policy": {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
            "meaning": "adjusted_price",
        },
        "return_basis": "adjusted_close_price_not_total_return",
        "observation_count": len(observations),
        "history_start": observations[0]["date"] if observations else None,
        "history_end": observations[-1]["date"] if observations else None,
        "modified_observation_count": sum(
            row["modified"] == "Y" for row in observations
        ),
        "page_evidence": page_evidence,
        "limitations": [
            "Adjusted prices must not be assumed to include cash distributions.",
            "KIND distribution events remain the total-return cash-flow source.",
            "KRX remains the exchange-level listing and raw-market audit source.",
        ],
        "observations": observations,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _collect_product(
    *,
    client: httpx.Client,
    app_key: str,
    app_secret: str,
    access_token: str,
    product: dict[str, str],
    start_date: date,
    end_date: date,
    raw_root: Path,
    cache_root: Path,
    delay_seconds: float,
    force: bool,
) -> AdjustedPriceCollectionRecord:
    requested_end = end_date
    observations_by_date: dict[str, dict[str, str]] = {}
    page_evidence = []
    fetched_any = False
    while requested_end >= start_date:
        path = _raw_path(raw_root, product["isu_code"], requested_end)
        if path.exists() and not force:
            response = _load_raw(path)
            page_status = "skipped_existing"
            digest = hashlib.sha256(response.raw_content).hexdigest()
        else:
            response = _fetch_with_retry(
                lambda page_end=requested_end: fetch_adjusted_daily_item_prices(
                    client,
                    app_key=app_key,
                    app_secret=app_secret,
                    access_token=access_token,
                    isu_code=product["isu_code"],
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=page_end.strftime("%Y%m%d"),
                )
            )
            digest = _write_raw(path, response)
            page_status = "fetched"
            fetched_any = True
            if delay_seconds:
                time.sleep(delay_seconds)
        rows = response.payload["output2"]
        page_evidence.append(
            {
                "requested_end": requested_end.isoformat(),
                "row_count": len(rows),
                "status": page_status,
                "sha256": digest,
                "raw_path": path.as_posix(),
            }
        )
        if not rows:
            break
        for row in rows:
            business_date = datetime.strptime(
                row["stck_bsop_date"], "%Y%m%d"
            ).date()
            if start_date <= business_date <= end_date:
                normalized = _normalize_row(row)
                observations_by_date[normalized["date"]] = normalized
        oldest_date = datetime.strptime(
            rows[-1]["stck_bsop_date"], "%Y%m%d"
        ).date()
        if oldest_date <= start_date or len(rows) < 100:
            break
        next_end = oldest_date - timedelta(days=1)
        if next_end >= requested_end:
            raise KisApiError("KIS adjusted price pagination did not advance")
        requested_end = next_end

    observations = sorted(
        observations_by_date.values(), key=lambda row: row["date"]
    )
    cache_path = _write_product_cache(
        cache_root=cache_root,
        as_of=end_date,
        product=product,
        start_date=start_date,
        observations=observations,
        page_evidence=page_evidence,
    )
    return AdjustedPriceCollectionRecord(
        isu_code=product["isu_code"],
        isu_name=product["isu_name"],
        status="fetched" if fetched_any else "skipped_existing",
        page_count=len(page_evidence),
        observation_count=len(observations),
        history_start=observations[0]["date"] if observations else None,
        history_end=observations[-1]["date"] if observations else None,
        modified_observation_count=sum(
            row["modified"] == "Y" for row in observations
        ),
        cache_path=cache_path.as_posix(),
        retrieved_at=datetime.now(UTC).isoformat() if fetched_any else None,
    )


def collect_kis_adjusted_prices(
    *,
    app_key: str,
    app_secret: str,
    universe_path: Path,
    start_date: date,
    end_date: date,
    raw_root: Path,
    cache_root: Path,
    delay_seconds: float,
    workers: int,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("from-date must not be after to-date")
    if delay_seconds < 0:
        raise ValueError("delay-seconds must not be negative")
    if workers < 1 or workers > 8:
        raise ValueError("workers must be between 1 and 8")
    products = load_pension_etf_universe(universe_path)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        products = products[:limit]
    records: list[AdjustedPriceCollectionRecord] = []
    with httpx.Client(
        base_url=KIS_BASE_URL,
        timeout=httpx.Timeout(30.0),
        headers={
            "Accept": "application/json",
            "User-Agent": "pension-copilot-kis-adjusted-price/0.1",
        },
    ) as client:
        token = issue_access_token(client, app_key=app_key, app_secret=app_secret)
        def collect_one(product: dict[str, str]) -> AdjustedPriceCollectionRecord:
            try:
                return _collect_product(
                    client=client,
                    app_key=app_key,
                    app_secret=app_secret,
                    access_token=token.value,
                    product=product,
                    start_date=start_date,
                    end_date=end_date,
                    raw_root=raw_root,
                    cache_root=cache_root,
                    delay_seconds=delay_seconds,
                    force=force,
                )
            except (KisApiError, OSError, ValueError) as exc:
                return AdjustedPriceCollectionRecord(
                    isu_code=product["isu_code"],
                    isu_name=product["isu_name"],
                    status="failed",
                    page_count=0,
                    observation_count=0,
                    history_start=None,
                    history_end=None,
                    modified_observation_count=0,
                    cache_path=None,
                    retrieved_at=datetime.now(UTC).isoformat(),
                    error=str(exc),
                )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(collect_one, product): product
                for product in products
            }
            for position, future in enumerate(as_completed(futures), start=1):
                product = futures[future]
                records.append(future.result())
                if position % 10 == 0 or position == len(products):
                    print(
                        json.dumps(
                            {
                                "completed": position,
                                "product_total": len(products),
                                "last_code": product["isu_code"],
                                "failed": sum(
                                    item.status == "failed" for item in records
                                ),
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )

    generated_at = datetime.now(UTC).isoformat()
    manifest_root = raw_root / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / (
        f"adjusted_prices_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    manifest = {
        "source": "Korea Investment & Securities Open Trading API",
        "endpoint": KIS_ADJUSTED_DAILY_PRICE_ENDPOINT,
        "universe_path": universe_path.as_posix(),
        "requested_from": start_date.isoformat(),
        "requested_to": end_date.isoformat(),
        "generated_at": generated_at,
        "price_policy": {"FID_ORG_ADJ_PRC": "0", "meaning": "adjusted_price"},
        "requested_product_count": len(products),
        "completed_product_count": sum(
            item.status != "failed" for item in records
        ),
        "failed_product_count": sum(item.status == "failed" for item in records),
        "total_observation_count": sum(
            item.observation_count for item in records
        ),
        "modified_observation_count": sum(
            item.modified_observation_count for item in records
        ),
        "records": [asdict(item) for item in records],
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)

    cache_root.mkdir(parents=True, exist_ok=True)
    master_path = cache_root / f"adjusted_price_master_{end_date}.json"
    master = {
        **{key: value for key, value in manifest.items() if key != "records"},
        "manifest_path": manifest_path.as_posix(),
        "return_basis": "adjusted_close_price_not_total_return",
        "products": [asdict(item) for item in records if item.status != "failed"],
    }
    temporary_master = master_path.with_suffix(".json.tmp")
    temporary_master.write_text(
        json.dumps(master, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_master.replace(master_path)
    return {
        **{key: value for key, value in manifest.items() if key != "records"},
        "manifest_path": manifest_path.as_posix(),
        "master_path": master_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect KIS adjusted daily prices for pension-eligible ETFs."
    )
    parser.add_argument("--universe", type=Path)
    parser.add_argument(
        "--from-date", type=date.fromisoformat, default=DEFAULT_START_DATE
    )
    parser.add_argument(
        "--to-date", type=date.fromisoformat, default=date.today() - timedelta(days=1)
    )
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache-output", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--delay-seconds", type=float, default=0.12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    app_key = require_secret(settings.kis_app_key, "KIS_APP_KEY and KIS_APP_SECRET")
    app_secret = require_secret(
        settings.kis_app_secret, "KIS_APP_KEY and KIS_APP_SECRET"
    )
    result = collect_kis_adjusted_prices(
        app_key=app_key,
        app_secret=app_secret,
        universe_path=args.universe or _latest_universe(DEFAULT_UNIVERSE_ROOT),
        start_date=args.from_date,
        end_date=args.to_date,
        raw_root=args.raw_output,
        cache_root=args.cache_output,
        delay_seconds=args.delay_seconds,
        workers=args.workers,
        limit=args.limit,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result["failed_product_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
