from dataclasses import dataclass
from typing import Any

import httpx

FSC_FUND_PRODUCT_ENDPOINT = (
    "https://apis.data.go.kr/1160100/service/"
    "GetFundProductInfoService/getStandardCodeInfo"
)
FSC_REQUIRED_FIELDS = frozenset(
    {
        "basDt",
        "srtnCd",
        "fndNm",
        "ctg",
        "setpDt",
        "fndTp",
        "prdClsfCd",
        "asoStdCd",
    }
)


class FscFundApiError(RuntimeError):
    """A sanitized FSC public-data transport or contract failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class FscFundPage:
    page_number: int
    rows_per_page: int
    total_count: int
    records: list[dict[str, str]]
    raw_content: bytes


def parse_fsc_fund_payload(
    payload: Any,
    *,
    raw_content: bytes = b"",
) -> FscFundPage:
    if not isinstance(payload, dict):
        raise FscFundApiError("FSC response must be a JSON object")
    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise FscFundApiError("FSC response wrapper must be a JSON object")
    header = response.get("header")
    body = response.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        raise FscFundApiError("FSC response must contain header and body objects")
    result_code = str(header.get("resultCode", ""))
    if result_code != "00":
        raise FscFundApiError(f"FSC API rejected the request: code={result_code}")

    try:
        page_number = int(body["pageNo"])
        rows_per_page = int(body["numOfRows"])
        total_count = int(body["totalCount"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FscFundApiError("FSC pagination contract is invalid") from exc

    items = body.get("items", [])
    records = items.get("item", []) if isinstance(items, dict) else items
    if records is None:
        records = []
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise FscFundApiError("FSC items must be an array")

    normalized: list[dict[str, str]] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise FscFundApiError(f"FSC row {position} must be a JSON object")
        missing = FSC_REQUIRED_FIELDS.difference(record)
        if missing:
            fields = ",".join(sorted(missing))
            raise FscFundApiError(f"FSC row {position} is missing fields: {fields}")
        if not all(isinstance(value, str) for value in record.values()):
            raise FscFundApiError(f"FSC row {position} fields must be strings")
        normalized.append(record)
    if len(normalized) > rows_per_page:
        raise FscFundApiError("FSC page contains more rows than requested")
    return FscFundPage(
        page_number=page_number,
        rows_per_page=rows_per_page,
        total_count=total_count,
        records=normalized,
        raw_content=raw_content,
    )


def fetch_fsc_fund_page(
    client: httpx.Client,
    *,
    api_key: str,
    page_number: int,
    rows_per_page: int,
    name_query: str,
) -> FscFundPage:
    try:
        response = client.get(
            FSC_FUND_PRODUCT_ENDPOINT,
            params={
                "serviceKey": api_key,
                "resultType": "json",
                "pageNo": page_number,
                "numOfRows": rows_per_page,
                "likeFndNm": name_query,
            },
        )
    except httpx.HTTPError as exc:
        raise FscFundApiError("FSC fund-product transport failed") from exc
    if response.status_code != 200:
        raise FscFundApiError(
            f"FSC fund-product API returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise FscFundApiError("FSC fund-product API returned invalid JSON") from exc
    return parse_fsc_fund_payload(payload, raw_content=response.content)
