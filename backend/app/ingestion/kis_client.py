from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_TOKEN_ENDPOINT = "/oauth2/tokenP"
KIS_COMPONENT_ENDPOINT = "/uapi/etfetn/v1/quotations/inquire-component-stock-price"
KIS_PRICE_ENDPOINT = "/uapi/etfetn/v1/quotations/inquire-price"
KIS_ADJUSTED_DAILY_PRICE_ENDPOINT = (
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
)
KIS_KSD_DIVIDEND_ENDPOINT = "/uapi/domestic-stock/v1/ksdinfo/dividend"
KIS_COMPONENT_TR_ID = "FHKST121600C0"
KIS_PRICE_TR_ID = "FHPST02400000"
KIS_ADJUSTED_DAILY_PRICE_TR_ID = "FHKST03010100"
KIS_KSD_DIVIDEND_TR_ID = "HHKDB669102C0"
KIS_ADJUSTED_DAILY_PRICE_REQUIRED_FIELDS = frozenset(
    {
        "stck_bsop_date",
        "stck_clpr",
        "stck_oprc",
        "stck_hgpr",
        "stck_lwpr",
        "acml_vol",
        "acml_tr_pbmn",
        "flng_cls_code",
        "prtt_rate",
        "mod_yn",
        "prdy_vrss_sign",
        "prdy_vrss",
        "revl_issu_reas",
    }
)
KIS_KSD_DIVIDEND_REQUIRED_FIELDS = frozenset(
    {
        "record_date",
        "sht_cd",
        "divi_kind",
        "face_val",
        "per_sto_divi_amt",
        "divi_rate",
        "stk_divi_rate",
        "divi_pay_dt",
        "stk_div_pay_dt",
        "odd_pay_dt",
        "stk_kind",
        "high_divi_gb",
    }
)


class KisApiError(RuntimeError):
    """A KIS failure whose message never contains credentials or tokens."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        message_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message_code = message_code

    @property
    def retryable(self) -> bool:
        return (
            self.status_code is None
            or self.status_code == 429
            or (self.status_code is not None and self.status_code >= 500)
            or self.message_code == "EGW00201"
        )


@dataclass(frozen=True, slots=True)
class KisAccessToken:
    value: str
    token_type: str
    expires_in: int
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class KisApiResponse:
    payload: dict[str, Any]
    raw_content: bytes


def _json_object(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise KisApiError(
            f"KIS {operation} returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise KisApiError(f"KIS {operation} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise KisApiError(f"KIS {operation} response must be a JSON object")
    return payload


def issue_access_token(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
) -> KisAccessToken:
    try:
        response = client.post(
            KIS_TOKEN_ENDPOINT,
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
        )
    except httpx.HTTPError as exc:
        raise KisApiError("KIS token transport failed") from exc
    payload = _json_object(response, operation="token")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        code = payload.get("error_code") or payload.get("msg_cd")
        raise KisApiError(
            "KIS token response did not contain an access token",
            message_code=code if isinstance(code, str) else None,
        )
    expires_in = payload.get("expires_in", 0)
    try:
        normalized_expires_in = int(expires_in)
    except (TypeError, ValueError):
        normalized_expires_in = 0
    expires_at = payload.get("access_token_token_expired")
    return KisAccessToken(
        value=token,
        token_type=str(payload.get("token_type", "Bearer")),
        expires_in=normalized_expires_in,
        expires_at=expires_at if isinstance(expires_at, str) else None,
    )


def _fetch(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
    access_token: str,
    endpoint: str,
    tr_id: str,
    params: dict[str, str],
    operation: str,
) -> KisApiResponse:
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
    }
    try:
        response = client.get(endpoint, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise KisApiError(f"KIS {operation} transport failed") from exc
    payload = _json_object(response, operation=operation)
    result_code = payload.get("rt_cd")
    if result_code != "0":
        message_code = payload.get("msg_cd")
        raise KisApiError(
            f"KIS {operation} rejected the request"
            + (f" ({message_code})" if isinstance(message_code, str) else ""),
            status_code=response.status_code,
            message_code=message_code if isinstance(message_code, str) else None,
        )
    return KisApiResponse(payload=payload, raw_content=response.content)


def fetch_etf_components(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
    access_token: str,
    isu_code: str,
) -> KisApiResponse:
    response = _fetch(
        client,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
        endpoint=KIS_COMPONENT_ENDPOINT,
        tr_id=KIS_COMPONENT_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": isu_code,
            "FID_COND_SCR_DIV_CODE": "11216",
        },
        operation="ETF components",
    )
    output1 = response.payload.get("output1")
    output2 = response.payload.get("output2")
    if not isinstance(output1, dict) or not isinstance(output2, list):
        raise KisApiError("KIS ETF components response has an invalid schema")
    if not all(isinstance(row, dict) for row in output2):
        raise KisApiError("KIS ETF component rows must be JSON objects")
    return response


def fetch_etf_price(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
    access_token: str,
    isu_code: str,
) -> KisApiResponse:
    response = _fetch(
        client,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
        endpoint=KIS_PRICE_ENDPOINT,
        tr_id=KIS_PRICE_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": isu_code,
        },
        operation="ETF price",
    )
    if not isinstance(response.payload.get("output"), dict):
        raise KisApiError("KIS ETF price response has an invalid schema")
    return response


def parse_adjusted_daily_price_payload(
    payload: Any,
    *,
    raw_content: bytes = b"",
) -> KisApiResponse:
    if not isinstance(payload, dict):
        raise KisApiError("KIS adjusted daily price payload must be an object")
    if payload.get("rt_cd") != "0":
        raise KisApiError("KIS adjusted daily price payload is not successful")
    output1 = payload.get("output1")
    output2 = payload.get("output2")
    if not isinstance(output1, dict) or not isinstance(output2, list):
        raise KisApiError("KIS adjusted daily price response has an invalid schema")
    previous_date: str | None = None
    for position, row in enumerate(output2):
        if not isinstance(row, dict):
            raise KisApiError(
                f"KIS adjusted daily price row {position} must be an object"
            )
        missing = KIS_ADJUSTED_DAILY_PRICE_REQUIRED_FIELDS.difference(row)
        if missing:
            fields = ",".join(sorted(missing))
            raise KisApiError(
                f"KIS adjusted daily price row {position} is missing: {fields}"
            )
        if not all(isinstance(value, str) for value in row.values()):
            raise KisApiError(
                f"KIS adjusted daily price row {position} fields must be strings"
            )
        business_date = row["stck_bsop_date"]
        if len(business_date) != 8 or not business_date.isdigit():
            raise KisApiError(
                f"KIS adjusted daily price row {position} has an invalid date"
            )
        if previous_date is not None and business_date >= previous_date:
            raise KisApiError(
                "KIS adjusted daily price rows must be unique and descending"
            )
        previous_date = business_date
    return KisApiResponse(payload=payload, raw_content=raw_content)


def fetch_adjusted_daily_item_prices(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
    access_token: str,
    isu_code: str,
    start_date: str,
    end_date: str,
) -> KisApiResponse:
    response = _fetch(
        client,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
        endpoint=KIS_ADJUSTED_DAILY_PRICE_ENDPOINT,
        tr_id=KIS_ADJUSTED_DAILY_PRICE_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": isu_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        },
        operation="adjusted daily item chart price",
    )
    return parse_adjusted_daily_price_payload(
        response.payload,
        raw_content=response.raw_content,
    )


def parse_ksd_dividend_payload(
    payload: Any,
    *,
    raw_content: bytes = b"",
) -> KisApiResponse:
    if not isinstance(payload, dict):
        raise KisApiError("KIS KSD dividend payload must be an object")
    if payload.get("rt_cd") != "0":
        raise KisApiError("KIS KSD dividend payload is not successful")
    rows = payload.get("output1", [])
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise KisApiError("KIS KSD dividend response has an invalid schema")
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise KisApiError(f"KIS KSD dividend row {position} must be an object")
        missing = KIS_KSD_DIVIDEND_REQUIRED_FIELDS.difference(row)
        if missing:
            fields = ",".join(sorted(missing))
            raise KisApiError(f"KIS KSD dividend row {position} is missing: {fields}")
        if not all(isinstance(value, str) for value in row.values()):
            raise KisApiError(f"KIS KSD dividend row {position} fields must be strings")
        for field in ("record_date", "divi_pay_dt", "stk_div_pay_dt", "odd_pay_dt"):
            value = row[field].strip()
            if field == "record_date" and not value:
                raise KisApiError(
                    f"KIS KSD dividend row {position} has an invalid {field}"
                )
            if field != "record_date" and value in {"", "00000000"}:
                continue
            try:
                if value:
                    date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
            except ValueError as exc:
                raise KisApiError(
                    f"KIS KSD dividend row {position} has an invalid {field}"
                ) from exc
    return KisApiResponse(payload=payload, raw_content=raw_content)


def fetch_ksd_dividend_schedule(
    client: httpx.Client,
    *,
    app_key: str,
    app_secret: str,
    access_token: str,
    start_date: str,
    end_date: str,
    isu_code: str = "",
    dividend_kind: str = "0",
) -> KisApiResponse:
    response = _fetch(
        client,
        app_key=app_key,
        app_secret=app_secret,
        access_token=access_token,
        endpoint=KIS_KSD_DIVIDEND_ENDPOINT,
        tr_id=KIS_KSD_DIVIDEND_TR_ID,
        params={
            "CTS": "",
            "GB1": dividend_kind,
            "F_DT": start_date,
            "T_DT": end_date,
            "SHT_CD": isu_code,
            "HIGH_GB": "",
        },
        operation="KSD dividend schedule",
    )
    return parse_ksd_dividend_payload(
        response.payload,
        raw_content=response.raw_content,
    )
