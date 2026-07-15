import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

PS_CORP_ENDPOINT = "https://www.fss.or.kr/openapi/api/psCorpList.json"
RP_CORP_ENDPOINT = "https://www.fss.or.kr/openapi/api/rpCorpResultList.json"


class FssApiError(RuntimeError):
    """A sanitized FSS transport or response-contract failure."""

    def __init__(self, message: str, *, code: str = "invalid_response") -> None:
        super().__init__(message)
        self.code = code if re.fullmatch(r"[a-z0-9_]+", code) else "invalid_response"


@dataclass(frozen=True, slots=True)
class FssResponse:
    api_code: str
    message: str
    source_count: int
    records: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PensionSavingsProviderRow:
    area_name_raw: str
    company_name_raw: str
    reserve_source_value: Decimal | None
    reserve_source_value_1y: Decimal | None
    reserve_source_value_2y: Decimal | None
    reserve_source_value_3y: Decimal | None
    earn_rate_current: Decimal | None
    earn_rate_1y: Decimal | None
    earn_rate_2y: Decimal | None
    earn_rate_3y: Decimal | None
    fee_rate_1y: Decimal | None
    fee_rate_2y: Decimal | None
    fee_rate_3y: Decimal | None
    avg_earn_rate_3y: Decimal | None
    avg_earn_rate_5y: Decimal | None
    avg_earn_rate_7y: Decimal | None
    avg_earn_rate_10y: Decimal | None
    avg_fee_rate_3y: Decimal | None
    avg_fee_rate_5y: Decimal | None
    avg_fee_rate_7y: Decimal | None
    avg_fee_rate_10y: Decimal | None
    quality_flags: tuple[str, ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RetirementProviderRow:
    area_name_raw: str
    company_name_raw: str
    response_division: str
    scheme: str
    reserve_source_value: Decimal | None
    earn_rate_current: Decimal | None
    avg_earn_rate_3y: Decimal | None
    avg_earn_rate_5y: Decimal | None
    avg_earn_rate_7y: Decimal | None
    avg_earn_rate_10y: Decimal | None
    quality_flags: tuple[str, ...]
    raw_payload: dict[str, Any]


def _decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise FssApiError(
            f"FSS field {field_name} must be numeric or null",
            code="invalid_record",
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FssApiError(
            f"FSS field {field_name} must be numeric or null",
            code="invalid_record",
        ) from exc
    if not parsed.is_finite():
        raise FssApiError(
            f"FSS field {field_name} must be finite",
            code="invalid_record",
        )
    return parsed


def _required_text(record: dict[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise FssApiError(
            f"FSS field {field_name} must be a non-empty string",
            code="invalid_record",
        )
    return value.strip()


def fetch_fss_response(
    client: httpx.Client,
    *,
    endpoint: str,
    api_key: str,
    request_params: dict[str, int],
) -> FssResponse:
    """Call FSS without allowing the key to appear in raised error messages."""

    try:
        response = client.get(endpoint, params={"key": api_key, **request_params})
    except httpx.HTTPError as exc:
        raise FssApiError(
            f"FSS transport failed for {endpoint}",
            code="transport_error",
        ) from exc
    if response.status_code != 200:
        raise FssApiError(
            f"FSS returned HTTP {response.status_code} for {endpoint}",
            code="http_error",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise FssApiError(
            f"FSS returned invalid JSON for {endpoint}",
            code="invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise FssApiError(
            "FSS response must be a JSON object",
            code="invalid_contract",
        )

    code = str(payload.get("code", ""))
    if code != "000":
        safe_code = code if re.fullmatch(r"[0-9]{3}", code) else "unknown"
        raise FssApiError(
            f"FSS API rejected the request: code={safe_code}",
            code=f"provider_rejected_{safe_code}",
        )

    records = payload.get("list")
    count = payload.get("count")
    if not isinstance(records, list) or isinstance(count, bool):
        raise FssApiError(
            "FSS response count/list contract is invalid",
            code="invalid_contract",
        )
    try:
        parsed_count = int(count)
    except (TypeError, ValueError) as exc:
        raise FssApiError(
            "FSS response count must be an integer",
            code="invalid_contract",
        ) from exc
    if parsed_count != len(records):
        raise FssApiError(
            f"FSS count mismatch: declared={parsed_count}, received={len(records)}",
            code="count_mismatch",
        )
    if not all(isinstance(record, dict) for record in records):
        raise FssApiError(
            "FSS list entries must be JSON objects",
            code="invalid_contract",
        )
    return FssResponse(code, "accepted", parsed_count, records)


def normalize_pension_savings(
    response: FssResponse,
) -> list[PensionSavingsProviderRow]:
    rows: list[PensionSavingsProviderRow] = []
    for raw in response.records:
        reserve = _decimal(raw.get("reserve"), "reserve")
        rate_fields = (
            "earnRate",
            "earnRate1",
            "earnRate2",
            "earnRate3",
            "feeRate1",
            "feeRate2",
            "feeRate3",
            "avgEarnRate3",
            "avgEarnRate5",
            "avgEarnRate7",
            "avgEarnRate10",
            "avgFeeRate3",
            "avgFeeRate5",
            "avgFeeRate7",
            "avgFeeRate10",
        )
        parsed_rates = {field: _decimal(raw.get(field), field) for field in rate_fields}
        flags: list[str] = []
        if reserve is None:
            flags.append("reserve_missing")
        if any(value is None for value in parsed_rates.values()):
            flags.append("rate_missing")

        rows.append(
            PensionSavingsProviderRow(
                area_name_raw=_required_text(raw, "area"),
                company_name_raw=_required_text(raw, "company"),
                reserve_source_value=reserve,
                reserve_source_value_1y=_decimal(raw.get("reserve1"), "reserve1"),
                reserve_source_value_2y=_decimal(raw.get("reserve2"), "reserve2"),
                reserve_source_value_3y=_decimal(raw.get("reserve3"), "reserve3"),
                earn_rate_current=parsed_rates["earnRate"],
                earn_rate_1y=parsed_rates["earnRate1"],
                earn_rate_2y=parsed_rates["earnRate2"],
                earn_rate_3y=parsed_rates["earnRate3"],
                fee_rate_1y=parsed_rates["feeRate1"],
                fee_rate_2y=parsed_rates["feeRate2"],
                fee_rate_3y=parsed_rates["feeRate3"],
                avg_earn_rate_3y=parsed_rates["avgEarnRate3"],
                avg_earn_rate_5y=parsed_rates["avgEarnRate5"],
                avg_earn_rate_7y=parsed_rates["avgEarnRate7"],
                avg_earn_rate_10y=parsed_rates["avgEarnRate10"],
                avg_fee_rate_3y=parsed_rates["avgFeeRate3"],
                avg_fee_rate_5y=parsed_rates["avgFeeRate5"],
                avg_fee_rate_7y=parsed_rates["avgFeeRate7"],
                avg_fee_rate_10y=parsed_rates["avgFeeRate10"],
                quality_flags=tuple(flags),
                raw_payload=raw,
            )
        )
    return rows


def normalize_retirement(
    response: FssResponse,
) -> list[RetirementProviderRow]:
    rows: list[RetirementProviderRow] = []
    for outer in response.records:
        company = _required_text(outer, "company")
        area = _required_text(outer, "area")
        result_list = outer.get("list")
        if not isinstance(result_list, list) or len(result_list) != 1:
            raise FssApiError(
                "FSS retirement company record must contain exactly one result entry",
                code="invalid_record",
            )
        result = result_list[0]
        if not isinstance(result, dict):
            raise FssApiError(
                "FSS retirement result entry must be an object",
                code="invalid_record",
            )
        division = _required_text(result, "division")

        for scheme in ("db", "dc", "irp"):
            prefix = scheme
            reserve = _decimal(result.get(f"{prefix}Reserve"), f"{prefix}Reserve")
            current = _decimal(result.get(f"{prefix}EarnRate"), f"{prefix}EarnRate")
            long_rates = {
                years: _decimal(
                    result.get(f"{prefix}EarnRate{years}"),
                    f"{prefix}EarnRate{years}",
                )
                for years in (3, 5, 7, 10)
            }
            flags: list[str] = []
            if reserve is None:
                flags.append("reserve_missing")
            if current is None or any(value is None for value in long_rates.values()):
                flags.append("rate_missing")
            rows.append(
                RetirementProviderRow(
                    area_name_raw=area,
                    company_name_raw=company,
                    response_division=division,
                    scheme=scheme,
                    reserve_source_value=reserve,
                    earn_rate_current=current,
                    avg_earn_rate_3y=long_rates[3],
                    avg_earn_rate_5y=long_rates[5],
                    avg_earn_rate_7y=long_rates[7],
                    avg_earn_rate_10y=long_rates[10],
                    quality_flags=tuple(flags),
                    raw_payload=outer,
                )
            )
    return rows
