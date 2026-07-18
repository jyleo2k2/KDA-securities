import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import get_settings

from ._dates import weekdays
from ._retry import async_retry_with_backoff
from ._secrets import require_secret
from .krx_client import (
    KRX_INDEX_ENDPOINTS,
    KrxApiError,
    KrxIndexDailyResponse,
    fetch_krx_index_daily_async,
    parse_krx_index_payload,
)

DEFAULT_START_DATE = date(2020, 1, 2)
DEFAULT_WORKERS = 8
MAX_RETRIES = 3
INDEX_SERIES = ("krx", "kospi", "kosdaq", "bond")
BENCHMARKS = {
    "krx": {"KRX 300": "domestic_equity_broad"},
    "kospi": {
        "코스피": "domestic_equity_broad",
        "코스피 200": "domestic_large_cap",
    },
    "kosdaq": {
        "코스닥": "domestic_growth_equity",
        "코스닥 150": "domestic_growth_large_cap",
    },
    "bond": {
        "KRX 채권지수": "domestic_bond_broad",
        "KTB 지수": "domestic_government_bond",
        "국고채프라임지수": "domestic_government_bond_prime",
    },
}


@dataclass(frozen=True, slots=True)
class IndexCollectionRecord:
    series: str
    base_date: str
    status: str
    row_count: int
    usable_row_count: int
    sha256: str | None
    relative_path: str | None
    retrieved_at: str | None
    error: str | None = None


def _raw_path(root: Path, series: str, base_date: date) -> Path:
    return (
        root
        / "indices"
        / series
        / f"{base_date.year:04d}"
        / f"{base_date.month:02d}"
        / f"{base_date:%Y%m%d}.json"
    )


def _load_existing(
    path: Path, *, series: str, base_date: date
) -> KrxIndexDailyResponse:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KrxApiError(f"existing KRX index file is invalid JSON: {path}") from exc
    return parse_krx_index_payload(
        payload,
        series=series,
        base_date=base_date,
        raw_content=raw,
    )


def _usable_row_count(response: KrxIndexDailyResponse) -> int:
    value_field = "TOT_EARNG_IDX" if response.series == "bond" else "CLSPRC_IDX"
    return sum(row[value_field] not in {"", "-"} for row in response.records)


def _persist_raw(path: Path, response: KrxIndexDailyResponse) -> IndexCollectionRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(response.raw_content)
    temporary.replace(path)
    return IndexCollectionRecord(
        series=response.series,
        base_date=response.base_date.isoformat(),
        status="fetched",
        row_count=len(response.records),
        usable_row_count=_usable_row_count(response),
        sha256=hashlib.sha256(response.raw_content).hexdigest(),
        relative_path=path.as_posix(),
        retrieved_at=datetime.now(UTC).isoformat(),
    )


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    series: str,
    base_date: date,
) -> KrxIndexDailyResponse:
    return await async_retry_with_backoff(
        lambda: fetch_krx_index_daily_async(
            client, api_key=api_key, series=series, base_date=base_date
        ),
        exceptions=KrxApiError,
        is_retryable=lambda exc: exc.status_code is None
        or exc.status_code == 429
        or exc.status_code >= 500,
        max_retries=MAX_RETRIES,
    )


def _benchmark_name(series: str, row: dict[str, str]) -> str:
    return row["BND_IDX_GRP_NM"] if series == "bond" else row["IDX_NM"]


def _normalize_observation(
    series: str, base_date: date, row: dict[str, str]
) -> dict[str, str]:
    if series == "bond":
        return {
            "date": base_date.isoformat(),
            "total_return_index": row["TOT_EARNG_IDX"],
            "net_price_index": row["NETPRC_IDX"],
            "market_price_index": row["MKT_PRC_IDX"],
            "average_yield_percent": row["BND_IDX_AVG_YD"],
            "average_duration": row["AVG_DURATION"],
            "average_convexity": row["AVG_CONVEXITY_PRC"],
        }
    return {
        "date": base_date.isoformat(),
        "close_index": row["CLSPRC_IDX"],
        "trading_volume": row["ACC_TRDVOL"],
        "trading_value_krw": row["ACC_TRDVAL"],
        "market_cap_krw": row["MKTCAP"],
    }


def build_benchmark_history(
    *,
    start_date: date,
    end_date: date,
    raw_root: Path,
    cache_root: Path,
) -> dict[str, Any]:
    observations: dict[tuple[str, str], list[dict[str, str]]] = {
        (series, name): []
        for series, names in BENCHMARKS.items()
        for name in names
    }
    missing_raw_count = 0
    for base_date in weekdays(start_date, end_date):
        for series in INDEX_SERIES:
            path = _raw_path(raw_root, series, base_date)
            if not path.exists():
                missing_raw_count += 1
                continue
            response = _load_existing(path, series=series, base_date=base_date)
            value_field = "TOT_EARNG_IDX" if series == "bond" else "CLSPRC_IDX"
            for row in response.records:
                name = _benchmark_name(series, row)
                key = (series, name)
                if key not in observations or row[value_field] in {"", "-"}:
                    continue
                observations[key].append(
                    _normalize_observation(series, base_date, row)
                )

    benchmarks = []
    for (series, name), rows in observations.items():
        benchmarks.append(
            {
                "benchmark_id": f"{series}:{name}",
                "series": series,
                "index_name": name,
                "portfolio_role": BENCHMARKS[series][name],
                "asset_class": "fixed_income" if series == "bond" else "equity",
                "return_basis": (
                    "total_return_index" if series == "bond" else "price_index"
                ),
                "observation_count": len(rows),
                "history_start": rows[0]["date"] if rows else None,
                "history_end": rows[-1]["date"] if rows else None,
                "observations": rows,
            }
        )
    output = {
        "report_type": "krx_portfolio_benchmark_history",
        "source": "KRX statistical information",
        "requested_from": start_date.isoformat(),
        "requested_to": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "benchmark_count": len(benchmarks),
        "missing_raw_request_count": missing_raw_count,
        "usage": [
            "historical volatility and correlation evidence",
            "domestic equity and domestic bond stress calibration",
        ],
        "prohibited_usage": [
            "direct future return forecast",
            "automatic ETF eligibility determination",
        ],
        "benchmarks": benchmarks,
    }
    cache_root.mkdir(parents=True, exist_ok=True)
    output_path = cache_root / (
        f"index_benchmark_history_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    output["output_path"] = output_path.as_posix()
    return output


async def collect_krx_index_history(
    *,
    api_key: str,
    start_date: date,
    end_date: date,
    raw_root: Path,
    cache_root: Path,
    workers: int,
    force: bool,
) -> dict[str, Any]:
    if workers < 1 or workers > 16:
        raise ValueError("workers must be between 1 and 16")
    requested_dates = weekdays(start_date, end_date)
    requested = [
        (series, base_date)
        for base_date in requested_dates
        for series in INDEX_SERIES
    ]
    records: list[IndexCollectionRecord] = []
    pending = []
    for series, base_date in requested:
        path = _raw_path(raw_root, series, base_date)
        if path.exists() and not force:
            try:
                response = _load_existing(
                    path, series=series, base_date=base_date
                )
                records.append(
                    IndexCollectionRecord(
                        series=series,
                        base_date=base_date.isoformat(),
                        status="skipped_existing",
                        row_count=len(response.records),
                        usable_row_count=_usable_row_count(response),
                        sha256=hashlib.sha256(response.raw_content).hexdigest(),
                        relative_path=path.as_posix(),
                        retrieved_at=None,
                    )
                )
                continue
            except KrxApiError:
                pass
        pending.append((series, base_date))

    queue: asyncio.Queue[tuple[str, date] | None] = asyncio.Queue()
    for item in pending:
        queue.put_nowait(item)
    for _ in range(workers):
        queue.put_nowait(None)
    completed = 0
    progress_lock = asyncio.Lock()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(
            max_connections=workers,
            max_keepalive_connections=workers,
        ),
        headers={
            "Accept": "application/json",
            "User-Agent": "pension-copilot-krx-index/0.1",
        },
    ) as client:

        async def worker() -> None:
            nonlocal completed
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    return
                series, base_date = item
                try:
                    response = await _fetch_with_retry(
                        client,
                        api_key=api_key,
                        series=series,
                        base_date=base_date,
                    )
                    record = _persist_raw(
                        _raw_path(raw_root, series, base_date), response
                    )
                except KrxApiError as exc:
                    record = IndexCollectionRecord(
                        series=series,
                        base_date=base_date.isoformat(),
                        status="failed",
                        row_count=0,
                        usable_row_count=0,
                        sha256=None,
                        relative_path=None,
                        retrieved_at=datetime.now(UTC).isoformat(),
                        error=str(exc),
                    )
                finally:
                    queue.task_done()
                async with progress_lock:
                    records.append(record)
                    completed += 1
                    if completed % 100 == 0 or completed == len(pending):
                        print(
                            json.dumps(
                                {
                                    "completed": completed,
                                    "pending_total": len(pending),
                                    "last_series": series,
                                    "last_date": base_date.isoformat(),
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )

        tasks = [asyncio.create_task(worker()) for _ in range(workers)]
        await queue.join()
        await asyncio.gather(*tasks)

    records.sort(key=lambda item: (item.base_date, item.series))
    manifest_dir = raw_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / (
        f"index_daily_all_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    summary = {
        "source": "KRX statistical information",
        "endpoints": KRX_INDEX_ENDPOINTS,
        "requested_from": start_date.isoformat(),
        "requested_to": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_weekdays": len(requested_dates),
        "requested_api_calls": len(requested),
        "fetched": sum(item.status == "fetched" for item in records),
        "skipped_existing": sum(
            item.status == "skipped_existing" for item in records
        ),
        "empty_requests": sum(item.usable_row_count == 0 for item in records),
        "failed": sum(item.status == "failed" for item in records),
        "total_rows": sum(item.row_count for item in records),
        "usable_total_rows": sum(item.usable_row_count for item in records),
        "records": [asdict(item) for item in records],
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    benchmark_report = build_benchmark_history(
        start_date=start_date,
        end_date=end_date,
        raw_root=raw_root,
        cache_root=cache_root,
    )
    summary["manifest_path"] = manifest_path.as_posix()
    summary["benchmark_output_path"] = benchmark_report["output_path"]
    summary["benchmark_count"] = benchmark_report["benchmark_count"]
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect KRX equity and bond index history."
    )
    parser.add_argument(
        "--from-date", type=date.fromisoformat, default=DEFAULT_START_DATE
    )
    parser.add_argument(
        "--to-date",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
    )
    parser.add_argument("--raw-output", type=Path, default=Path("data/raw/krx"))
    parser.add_argument(
        "--cache-output", type=Path, default=Path("data/cache/krx")
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    api_key = require_secret(settings.krx_api_key, "KRX_API_KEY")
    result = asyncio.run(
        collect_krx_index_history(
            api_key=api_key,
            start_date=args.from_date,
            end_date=args.to_date,
            raw_root=args.raw_output,
            cache_root=args.cache_output,
            workers=args.workers,
            force=args.force,
        )
    )
    public_summary = {key: value for key, value in result.items() if key != "records"}
    print(json.dumps(public_summary, ensure_ascii=False, sort_keys=True))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
