"""Collect approved official overseas ETF component disclosures."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

import httpx
import psycopg
import truststore
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.app.settings import get_settings

from ._secrets import require_secret

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
)
_TIGER_PDF_OVERVIEW = (
    "https://investments.miraeasset.com/tigeretf/ko/product/search/detail/"
    "pdf.ajax"
)
_TIGER_PDF_ROWS = (
    "https://investments.miraeasset.com/tigeretf/ko/product/search/detail/"
    "pdfListAjax.ajax"
)
_CASH_CODES = {"CASH00000001", "KRD010010001"}


@dataclass(frozen=True, slots=True)
class OfficialEtfSourceBinding:
    isu_code: str
    source_code: str
    publisher: str
    adapter_code: str
    source_product_key: str
    product_url: str
    holdings_url: str
    source_kind: str
    coverage_kind: str
    weight_basis: str
    replication_type: str
    management_type: str
    priority: int = 100
    source_id: int | None = None


@dataclass(frozen=True, slots=True)
class OfficialEtfHolding:
    rank: int
    component_code: str | None
    component_name: str
    weight_percent: Decimal


@dataclass(frozen=True, slots=True)
class OfficialEtfComponentSnapshot:
    isu_code: str
    as_of_date: date | None
    source_kind: str
    coverage_kind: str
    weight_basis: str
    completeness: str
    source_component_count: int
    holdings: tuple[OfficialEtfHolding, ...]
    raw_payload: dict[str, Any]
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class OfficialEtfRefreshSummary:
    requested_etf_count: int
    succeeded_etf_count: int
    partial_etf_count: int
    failed_etf_count: int


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.table_totals: list[int | None] = []
        self.inputs: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None
        self._table_total: int | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "table":
            self._table = []
            self._table_total = None
        elif tag == "tr" and self._table is not None:
            self._row = []
            total = values.get("data-tot-cnt")
            if total and total.isdigit():
                self._table_total = int(total)
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
        elif tag == "input":
            self.inputs.append(values)

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if not normalized:
            return
        self.text_parts.append(normalized)
        if self._cell_parts is not None:
            self._cell_parts.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell_parts is not None:
            if self._row is not None:
                self._row.append(" ".join(self._cell_parts).strip())
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self.table_totals.append(self._table_total)
            self._table = None
            self._table_total = None

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def _parse_html(html: str) -> _TableParser:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return parser


def _parse_decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "").removesuffix("%")
    if not text or text == "-":
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number <= 0 or number > 100:
        return None
    return number


def _parse_date(value: str) -> date | None:
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _input_value(
    parser: _TableParser, *, name: str | None = None, element_id: str | None = None
) -> str | None:
    for item in parser.inputs:
        if name is not None and item.get("name") == name:
            return item.get("value")
        if element_id is not None and item.get("id") == element_id:
            return item.get("value")
    return None


def _matching_table(
    parser: _TableParser, required_headers: set[str]
) -> tuple[list[list[str]], int | None] | None:
    for table, total in zip(parser.tables, parser.table_totals, strict=True):
        if not table:
            continue
        headers = {re.sub(r"\s+", "", value) for value in table[0]}
        if all(
            any(required in header for header in headers)
            for required in required_headers
        ):
            return table, total
    return None


def _payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _finish_snapshot(
    binding: OfficialEtfSourceBinding,
    *,
    as_of_date: date | None,
    rows: Sequence[tuple[str | None, str, Decimal]],
    source_component_count: int,
    raw_payload: dict[str, Any],
) -> OfficialEtfComponentSnapshot:
    seen: set[str] = set()
    valid: list[tuple[str | None, str, Decimal]] = []
    duplicate = False
    for component_code, component_name, weight in rows:
        name = component_name.strip()
        code = component_code.strip() if component_code else None
        key = code or name.casefold()
        if not name or key in seen:
            duplicate = duplicate or key in seen
            continue
        seen.add(key)
        valid.append((code, name, weight))
    valid.sort(key=lambda item: (-item[2], item[1], item[0] or ""))
    complete = as_of_date is not None and len(valid) >= 3 and not duplicate
    holdings = (
        tuple(
            OfficialEtfHolding(
                rank=rank,
                component_code=code,
                component_name=name,
                weight_percent=weight,
            )
            for rank, (code, name, weight) in enumerate(valid[:3], start=1)
        )
        if complete
        else ()
    )
    return OfficialEtfComponentSnapshot(
        isu_code=binding.isu_code,
        as_of_date=as_of_date,
        source_kind=binding.source_kind,
        coverage_kind=binding.coverage_kind,
        weight_basis=binding.weight_basis,
        completeness="complete" if complete else "partial",
        source_component_count=max(source_component_count, 0),
        holdings=holdings,
        raw_payload=raw_payload,
        raw_sha256=_payload_sha256(raw_payload),
    )


def normalize_sol_summary_html(
    binding: OfficialEtfSourceBinding, html: str
) -> OfficialEtfComponentSnapshot:
    parser = _parse_html(html)
    date_match = re.search(
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\s*기준", parser.text
    )
    as_of = (
        date(*(int(value) for value in date_match.groups()))
        if date_match
        else None
    )
    matched = _matching_table(parser, {"순위", "종목명", "비중"})
    rows: list[tuple[str | None, str, Decimal]] = []
    if matched is not None:
        table, _ = matched
        for cells in table[1:]:
            if len(cells) < 3:
                continue
            weight = _parse_decimal(cells[-1])
            if weight is not None:
                rows.append((None, cells[-2], weight))
    raw_payload = {"document_type": "official_ranked_holdings", "html": html}
    return _finish_snapshot(
        binding,
        as_of_date=as_of,
        rows=rows,
        source_component_count=len(rows),
        raw_payload=raw_payload,
    )


def normalize_tiger_pdf_html(
    binding: OfficialEtfSourceBinding,
    overview_html: str,
    rows_html: str,
) -> OfficialEtfComponentSnapshot:
    overview = _parse_html(overview_html)
    as_of = _parse_date(_input_value(overview, name="fixDate") or "")
    rows_parser = _parse_html(f"<table>{rows_html}</table>")
    table = rows_parser.tables[0] if rows_parser.tables else []
    total = rows_parser.table_totals[0] if rows_parser.table_totals else None
    rows: list[tuple[str | None, str, Decimal]] = []
    for cells in table:
        if len(cells) < 5:
            continue
        weight = _parse_decimal(cells[4])
        if weight is not None and cells[0].strip() not in _CASH_CODES:
            rows.append((cells[0], cells[1], weight))
    raw_payload = {
        "document_type": "official_creation_basket",
        "overview_html": overview_html,
        "rows_html": rows_html,
    }
    return _finish_snapshot(
        binding,
        as_of_date=as_of,
        rows=rows,
        source_component_count=total or len(rows),
        raw_payload=raw_payload,
    )


def normalize_samsung_product_payload(
    binding: OfficialEtfSourceBinding, payload: dict[str, Any]
) -> OfficialEtfComponentSnapshot:
    pdf = payload.get("pdf")
    if not isinstance(pdf, dict):
        pdf = {}
    as_of = _parse_date(str(pdf.get("gijunYMD") or ""))
    raw_list = pdf.get("list") if isinstance(pdf.get("list"), list) else []
    rows: list[tuple[str | None, str, Decimal]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        code = str(item.get("itmNo") or "").strip()
        weight = _parse_decimal(item.get("ratio"))
        if code in _CASH_CODES or weight is None:
            continue
        rows.append((code or None, str(item.get("secNm") or ""), weight))
    total_value = pdf.get("totalCnt")
    try:
        total = int(total_value) if total_value is not None else len(rows)
    except (TypeError, ValueError):
        total = len(rows)
    raw_payload = {"document_type": "official_creation_basket", "pdf": pdf}
    return _finish_snapshot(
        binding,
        as_of_date=as_of,
        rows=rows,
        source_component_count=total,
        raw_payload=raw_payload,
    )


def normalize_kiwoom_pdf_html(
    binding: OfficialEtfSourceBinding, html: str
) -> OfficialEtfComponentSnapshot:
    parser = _parse_html(html)
    as_of = _parse_date(_input_value(parser, element_id="pdfDt") or "")
    matched = _matching_table(parser, {"NO.", "종목명", "종목코드", "비중"})
    rows: list[tuple[str | None, str, Decimal]] = []
    if matched is not None:
        table, _ = matched
        for cells in table[1:]:
            if len(cells) < 4:
                continue
            code = cells[-2].strip()
            weight = _parse_decimal(cells[-1])
            if code in _CASH_CODES or weight is None:
                continue
            rows.append((code or None, cells[-3], weight))
    raw_payload = {"document_type": "official_creation_basket", "html": html}
    return _finish_snapshot(
        binding,
        as_of_date=as_of,
        rows=rows,
        source_component_count=len(rows),
        raw_payload=raw_payload,
    )


def fetch_official_etf_snapshot(
    binding: OfficialEtfSourceBinding,
    client: httpx.Client,
) -> OfficialEtfComponentSnapshot:
    if binding.adapter_code == "sol_summary":
        response = client.get(binding.holdings_url)
        response.raise_for_status()
        return normalize_sol_summary_html(binding, response.text)
    if binding.adapter_code == "kiwoom_pdf":
        response = client.get(binding.holdings_url)
        response.raise_for_status()
        return normalize_kiwoom_pdf_html(binding, response.text)
    if binding.adapter_code in {"samsung_kodex_pdf", "samsung_active_pdf"}:
        response = client.get(binding.holdings_url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("official Samsung ETF response must be an object")
        return normalize_samsung_product_payload(binding, payload)
    if binding.adapter_code == "tiger_pdf":
        # TIGER's legacy domain redirects to the current Mirae Asset domain.
        # Following this redirect is required before its public basket endpoints
        # will return a product-specific response.
        landing = client.get(binding.product_url, follow_redirects=True)
        landing.raise_for_status()
        overview = client.get(
            _TIGER_PDF_OVERVIEW,
            params={"ksdFund": binding.source_product_key},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=True,
        )
        overview.raise_for_status()
        parser = _parse_html(overview.text)
        fix_date = _input_value(parser, name="fixDate")
        rows = client.get(
            _TIGER_PDF_ROWS,
            params={
                "ksdFund": binding.source_product_key,
                "fixDate": re.sub(r"[^0-9]", "", fix_date),
                "prfPrd": "Week01",
                "order": "SRD",
                "pageIndex": "1",
                "firstIndex": "0",
                "listCnt": "10",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=True,
        )
        rows.raise_for_status()
        return normalize_tiger_pdf_html(binding, overview.text, rows.text)
    raise ValueError(f"unsupported official ETF adapter: {binding.adapter_code}")


class OfficialEtfComponentSnapshotWriter:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                yield connection
            return
        with self._connection_factory(self._database_url) as connection:
            yield connection

    def active_bindings(
        self, isu_codes: Sequence[str] | None = None
    ) -> tuple[OfficialEtfSourceBinding, ...]:
        selected_clause = ""
        params: list[object] = []
        if isu_codes:
            selected_clause = "and binding.isu_code = any(%s)"
            params.append(list(dict.fromkeys(isu_codes)))
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select
                    binding.isu_code, source.code, source.authority,
                    binding.adapter_code, binding.source_product_key,
                    binding.product_url, binding.holdings_url,
                    binding.source_kind, binding.coverage_kind,
                    binding.weight_basis, binding.replication_type,
                    binding.management_type, binding.priority, source.id
                from public.etf_component_source_bindings binding
                join public.data_sources source on source.id = binding.source_id
                where binding.is_active and source.is_active
                {selected_clause}
                order by binding.priority, binding.isu_code
                """,
                tuple(params),
            )
            return tuple(OfficialEtfSourceBinding(*row) for row in cursor.fetchall())

    def store_snapshot(
        self,
        binding: OfficialEtfSourceBinding,
        snapshot: OfficialEtfComponentSnapshot,
    ) -> bool:
        if binding.source_id is None:
            raise ValueError("source_id is required for persistence")
        captured_at = datetime.now(UTC)
        succeeded = snapshot.completeness == "complete"
        with self._connection() as connection, connection.cursor() as cursor:
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
                    binding.source_id,
                    binding.holdings_url,
                    Jsonb({"isu_code": binding.isu_code}),
                    snapshot.source_component_count,
                    Jsonb(
                        {
                            "adapter_code": binding.adapter_code,
                            "source_kind": snapshot.source_kind,
                            "coverage_kind": snapshot.coverage_kind,
                        }
                    ),
                ),
            )
            run = cursor.fetchone()
            if run is None:
                raise RuntimeError("failed to create official ETF ingestion run")
            run_id = run[0]
            cursor.execute(
                """
                insert into public.etf_component_snapshots (
                    isu_code, captured_at, status, component_count,
                    raw_payload, raw_sha256, source_id, ingestion_run_id,
                    as_of_date, source_kind, coverage_kind, completeness,
                    weight_basis, source_locator, source_component_count
                )
                values (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                on conflict do nothing
                returning id
                """,
                (
                    binding.isu_code,
                    captured_at,
                    "succeeded" if succeeded else "empty",
                    len(snapshot.holdings),
                    Jsonb(snapshot.raw_payload),
                    snapshot.raw_sha256,
                    binding.source_id,
                    run_id,
                    snapshot.as_of_date,
                    snapshot.source_kind,
                    snapshot.coverage_kind,
                    snapshot.completeness,
                    snapshot.weight_basis,
                    binding.holdings_url,
                    snapshot.source_component_count,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is not None:
                snapshot_id = inserted[0]
                if snapshot.holdings:
                    cursor.executemany(
                        """
                        insert into public.etf_component_snapshot_items (
                            snapshot_id, rank, component_isu_code,
                            component_name, weight_percent
                        )
                        values (%s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                snapshot_id,
                                holding.rank,
                                holding.component_code,
                                holding.component_name,
                                holding.weight_percent,
                            )
                            for holding in snapshot.holdings
                        ],
                    )
            cursor.execute(
                """
                update public.ingestion_runs
                set status = %s,
                    completed_at = now(),
                    normalized_record_count = %s,
                    upserted_record_count = %s,
                    response_code = %s,
                    response_message = %s,
                    error_message = %s
                where id = %s and status = 'running'
                """,
                (
                    "succeeded" if succeeded else "failed",
                    len(snapshot.holdings),
                    len(snapshot.holdings) if inserted is not None else 0,
                    "200" if succeeded else "422",
                    "Official ETF components",
                    None if succeeded else "official component snapshot is partial",
                    run_id,
                ),
            )
        return inserted is not None

    def record_failure(
        self, binding: OfficialEtfSourceBinding, error: Exception
    ) -> None:
        if binding.source_id is None:
            return
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.ingestion_runs (
                    source_id, endpoint, requested_params, status,
                    completed_at, response_code, response_message,
                    error_message, metadata
                )
                values (%s, %s, %s, 'failed', now(), 'error', %s, %s, %s)
                """,
                (
                    binding.source_id,
                    binding.holdings_url,
                    Jsonb({"isu_code": binding.isu_code}),
                    "Official ETF component fetch failed",
                    type(error).__name__,
                    Jsonb({"adapter_code": binding.adapter_code}),
                ),
            )


def refresh_official_etf_component_snapshots(
    database_url: str,
    *,
    isu_codes: Sequence[str] | None = None,
    limit: int | None = None,
    timeout_seconds: float = 20.0,
) -> OfficialEtfRefreshSummary:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    with ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=1,
        timeout=10,
        kwargs={"connect_timeout": 10},
        open=False,
    ) as pool:
        writer = OfficialEtfComponentSnapshotWriter(database_url, pool=pool)
        bindings = writer.active_bindings(isu_codes)
        if limit is not None:
            bindings = bindings[:limit]
        succeeded = 0
        partial = 0
        failed = 0
        with httpx.Client(
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"},
            follow_redirects=True,
            timeout=timeout_seconds,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        ) as client:
            for binding in bindings:
                try:
                    snapshot = fetch_official_etf_snapshot(binding, client)
                    writer.store_snapshot(binding, snapshot)
                except Exception as exc:  # noqa: BLE001 — isolate per official product.
                    failed += 1
                    writer.record_failure(binding, exc)
                    continue
                if snapshot.completeness == "complete":
                    succeeded += 1
                else:
                    partial += 1
        return OfficialEtfRefreshSummary(
            requested_etf_count=len(bindings),
            succeeded_etf_count=succeeded,
            partial_etf_count=partial,
            failed_etf_count=failed,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh approved official overseas ETF component TOP3 snapshots"
    )
    parser.add_argument("--isu-code", action="append", dest="isu_codes")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()
    database_url = require_secret(get_settings().database_url, "DATABASE_URL")
    summary = refresh_official_etf_component_snapshots(
        database_url,
        isu_codes=args.isu_codes,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "requested_etf_count": summary.requested_etf_count,
                "succeeded_etf_count": summary.succeeded_etf_count,
                "partial_etf_count": summary.partial_etf_count,
                "failed_etf_count": summary.failed_etf_count,
            },
            ensure_ascii=False,
        )
    )
    return 1 if summary.failed_etf_count or summary.partial_etf_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
