"""Weekly KIS ETF component TOP3 ingestion into the remote product database."""

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg
from psycopg.types.json import Jsonb

from backend.app.engine.etf_theme import normalize_kis_holdings
from backend.app.settings import get_settings

from ._retry import retry_with_backoff
from ._secrets import require_secret
from .kis_client import (
    KIS_BASE_URL,
    KIS_COMPONENT_ENDPOINT,
    KisApiError,
    KisApiResponse,
    fetch_etf_components,
    issue_access_token,
)

KIS_COMPONENT_SOURCE_CODE = "kis_etf_components"
DEFAULT_DELAY_SECONDS = 0.25
KST = ZoneInfo("Asia/Seoul")


class KisComponentSnapshotLoadError(RuntimeError):
    """A database-side KIS component ingestion failure."""


class _KisTransientEmpty(KisApiError):
    def __init__(self, response: KisApiResponse) -> None:
        super().__init__("KIS reported ETF components but returned no detail rows")
        self.response = response


@dataclass(frozen=True, slots=True)
class _ComponentFetchResult:
    response: KisApiResponse
    transient_empty: bool


@dataclass(frozen=True, slots=True)
class KisComponentRefreshSummary:
    requested_etf_count: int
    succeeded_etf_count: int
    empty_etf_count: int
    failed_etf_count: int
    transient_empty_etf_count: int
    true_empty_etf_count: int


def _reported_component_count(payload: dict[str, Any]) -> int | None:
    output1 = payload.get("output1")
    if not isinstance(output1, dict):
        return None
    value = output1.get("etf_cnfg_issu_cnt")
    try:
        count = int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _is_transient_empty(payload: dict[str, Any]) -> bool:
    rows = payload.get("output2")
    if not isinstance(rows, list) or rows:
        return False
    return _reported_component_count(payload) != 0


def _fetch_components_with_retry(
    fetch: Callable[[], KisApiResponse],
    *,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> _ComponentFetchResult:
    def checked_fetch() -> KisApiResponse:
        response = fetch()
        if _is_transient_empty(response.payload):
            raise _KisTransientEmpty(response)
        return response

    try:
        response = retry_with_backoff(
            checked_fetch,
            exceptions=KisApiError,
            is_retryable=lambda error: error.retryable,
            max_retries=max_retries,
            sleep=sleep,
        )
    except _KisTransientEmpty as error:
        return _ComponentFetchResult(response=error.response, transient_empty=True)
    return _ComponentFetchResult(response=response, transient_empty=False)


class KisComponentSnapshotWriter:
    def __init__(
        self,
        database_url: str,
        *,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._connection_factory(self._database_url) as connection:
            yield connection

    def target_codes(
        self,
        *,
        limit: int | None = None,
        resume_since: datetime | None = None,
        isu_codes: Sequence[str] | None = None,
    ) -> tuple[int, list[str]]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        selected_codes = tuple(
            dict.fromkeys(
                code.strip().upper() for code in isu_codes or () if code.strip()
            )
        )
        if isu_codes is not None and not selected_codes:
            raise ValueError("isu_codes must contain at least one code")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id
                from public.etf_dataset_versions
                where status = 'ready'
                order by as_of desc, id desc
                limit 1
                """
            )
            version = cursor.fetchone()
            if version is None:
                raise KisComponentSnapshotLoadError("no ready ETF dataset version")
            version_id = int(version[0])
            resume_clause = (
                """
                and not exists (
                    select 1
                    from public.etf_component_snapshots snapshot
                    where snapshot.isu_code = product.isu_code
                      and snapshot.captured_at >= %s
                      and (
                          snapshot.status = 'succeeded'
                          or (
                              snapshot.status = 'empty'
                              and snapshot.raw_payload #>>
                                  '{output1,etf_cnfg_issu_cnt}' ~ '^\\s*0+\\s*$'
                          )
                      )
                )
                """
                if resume_since is not None
                else ""
            )
            selected_clause = (
                "and isu_code = any(%s)" if selected_codes else ""
            )
            params: list[object] = [version_id]
            if selected_codes:
                params.append(list(selected_codes))
            if resume_since is not None:
                params.append(resume_since)
            if limit is not None:
                params.append(limit)
            cursor.execute(
                """
                select distinct isu_code
                from public.etf_universe_products product
                where version_id = %s
                """
                + selected_clause
                + resume_clause
                + """
                order by isu_code
                """
                + (" limit %s" if limit is not None else ""),
                tuple(params),
            )
            return version_id, [str(row[0]) for row in cursor.fetchall()]

    def start_run(self, *, version_id: int, source_count: int) -> tuple[Any, int]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "select id from public.data_sources where code = %s",
                (KIS_COMPONENT_SOURCE_CODE,),
            )
            source = cursor.fetchone()
            if source is None:
                raise KisComponentSnapshotLoadError("KIS component data source missing")
            source_id = int(source[0])
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status,
                    source_record_count, metadata
                )
                values (%s, %s, %s, 'running', %s, %s)
                returning id
                """,
                (
                    source_id,
                    KIS_COMPONENT_ENDPOINT,
                    Jsonb(
                        {
                            "dataset_version_id": version_id,
                            "refresh_interval_hours": 168,
                        }
                    ),
                    source_count,
                    Jsonb({"data_boundary": "official_market_data", "is_mock": False}),
                ),
            )
            run = cursor.fetchone()
            if run is None:
                raise KisComponentSnapshotLoadError("failed to create ingestion run")
            return run[0], source_id

    def store_snapshot(
        self,
        *,
        run_id: Any,
        source_id: int,
        isu_code: str,
        captured_at: datetime,
        payload: dict[str, Any],
        raw_content: bytes,
        holdings: tuple[Any, ...],
    ) -> None:
        component_rows = payload.get("output2")
        if not isinstance(component_rows, list):
            raise KisComponentSnapshotLoadError("KIS component response rows missing")
        if component_rows and not holdings:
            raise KisComponentSnapshotLoadError(
                "KIS component rows could not be normalized"
            )
        status = "succeeded" if component_rows else "empty"
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.etf_component_snapshots (
                    isu_code, captured_at, status, component_count, raw_payload,
                    raw_sha256, source_id, ingestion_run_id
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    isu_code,
                    captured_at,
                    status,
                    len(component_rows),
                    Jsonb(payload),
                    hashlib.sha256(raw_content).hexdigest(),
                    source_id,
                    run_id,
                ),
            )
            snapshot = cursor.fetchone()
            if snapshot is None:
                raise KisComponentSnapshotLoadError(
                    "failed to store component snapshot"
                )
            if holdings:
                cursor.executemany(
                    """
                    insert into public.etf_component_snapshot_items (
                        snapshot_id, rank, component_isu_code, component_name,
                        weight_percent
                    ) values (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            snapshot[0],
                            rank,
                            holding.component_code,
                            holding.component_name,
                            holding.weight_percent,
                        )
                        for rank, holding in enumerate(holdings[:3], start=1)
                    ],
                )

    def complete_run(
        self, *, run_id: Any, summary: KisComponentRefreshSummary
    ) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'succeeded', completed_at = now(),
                    normalized_record_count = %s, upserted_record_count = %s,
                    response_code = '200', response_message = 'KIS ETF components',
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (
                    summary.succeeded_etf_count,
                    summary.succeeded_etf_count + summary.empty_etf_count,
                    Jsonb(
                        {
                            "outcome": "partial"
                            if summary.failed_etf_count
                            or summary.transient_empty_etf_count
                            else "succeeded",
                            "empty_etf_count": summary.empty_etf_count,
                            "transient_empty_etf_count": (
                                summary.transient_empty_etf_count
                            ),
                            "true_empty_etf_count": summary.true_empty_etf_count,
                            "failed_etf_count": summary.failed_etf_count,
                        }
                    ),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KisComponentSnapshotLoadError("failed to complete ingestion run")

    def fail_run(self, *, run_id: Any) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.ingestion_runs
                set status = 'failed', completed_at = now(),
                    error_message = 'KIS component refresh failed',
                    metadata = metadata || %s
                where id = %s and status = 'running'
                """,
                (Jsonb({"outcome": "failed"}), run_id),
            )


def refresh_kis_component_snapshots(
    *,
    database_url: str,
    app_key: str,
    app_secret: str,
    limit: int | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    resume_today: bool = False,
    isu_codes: Sequence[str] | None = None,
) -> KisComponentRefreshSummary:
    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative")
    writer = KisComponentSnapshotWriter(database_url)
    resume_since = (
        datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        if resume_today
        else None
    )
    version_id, codes = writer.target_codes(
        limit=limit,
        resume_since=resume_since,
        isu_codes=isu_codes,
    )
    run_id, source_id = writer.start_run(version_id=version_id, source_count=len(codes))
    succeeded = transient_empty = true_empty = failed = 0
    try:
        with httpx.Client(
            base_url=KIS_BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={
                "Accept": "application/json",
                "User-Agent": "pension-copilot-kis/0.1",
            },
        ) as client:
            token = issue_access_token(client, app_key=app_key, app_secret=app_secret)
            for position, code in enumerate(codes, start=1):
                try:
                    fetch_result = _fetch_components_with_retry(
                        lambda code=code: fetch_etf_components(
                            client,
                            app_key=app_key,
                            app_secret=app_secret,
                            access_token=token.value,
                            isu_code=code,
                        )
                    )
                    response = fetch_result.response
                    component_rows = response.payload["output2"]
                    holdings = normalize_kis_holdings(component_rows)
                    writer.store_snapshot(
                        run_id=run_id,
                        source_id=source_id,
                        isu_code=code,
                        captured_at=datetime.now(UTC),
                        payload=response.payload,
                        raw_content=response.raw_content,
                        holdings=holdings,
                    )
                    if component_rows:
                        succeeded += 1
                    elif fetch_result.transient_empty:
                        transient_empty += 1
                    else:
                        true_empty += 1
                except (KisApiError, KisComponentSnapshotLoadError):
                    failed += 1
                if delay_seconds:
                    time.sleep(delay_seconds)
                if position % 25 == 0 or position == len(codes):
                    print(
                        json.dumps({"completed": position, "total": len(codes)}),
                        flush=True,
                    )
        empty = transient_empty + true_empty
        summary = KisComponentRefreshSummary(
            requested_etf_count=len(codes),
            succeeded_etf_count=succeeded,
            empty_etf_count=empty,
            failed_etf_count=failed,
            transient_empty_etf_count=transient_empty,
            true_empty_etf_count=true_empty,
        )
        writer.complete_run(run_id=run_id, summary=summary)
        return summary
    except Exception:
        writer.fail_run(run_id=run_id)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh KIS ETF component TOP3 snapshots"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--isu-code",
        action="append",
        dest="isu_codes",
        help="refresh only this ETF code; may be repeated",
    )
    parser.add_argument(
        "--resume-today",
        action="store_true",
        help="skip ETFs with a component snapshot already captured today in KST",
    )
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()
    settings = get_settings()
    database_url = require_secret(settings.database_url, "DATABASE_URL")
    summary = refresh_kis_component_snapshots(
        database_url=database_url,
        app_key=require_secret(
            settings.kis_app_key, "KIS_APP_KEY and KIS_APP_SECRET"
        ),
        app_secret=require_secret(
            settings.kis_app_secret, "KIS_APP_KEY and KIS_APP_SECRET"
        ),
        limit=args.limit,
        delay_seconds=args.delay_seconds,
        resume_today=args.resume_today,
        isu_codes=args.isu_codes,
    )
    print(json.dumps(asdict(summary), sort_keys=True))
    return 1 if summary.failed_etf_count or summary.transient_empty_etf_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
