from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

KRX_ETF_DAILY_ENDPOINT = (
    "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
)
KRX_ETF_OUTPUT_BLOCK = "OutBlock_1"
KRX_ETF_REQUIRED_FIELDS = frozenset(
    {
        "BAS_DD",
        "ISU_CD",
        "ISU_NM",
        "TDD_CLSPRC",
        "CMPPREVDD_PRC",
        "FLUC_RT",
        "NAV",
        "TDD_OPNPRC",
        "TDD_HGPRC",
        "TDD_LWPRC",
        "ACC_TRDVOL",
        "ACC_TRDVAL",
        "MKTCAP",
        "INVSTASST_NETASST_TOTAMT",
        "LIST_SHRS",
        "IDX_IND_NM",
        "OBJ_STKPRC_IDX",
        "CMPPREVDD_IDX",
        "FLUC_RT_IDX",
    }
)


class KrxApiError(RuntimeError):
    """A KRX failure whose message never contains the authentication key."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class KrxEtfDailyResponse:
    base_date: date
    records: list[dict[str, str]]
    raw_content: bytes


def parse_krx_etf_payload(
    payload: Any,
    *,
    base_date: date,
    raw_content: bytes = b"",
) -> KrxEtfDailyResponse:
    if not isinstance(payload, dict):
        raise KrxApiError("KRX response must be a JSON object")
    records = payload.get(KRX_ETF_OUTPUT_BLOCK)
    if not isinstance(records, list):
        raise KrxApiError(f"KRX response must contain {KRX_ETF_OUTPUT_BLOCK}")

    expected_date = base_date.strftime("%Y%m%d")
    normalized: list[dict[str, str]] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise KrxApiError(f"KRX row {position} must be a JSON object")
        missing = KRX_ETF_REQUIRED_FIELDS.difference(record)
        if missing:
            fields = ",".join(sorted(missing))
            raise KrxApiError(f"KRX row {position} is missing fields: {fields}")
        if record["BAS_DD"] != expected_date:
            raise KrxApiError(
                f"KRX row {position} date does not match requested base date"
            )
        if not all(isinstance(value, str) for value in record.values()):
            raise KrxApiError(f"KRX row {position} fields must be strings")
        normalized.append(record)
    return KrxEtfDailyResponse(base_date, normalized, raw_content)


def _parse_response(response: httpx.Response, base_date: date) -> KrxEtfDailyResponse:
    if response.status_code != 200:
        raise KrxApiError(
            f"KRX returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise KrxApiError("KRX returned invalid JSON") from exc
    return parse_krx_etf_payload(
        payload,
        base_date=base_date,
        raw_content=response.content,
    )


def fetch_krx_etf_daily(
    client: httpx.Client,
    *,
    api_key: str,
    base_date: date,
) -> KrxEtfDailyResponse:
    try:
        response = client.get(
            KRX_ETF_DAILY_ENDPOINT,
            params={"basDd": base_date.strftime("%Y%m%d")},
            headers={"AUTH_KEY": api_key},
        )
    except httpx.HTTPError as exc:
        raise KrxApiError("KRX transport failed") from exc
    return _parse_response(response, base_date)


async def fetch_krx_etf_daily_async(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    base_date: date,
) -> KrxEtfDailyResponse:
    try:
        response = await client.get(
            KRX_ETF_DAILY_ENDPOINT,
            params={"basDd": base_date.strftime("%Y%m%d")},
            headers={"AUTH_KEY": api_key},
        )
    except httpx.HTTPError as exc:
        raise KrxApiError("KRX transport failed") from exc
    return _parse_response(response, base_date)
