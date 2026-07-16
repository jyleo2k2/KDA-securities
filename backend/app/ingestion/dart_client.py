from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

DART_LIST_ENDPOINT = "https://opendart.fss.or.kr/api/list.json"
DART_DOCUMENT_ENDPOINT = "https://opendart.fss.or.kr/api/document.xml"
DART_FUND_DISCLOSURE_TYPE = "G"
DART_OK_STATUS = "000"
DART_NO_DATA_STATUS = "013"


class DartApiError(RuntimeError):
    """A sanitized OpenDART transport or contract failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        dart_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.dart_status = dart_status

    @property
    def retryable(self) -> bool:
        return (
            self.status_code is None
            or self.status_code == 429
            or (self.status_code is not None and self.status_code >= 500)
            or self.dart_status in {"020", "800", "900"}
        )


@dataclass(frozen=True, slots=True)
class DartDisclosure:
    corp_code: str
    corp_name: str
    stock_code: str
    corp_class: str
    report_name: str
    receipt_number: str
    filer_name: str
    receipt_date: date
    remarks: str


@dataclass(frozen=True, slots=True)
class DartDisclosurePage:
    page_number: int
    page_count: int
    total_count: int
    total_pages: int
    disclosures: list[DartDisclosure]
    raw_content: bytes


@dataclass(frozen=True, slots=True)
class DartOriginalDocument:
    receipt_number: str
    content: bytes
    member_names: tuple[str, ...]


def _as_int(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise DartApiError(f"OpenDART response has invalid {key}") from exc


def parse_disclosure_payload(
    payload: Any,
    *,
    raw_content: bytes = b"",
) -> DartDisclosurePage:
    if not isinstance(payload, dict):
        raise DartApiError("OpenDART response must be a JSON object")
    status = payload.get("status")
    if status == DART_NO_DATA_STATUS:
        return DartDisclosurePage(
            page_number=1,
            page_count=0,
            total_count=0,
            total_pages=0,
            disclosures=[],
            raw_content=raw_content,
        )
    if status != DART_OK_STATUS:
        safe_status = status if isinstance(status, str) else "unknown"
        raise DartApiError(
            f"OpenDART rejected the request: status={safe_status}",
            dart_status=safe_status,
        )

    page_number = _as_int(payload, "page_no")
    page_count = _as_int(payload, "page_count")
    total_count = _as_int(payload, "total_count")
    total_pages = _as_int(payload, "total_page")
    rows = payload.get("list")
    if not isinstance(rows, list):
        raise DartApiError("OpenDART disclosure list must be an array")

    required = {
        "corp_code",
        "corp_name",
        "stock_code",
        "corp_cls",
        "report_nm",
        "rcept_no",
        "flr_nm",
        "rcept_dt",
        "rm",
    }
    disclosures: list[DartDisclosure] = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DartApiError(f"OpenDART row {position} must be a JSON object")
        missing = required.difference(row)
        if missing:
            fields = ",".join(sorted(missing))
            raise DartApiError(f"OpenDART row {position} is missing fields: {fields}")
        if not all(isinstance(row[field], str) for field in required):
            raise DartApiError(f"OpenDART row {position} fields must be strings")
        try:
            receipt_date = date.fromisoformat(
                f"{row['rcept_dt'][:4]}-{row['rcept_dt'][4:6]}-{row['rcept_dt'][6:8]}"
            )
        except ValueError as exc:
            raise DartApiError(
                f"OpenDART row {position} has an invalid receipt date"
            ) from exc
        disclosures.append(
            DartDisclosure(
                corp_code=row["corp_code"],
                corp_name=row["corp_name"],
                stock_code=row["stock_code"],
                corp_class=row["corp_cls"],
                report_name=row["report_nm"],
                receipt_number=row["rcept_no"],
                filer_name=row["flr_nm"],
                receipt_date=receipt_date,
                remarks=row["rm"],
            )
        )
    if len(disclosures) > page_count:
        raise DartApiError("OpenDART returned more rows than the requested page size")
    return DartDisclosurePage(
        page_number=page_number,
        page_count=page_count,
        total_count=total_count,
        total_pages=total_pages,
        disclosures=disclosures,
        raw_content=raw_content,
    )


def fetch_fund_disclosure_page(
    client: httpx.Client,
    *,
    api_key: str,
    begin_date: date,
    end_date: date,
    page_number: int,
    page_count: int = 100,
) -> DartDisclosurePage:
    if begin_date > end_date:
        raise ValueError("begin_date must be on or before end_date")
    if page_number < 1 or page_count < 1 or page_count > 100:
        raise ValueError("OpenDART page_number/page_count is out of range")
    try:
        response = client.get(
            DART_LIST_ENDPOINT,
            params={
                "crtfc_key": api_key,
                "bgn_de": begin_date.strftime("%Y%m%d"),
                "end_de": end_date.strftime("%Y%m%d"),
                "pblntf_ty": DART_FUND_DISCLOSURE_TYPE,
                "page_no": page_number,
                "page_count": page_count,
            },
        )
    except httpx.HTTPError as exc:
        raise DartApiError("OpenDART disclosure transport failed") from exc
    if response.status_code != 200:
        raise DartApiError(
            f"OpenDART disclosure API returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise DartApiError("OpenDART disclosure API returned invalid JSON") from exc
    return parse_disclosure_payload(payload, raw_content=response.content)


def fetch_original_document(
    client: httpx.Client,
    *,
    api_key: str,
    receipt_number: str,
) -> DartOriginalDocument:
    if len(receipt_number) != 14 or not receipt_number.isdigit():
        raise ValueError("OpenDART receipt_number must contain 14 digits")
    try:
        response = client.get(
            DART_DOCUMENT_ENDPOINT,
            params={"crtfc_key": api_key, "rcept_no": receipt_number},
        )
    except httpx.HTTPError as exc:
        raise DartApiError("OpenDART original-document transport failed") from exc
    if response.status_code != 200:
        raise DartApiError(
            f"OpenDART original-document API returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        with ZipFile(BytesIO(response.content)) as archive:
            names = tuple(archive.namelist())
            if not names:
                raise DartApiError("OpenDART original-document ZIP is empty")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise DartApiError("OpenDART original-document ZIP is corrupt")
    except BadZipFile as exc:
        dart_status = None
        try:
            root = ElementTree.fromstring(response.content)
            status_node = root.find(".//status")
            if status_node is not None and status_node.text:
                dart_status = status_node.text.strip()
        except ElementTree.ParseError:
            pass
        suffix = f": status={dart_status}" if dart_status else ""
        raise DartApiError(
            "OpenDART original-document response is not a ZIP archive" + suffix,
            dart_status=dart_status,
        ) from exc
    return DartOriginalDocument(
        receipt_number=receipt_number,
        content=response.content,
        member_names=names,
    )
