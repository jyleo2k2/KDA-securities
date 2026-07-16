import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx

KIND_BASE_URL = "https://kind.krx.co.kr"
KIND_ETF_DISCLOSURE_ENDPOINT = "/disclosure/disclosurebystocktype.do"
KIND_VIEWER_ENDPOINT = "/common/disclsviewer.do"
KIND_REPORT_NAME = "ETF이익금분배 신고"
KIND_EX_DATE_REPORT_NAME = "ETF 분배락 기준가격 안내"
RECEIPT_PATTERN = re.compile(r"openDisclsViewer\('([0-9]{14})'")
ISSUE_PATTERN = re.compile(r"etfisusummary_open\('([0-9A-Z]{1,6})'")
SET_PATH_PATTERN = re.compile(r"parent\.setPath\([^,]*,\s*'([^']+)'", re.DOTALL)
ISIN_PATTERN = re.compile(r"KR7([0-9A-Z]{6})[0-9]{3}")


class KindDisclosureError(RuntimeError):
    """A sanitized KIND disclosure collection failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class KindDisclosureRow:
    submitted_at: datetime
    isu_code: str
    isu_name: str
    receipt_number: str
    report_title: str
    submitter: str


@dataclass(frozen=True, slots=True)
class KindDistributionEvent:
    isu_code: str
    isin: str
    isu_name: str
    record_date: date
    payment_date: date | None
    distribution_per_share_krw: Decimal
    receipt_number: str
    submitted_at: datetime
    source_url: str


@dataclass(frozen=True, slots=True)
class KindDistributionExDateEvent:
    isu_code: str
    isu_name: str
    effective_date: date
    reference_price_krw: Decimal
    reason: str
    legal_basis: str
    receipt_number: str
    submitted_at: datetime
    source_url: str


def decode_kind_html(raw_content: bytes) -> str:
    for encoding in ("utf-8", "cp949"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise KindDisclosureError("KIND returned undecodable HTML")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize_issue_code(raw: str) -> str:
    value = raw.strip().upper()
    return value.zfill(6) if value.isdigit() else value


def _kind_etf_issue_id_to_short_code(raw: str) -> str:
    issue_id = _normalize_issue_code(raw).zfill(6)
    return f"{issue_id}0"[-6:]


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._cell_parts: list[str] = []
        self._receipt_number: str | None = None
        self._issue_code: str | None = None
        self._issue_name = ""
        self._report_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._in_row = True
            self._cells = []
            self._receipt_number = None
            self._issue_code = None
            self._issue_name = ""
            self._report_title = ""
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_parts = []
        elif tag == "a" and self._in_row:
            onclick = attributes.get("onclick") or ""
            receipt = RECEIPT_PATTERN.search(onclick)
            issue = ISSUE_PATTERN.search(onclick)
            title = _clean(attributes.get("title") or "")
            if receipt:
                self._receipt_number = receipt.group(1)
                self._report_title = title
            if issue:
                self._issue_code = _normalize_issue_code(issue.group(1))
                self._issue_name = title

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            self._cells.append(_clean("".join(self._cell_parts)))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._receipt_number and self._issue_code and len(self._cells) >= 2:
                self.rows.append(
                    {
                        "cells": self._cells,
                        "receipt_number": self._receipt_number,
                        "isu_code": self._issue_code,
                        "isu_name": self._issue_name,
                        "report_title": self._report_title,
                    }
                )
            self._in_row = False


class _MainDocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_main_select = False
        self.doc_numbers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "select" and attributes.get("id") == "mainDoc":
            self._in_main_select = True
        elif tag == "option" and self._in_main_select:
            value = attributes.get("value") or ""
            doc_number = value.split("|", maxsplit=1)[0]
            if doc_number.isdigit():
                self.doc_numbers.append(doc_number)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self._in_main_select = False


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth == 1:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell_parts is not None:
            if self._row is not None:
                self._row.append(_clean("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._rows:
                self.tables.append(self._rows)


def parse_disclosure_search(html: str) -> list[KindDisclosureRow]:
    parser = _SearchResultParser()
    parser.feed(html)
    results = []
    for row in parser.rows:
        cells = row["cells"]
        try:
            submitted_at = datetime.strptime(cells[1], "%Y-%m-%d %H:%M")
        except (IndexError, ValueError) as exc:
            raise KindDisclosureError("KIND search row has an invalid date") from exc
        results.append(
            KindDisclosureRow(
                submitted_at=submitted_at,
                isu_code=row["isu_code"],
                isu_name=row["isu_name"],
                receipt_number=row["receipt_number"],
                report_title=row["report_title"],
                submitter=cells[-1] if cells else "",
            )
        )
    return results


def parse_main_document_number(html: str) -> str:
    parser = _MainDocumentParser()
    parser.feed(html)
    if not parser.doc_numbers:
        raise KindDisclosureError("KIND viewer did not contain a main document")
    return parser.doc_numbers[0]


def parse_document_url(html: str) -> str:
    match = SET_PATH_PATTERN.search(html)
    if not match:
        raise KindDisclosureError("KIND document path response is invalid")
    return urljoin(KIND_BASE_URL, match.group(1))


def _date_value(raw: str) -> date | None:
    if raw in {"", "-"}:
        return None
    try:
        return date.fromisoformat(raw.replace(".", "-").rstrip("."))
    except ValueError:
        return None


def _amount(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "").replace("원", "").strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def parse_distribution_events(
    html: str,
    *,
    receipt_number: str,
    submitted_at: datetime,
    source_url: str,
) -> list[KindDistributionEvent]:
    parser = _TableParser()
    parser.feed(html)
    events: list[KindDistributionEvent] = []
    for table in parser.tables:
        header_index = next(
            (
                index
                for index, row in enumerate(table)
                if any("종목코드" in cell for cell in row)
                and any("분배금" in cell for cell in row)
            ),
            None,
        )
        if header_index is None:
            continue
        header = table[header_index]
        code_index = next(
            (index for index, cell in enumerate(header) if "종목코드" in cell),
            None,
        )
        name_index = next(
            (
                index
                for index, cell in enumerate(header)
                if "종목약명" in cell or cell.strip() == "종목명"
            ),
            None,
        )
        amount_index = next(
            (
                index
                for index, cell in enumerate(header)
                if "분배금" in cell and "지급" not in cell
            ),
            None,
        )
        date_indexes = [
            index for index, cell in enumerate(header) if "지급기준일" in cell
        ]
        payment_indexes = [
            index for index, cell in enumerate(header) if "지급예정일" in cell
        ]
        if (
            code_index is None
            or name_index is None
            or amount_index is None
            or not date_indexes
        ):
            continue
        for row in table[header_index + 1 :]:
            required = max(code_index, name_index, amount_index, date_indexes[0])
            if len(row) <= required:
                continue
            isin_match = ISIN_PATTERN.fullmatch(row[code_index].strip().upper())
            record_date = _date_value(row[date_indexes[0]])
            amount = _amount(row[amount_index])
            if not isin_match or record_date is None or amount is None:
                continue
            payment_date = (
                _date_value(row[payment_indexes[0]])
                if payment_indexes and len(row) > payment_indexes[0]
                else None
            )
            events.append(
                KindDistributionEvent(
                    isu_code=isin_match.group(1),
                    isin=row[code_index].strip().upper(),
                    isu_name=row[name_index],
                    record_date=record_date,
                    payment_date=payment_date,
                    distribution_per_share_krw=amount,
                    receipt_number=receipt_number,
                    submitted_at=submitted_at,
                    source_url=source_url,
                )
            )
    return events


def parse_distribution_ex_date_event(
    html: str,
    *,
    isu_code: str,
    isu_name: str,
    receipt_number: str,
    submitted_at: datetime,
    source_url: str,
) -> KindDistributionExDateEvent:
    parser = _TableParser()
    parser.feed(html)
    for table in parser.tables:
        fields: dict[str, str] = {}
        for row in table:
            if len(row) < 2:
                continue
            label = re.sub(r"^\d+\.\s*", "", row[0]).strip()
            fields[label] = row[1].strip()
        effective_date = _date_value(fields.get("적용일", ""))
        reference_price = _amount(fields.get("기준가격(원)", ""))
        reason = fields.get("사유", "")
        if effective_date is None or reference_price is None or "분배락" not in reason:
            continue
        return KindDistributionExDateEvent(
            isu_code=_kind_etf_issue_id_to_short_code(isu_code),
            isu_name=fields.get("종목명") or isu_name,
            effective_date=effective_date,
            reference_price_krw=reference_price,
            reason=reason,
            legal_basis=fields.get("근거규정", ""),
            receipt_number=receipt_number,
            submitted_at=submitted_at,
            source_url=source_url,
        )
    raise KindDisclosureError(
        "KIND ex-distribution document has no valid effective date"
    )


def _request(
    client: httpx.Client,
    method: str,
    endpoint: str,
    *,
    operation: str,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    try:
        response = client.request(method, endpoint, data=data)
    except httpx.HTTPError as exc:
        raise KindDisclosureError(f"KIND {operation} transport failed") from exc
    if response.status_code != 200:
        raise KindDisclosureError(
            f"KIND {operation} returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    return response


def fetch_disclosure_search(
    client: httpx.Client,
    *,
    start_date: date,
    end_date: date,
    page_index: int,
    page_size: int = 3000,
    report_name: str = KIND_REPORT_NAME,
) -> bytes:
    response = _request(
        client,
        "POST",
        KIND_ETF_DISCLOSURE_ENDPOINT,
        operation=f"ETF disclosure search ({report_name})",
        data={
            "method": "searchDisclosureByStockTypeEtfSub",
            "forward": "disclosurebystocktype_etf_sub",
            "currentPageSize": str(page_size),
            "pageIndex": str(page_index),
            "orderMode": "1",
            "orderStat": "D",
            "etfIsuSrtCd": "",
            "reportCd": "",
            "reportTmp": "",
            "etfIsuSrtNm": "",
            "reportNm": report_name,
            "fromDate": start_date.isoformat(),
            "toDate": end_date.isoformat(),
        },
    )
    return response.content


def fetch_viewer(client: httpx.Client, *, receipt_number: str) -> bytes:
    response = _request(
        client,
        "GET",
        f"{KIND_VIEWER_ENDPOINT}?method=search&acptno={receipt_number}"
        "&docno=&viewerhost=&viewerport=",
        operation="disclosure viewer",
    )
    return response.content


def fetch_document_path(client: httpx.Client, *, doc_number: str) -> bytes:
    response = _request(
        client,
        "POST",
        KIND_VIEWER_ENDPOINT,
        operation="disclosure document path",
        data={"method": "searchContents", "docNo": doc_number},
    )
    return response.content


def fetch_document(client: httpx.Client, *, source_url: str) -> bytes:
    response = _request(
        client,
        "GET",
        source_url,
        operation="disclosure document",
    )
    return response.content
