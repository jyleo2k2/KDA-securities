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

from .krx_client import (
    KRX_ETF_DAILY_ENDPOINT,
    KrxApiError,
    KrxEtfDailyResponse,
    fetch_krx_etf_daily_async,
    parse_krx_etf_payload,
)

DEFAULT_START_DATE = date(2020, 1, 2)
DEFAULT_WORKERS = 6
MAX_RETRIES = 3


@dataclass(frozen=True, slots=True)
class CollectionRecord:
    base_date: str
    status: str
    row_count: int
    usable_row_count: int
    sha256: str | None
    relative_path: str | None
    retrieved_at: str | None
    error: str | None = None


def _weekdays(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("from-date must not be after to-date")
    days = (end - start).days
    return [
        current
        for offset in range(days + 1)
        if (current := start + timedelta(days=offset)).weekday() < 5
    ]


def _raw_path(output_root: Path, base_date: date) -> Path:
    return (
        output_root
        / "etf_bydd_trd"
        / f"{base_date.year:04d}"
        / f"{base_date.month:02d}"
        / f"{base_date:%Y%m%d}.json"
    )


def _load_existing(path: Path, base_date: date) -> KrxEtfDailyResponse:
    raw_content = path.read_bytes()
    try:
        payload = json.loads(raw_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KrxApiError(f"existing KRX file is invalid JSON: {path}") from exc
    return parse_krx_etf_payload(
        payload,
        base_date=base_date,
        raw_content=raw_content,
    )


def _persist_raw(path: Path, response: KrxEtfDailyResponse) -> CollectionRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(response.raw_content)
    temporary.replace(path)
    digest = hashlib.sha256(response.raw_content).hexdigest()
    return CollectionRecord(
        base_date=f"{response.base_date:%Y-%m-%d}",
        status="fetched",
        row_count=len(response.records),
        usable_row_count=_usable_row_count(response),
        sha256=digest,
        relative_path=path.as_posix(),
        retrieved_at=datetime.now(UTC).isoformat(),
    )


def _usable_row_count(response: KrxEtfDailyResponse) -> int:
    return sum(
        record["TDD_CLSPRC"] not in {"", "-"} for record in response.records
    )


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    base_date: date,
) -> KrxEtfDailyResponse:
    last_error: KrxApiError | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await fetch_krx_etf_daily_async(
                client,
                api_key=api_key,
                base_date=base_date,
            )
        except KrxApiError as exc:
            last_error = exc
            retryable = exc.status_code is None or exc.status_code == 429 or (
                exc.status_code >= 500
            )
            if not retryable or attempt == MAX_RETRIES:
                break
            await asyncio.sleep(2**attempt)
    if last_error is None:
        raise RuntimeError("KRX retry loop completed without a result")
    raise last_error


async def collect_krx_etf_history(
    *,
    api_key: str,
    start_date: date,
    end_date: date,
    output_root: Path,
    workers: int,
    force: bool,
) -> dict[str, Any]:
    if workers < 1 or workers > 16:
        raise ValueError("workers must be between 1 and 16")

    requested_dates = _weekdays(start_date, end_date)
    records: list[CollectionRecord] = []
    pending: list[date] = []
    for base_date in requested_dates:
        path = _raw_path(output_root, base_date)
        if path.exists() and not force:
            try:
                response = _load_existing(path, base_date)
                records.append(
                    CollectionRecord(
                        base_date=f"{base_date:%Y-%m-%d}",
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
        pending.append(base_date)

    completed = 0
    progress_lock = asyncio.Lock()
    queue: asyncio.Queue[date | None] = asyncio.Queue()
    for base_date in pending:
        queue.put_nowait(base_date)
    for _ in range(workers):
        queue.put_nowait(None)

    timeout = httpx.Timeout(30.0)
    limits = httpx.Limits(
        max_connections=workers,
        max_keepalive_connections=workers,
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers={"Accept": "application/json", "User-Agent": "pension-copilot-krx/0.1"},
    ) as client:

        async def worker() -> None:
            nonlocal completed
            while True:
                base_date = await queue.get()
                if base_date is None:
                    queue.task_done()
                    return
                try:
                    response = await _fetch_with_retry(
                        client,
                        api_key=api_key,
                        base_date=base_date,
                    )
                    record = _persist_raw(
                        _raw_path(output_root, base_date),
                        response,
                    )
                except KrxApiError as exc:
                    record = CollectionRecord(
                        base_date=f"{base_date:%Y-%m-%d}",
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
                    if completed % 25 == 0 or completed == len(pending):
                        print(
                            json.dumps(
                                {
                                    "completed": completed,
                                    "pending_total": len(pending),
                                    "last_date": record.base_date,
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )

        tasks = [asyncio.create_task(worker()) for _ in range(workers)]
        await queue.join()
        await asyncio.gather(*tasks)

    records.sort(key=lambda item: item.base_date)
    manifest_dir = output_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / (
        f"etf_bydd_trd_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    summary = {
        "source": "KRX statistical information",
        "endpoint": KRX_ETF_DAILY_ENDPOINT,
        "requested_from": start_date.isoformat(),
        "requested_to": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_weekdays": len(requested_dates),
        "fetched": sum(item.status == "fetched" for item in records),
        "skipped_existing": sum(
            item.status == "skipped_existing" for item in records
        ),
        "empty_dates": sum(item.usable_row_count == 0 for item in records),
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
    summary["manifest_path"] = manifest_path.as_posix()
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill KRX ETF daily raw JSON with resumable storage."
    )
    parser.add_argument(
        "--from-date",
        type=date.fromisoformat,
        default=DEFAULT_START_DATE,
    )
    parser.add_argument(
        "--to-date",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
    )
    parser.add_argument("--output", type=Path, default=Path("data/raw/krx"))
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.krx_api_key is None:
        raise SystemExit("KRX_API_KEY is required")
    api_key = settings.krx_api_key.get_secret_value().strip()
    if not api_key:
        raise SystemExit("KRX_API_KEY is required")

    result = asyncio.run(
        collect_krx_etf_history(
            api_key=api_key,
            start_date=args.from_date,
            end_date=args.to_date,
            output_root=args.output,
            workers=args.workers,
            force=args.force,
        )
    )
    public_summary = {key: value for key, value in result.items() if key != "records"}
    print(json.dumps(public_summary, ensure_ascii=False, sort_keys=True))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
