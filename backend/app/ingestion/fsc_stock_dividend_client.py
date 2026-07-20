from dataclasses import dataclass
from typing import Any

import httpx

FSC_STOCK_DIVIDEND_ENDPOINT = (
    "https://apis.data.go.kr/1160100/GetStocDiviInfoService_V2/getDiviInfo_V2"
)
FSC_STOCK_DIVIDEND_REQUIRED_FIELDS = frozenset(
    {
        "basDt",
        "crno",
        "isinCd",
        "isinCdNm",
        "stckIssuCmpyNm",
        "dvdnBasDt",
        "cashDvdnPayDt",
        "stckHndvDt",
        "stckDvdnRcd",
        "stckDvdnRcdNm",
        "trsnmDptyDcd",
        "trsnmDptyDcdNm",
        "scrsItmsKcd",
        "scrsItmsKcdNm",
        "stckGenrDvdnAmt",
        "stckGrdnDvdnAmt",
        "stckGenrCashDvdnRt",
        "stckGenrDvdnRt",
        "cashGrdnDvdnRt",
        "stckGrdnDvdnRt",
        "stckParPrc",
        "stckStacMd",
    }
)


class FscStockDividendApiError(RuntimeError):
    """A sanitized FSC stock-dividend transport or contract failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class FscStockDividendPage:
    page_number: int
    rows_per_page: int
    total_count: int
    records: list[dict[str, str]]
    raw_content: bytes


def parse_fsc_stock_dividend_payload(
    payload: Any,
    *,
    raw_content: bytes = b"",
) -> FscStockDividendPage:
    if not isinstance(payload, dict):
        raise FscStockDividendApiError("FSC stock-dividend response must be an object")
    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise FscStockDividendApiError("FSC response wrapper must be an object")
    header = response.get("header")
    body = response.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        raise FscStockDividendApiError(
            "FSC stock-dividend response must contain header and body objects"
        )
    result_code = str(header.get("resultCode", ""))
    if result_code != "00":
        raise FscStockDividendApiError(
            f"FSC stock-dividend API rejected the request: code={result_code}"
        )
    try:
        page_number = int(body["pageNo"])
        rows_per_page = int(body["numOfRows"])
        total_count = int(body["totalCount"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FscStockDividendApiError(
            "FSC stock-dividend pagination contract is invalid"
        ) from exc

    items = body.get("items", [])
    records = items.get("item", []) if isinstance(items, dict) else items
    if records is None:
        records = []
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise FscStockDividendApiError("FSC stock-dividend items must be an array")
    normalized: list[dict[str, str]] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise FscStockDividendApiError(
                f"FSC stock-dividend row {position} must be an object"
            )
        missing = FSC_STOCK_DIVIDEND_REQUIRED_FIELDS.difference(record)
        if missing:
            fields = ",".join(sorted(missing))
            raise FscStockDividendApiError(
                f"FSC stock-dividend row {position} is missing fields: {fields}"
            )
        if not all(isinstance(value, str) for value in record.values()):
            raise FscStockDividendApiError(
                f"FSC stock-dividend row {position} fields must be strings"
            )
        normalized.append(record)
    if len(normalized) > rows_per_page:
        raise FscStockDividendApiError(
            "FSC stock-dividend page contains more rows than requested"
        )
    return FscStockDividendPage(
        page_number=page_number,
        rows_per_page=rows_per_page,
        total_count=total_count,
        records=normalized,
        raw_content=raw_content,
    )


def fetch_fsc_stock_dividend_page(
    client: httpx.Client,
    *,
    api_key: str,
    page_number: int,
    rows_per_page: int,
    base_date: str = "",
    corporate_registration_number: str = "",
    issuer_name: str = "",
) -> FscStockDividendPage:
    params = {
        "serviceKey": api_key,
        "resultType": "json",
        "pageNo": page_number,
        "numOfRows": rows_per_page,
    }
    optional = {
        "basDt": base_date,
        "crno": corporate_registration_number,
        "stckIssuCmpyNm": issuer_name,
    }
    params.update({key: value for key, value in optional.items() if value})
    try:
        response = client.get(FSC_STOCK_DIVIDEND_ENDPOINT, params=params)
    except httpx.HTTPError as exc:
        raise FscStockDividendApiError("FSC stock-dividend transport failed") from exc
    if response.status_code != 200:
        raise FscStockDividendApiError(
            f"FSC stock-dividend API returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise FscStockDividendApiError(
            "FSC stock-dividend API returned invalid JSON"
        ) from exc
    return parse_fsc_stock_dividend_payload(payload, raw_content=response.content)
