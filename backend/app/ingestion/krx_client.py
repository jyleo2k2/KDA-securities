from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

KRX_ETF_DAILY_ENDPOINT = (
    "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
)
KRX_ETF_OUTPUT_BLOCK = "OutBlock_1"
KRX_INDEX_ENDPOINTS = {
    "krx": "https://data-dbg.krx.co.kr/svc/apis/idx/krx_dd_trd",
    "kospi": "https://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd",
    "kosdaq": "https://data-dbg.krx.co.kr/svc/apis/idx/kosdaq_dd_trd",
    "bond": "https://data-dbg.krx.co.kr/svc/apis/idx/bon_dd_trd",
}
KRX_EQUITY_INDEX_REQUIRED_FIELDS = frozenset(
    {
        "BAS_DD",
        "IDX_CLSS",
        "IDX_NM",
        "CLSPRC_IDX",
        "CMPPREVDD_IDX",
        "FLUC_RT",
        "OPNPRC_IDX",
        "HGPRC_IDX",
        "LWPRC_IDX",
        "ACC_TRDVOL",
        "ACC_TRDVAL",
        "MKTCAP",
    }
)
KRX_BOND_INDEX_REQUIRED_FIELDS = frozenset(
    {
        "BAS_DD",
        "BND_IDX_GRP_NM",
        "TOT_EARNG_IDX",
        "TOT_EARNG_IDX_CMPPREVDD",
        "NETPRC_IDX",
        "NETPRC_IDX_CMPPREVDD",
        "ZERO_REINVST_IDX",
        "ZERO_REINVST_IDX_CMPPREVDD",
        "CALL_REINVST_IDX",
        "CALL_REINVST_IDX_CMPPREVDD",
        "MKT_PRC_IDX",
        "MKT_PRC_IDX_CMPPREVDD",
        "BND_IDX_AVG_YD",
        "AVG_DURATION",
        "AVG_CONVEXITY_PRC",
    }
)
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


@dataclass(frozen=True, slots=True)
class KrxIndexDailyResponse:
    series: str
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


def parse_krx_index_payload(
    payload: Any,
    *,
    series: str,
    base_date: date,
    raw_content: bytes = b"",
) -> KrxIndexDailyResponse:
    if series not in KRX_INDEX_ENDPOINTS:
        raise ValueError(f"unsupported KRX index series: {series}")
    if not isinstance(payload, dict):
        raise KrxApiError("KRX index response must be a JSON object")
    records = payload.get(KRX_ETF_OUTPUT_BLOCK)
    if not isinstance(records, list):
        raise KrxApiError(
            f"KRX index response must contain {KRX_ETF_OUTPUT_BLOCK}"
        )
    required = (
        KRX_BOND_INDEX_REQUIRED_FIELDS
        if series == "bond"
        else KRX_EQUITY_INDEX_REQUIRED_FIELDS
    )
    expected_date = base_date.strftime("%Y%m%d")
    normalized: list[dict[str, str]] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise KrxApiError(f"KRX index row {position} must be a JSON object")
        missing = required.difference(record)
        if missing:
            fields = ",".join(sorted(missing))
            raise KrxApiError(
                f"KRX index row {position} is missing fields: {fields}"
            )
        if record["BAS_DD"] != expected_date:
            raise KrxApiError(
                f"KRX index row {position} date does not match requested base date"
            )
        if not all(isinstance(value, str) for value in record.values()):
            raise KrxApiError(f"KRX index row {position} fields must be strings")
        normalized.append(record)
    return KrxIndexDailyResponse(series, base_date, normalized, raw_content)


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


def _parse_index_response(
    response: httpx.Response,
    *,
    series: str,
    base_date: date,
) -> KrxIndexDailyResponse:
    if response.status_code != 200:
        raise KrxApiError(
            f"KRX {series} index returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise KrxApiError(f"KRX {series} index returned invalid JSON") from exc
    return parse_krx_index_payload(
        payload,
        series=series,
        base_date=base_date,
        raw_content=response.content,
    )


def fetch_krx_index_daily(
    client: httpx.Client,
    *,
    api_key: str,
    series: str,
    base_date: date,
) -> KrxIndexDailyResponse:
    try:
        endpoint = KRX_INDEX_ENDPOINTS[series]
    except KeyError as exc:
        raise ValueError(f"unsupported KRX index series: {series}") from exc
    try:
        response = client.get(
            endpoint,
            params={"basDd": base_date.strftime("%Y%m%d")},
            headers={"AUTH_KEY": api_key},
        )
    except httpx.HTTPError as exc:
        raise KrxApiError(f"KRX {series} index transport failed") from exc
    return _parse_index_response(response, series=series, base_date=base_date)


async def fetch_krx_index_daily_async(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    series: str,
    base_date: date,
) -> KrxIndexDailyResponse:
    try:
        endpoint = KRX_INDEX_ENDPOINTS[series]
    except KeyError as exc:
        raise ValueError(f"unsupported KRX index series: {series}") from exc
    try:
        response = await client.get(
            endpoint,
            params={"basDd": base_date.strftime("%Y%m%d")},
            headers={"AUTH_KEY": api_key},
        )
    except httpx.HTTPError as exc:
        raise KrxApiError(f"KRX {series} index transport failed") from exc
    return _parse_index_response(response, series=series, base_date=base_date)
