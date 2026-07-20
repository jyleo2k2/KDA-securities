"""Secret-safe clients and normalizers for official macro observations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

BOK_API_ROOT = "https://ecos.bok.or.kr/api"
KOSIS_ENDPOINT = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
FRED_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"


class MacroApiError(RuntimeError):
    """An error that never includes credentials or a credential-bearing URL."""

    def __init__(self, message: str, *, code: str = "invalid_response") -> None:
        super().__init__(message)
        self.code = code if re.fullmatch(r"[a-z0-9_]+", code) else "invalid_response"


@dataclass(frozen=True, slots=True)
class RawMacroResponse:
    source: str
    request_params: dict[str, str | int]
    raw_content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class MacroObservation:
    metric_id: str
    source: str
    label: str
    period: str
    value: Decimal
    unit: str
    source_reference: str
    dimensions: dict[str, str]


def _decode_json(response: httpx.Response, *, source: str) -> tuple[Any, bytes]:
    if response.status_code != 200:
        raise MacroApiError(
            f"{source} returned HTTP {response.status_code}", code="http_error"
        )
    raw = response.content
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MacroApiError(
            f"{source} returned invalid JSON", code="invalid_json"
        ) from exc


def _decimal(value: Any, *, source: str, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise MacroApiError(
            f"{source} field {field} must be numeric", code="invalid_record"
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MacroApiError(
            f"{source} field {field} must be numeric", code="invalid_record"
        ) from exc
    if not parsed.is_finite():
        raise MacroApiError(
            f"{source} field {field} must be finite", code="invalid_record"
        )
    return parsed


def _required_text(row: dict[str, Any], field: str, *, source: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MacroApiError(
            f"{source} field {field} must be non-empty", code="invalid_record"
        )
    return value.strip()


def _raw_response(
    *, source: str, request_params: dict[str, str | int], raw: bytes
) -> RawMacroResponse:
    return RawMacroResponse(
        source=source,
        request_params=request_params,
        raw_content=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _bok_period(value: str, cycle: str) -> str:
    if cycle == "D" and re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if cycle == "M" and re.fullmatch(r"\d{6}", value):
        return f"{value[:4]}-{value[4:]}-01"
    if cycle == "A" and re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01"
    raise MacroApiError(
        "BOK TIME does not match the requested cycle", code="invalid_record"
    )


def fetch_bok_series(
    client: httpx.Client,
    *,
    api_key: str,
    metric_id: str,
    stat_code: str,
    cycle: str,
    start_period: str,
    end_period: str,
    item_code: str,
) -> tuple[RawMacroResponse, list[MacroObservation]]:
    request_params: dict[str, str | int] = {
        "stat_code": stat_code,
        "cycle": cycle,
        "start_period": start_period,
        "end_period": end_period,
        "item_code": item_code,
        "language": "kr",
        "start_index": 1,
        "end_index": 10000,
    }
    path = "/".join(
        quote(str(part), safe="")
        for part in (
            "StatisticSearch",
            api_key,
            "json",
            "kr",
            1,
            10000,
            stat_code,
            cycle,
            start_period,
            end_period,
            item_code,
        )
    )
    try:
        response = client.get(f"{BOK_API_ROOT}/{path}")
    except httpx.HTTPError as exc:
        raise MacroApiError("BOK transport failed", code="transport_error") from exc
    payload, raw = _decode_json(response, source="BOK")
    if not isinstance(payload, dict) or not isinstance(
        payload.get("StatisticSearch"), dict
    ):
        raise MacroApiError("BOK response contract is invalid", code="invalid_contract")
    result = payload["StatisticSearch"]
    rows = result.get("row")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise MacroApiError("BOK response rows are invalid", code="invalid_contract")

    observations: list[MacroObservation] = []
    for row in rows:
        if _required_text(row, "STAT_CODE", source="BOK") != stat_code:
            raise MacroApiError(
                "BOK returned an unexpected statistic", code="series_mismatch"
            )
        returned_item = _required_text(row, "ITEM_CODE1", source="BOK")
        if returned_item != item_code:
            raise MacroApiError(
                "BOK returned an unexpected item", code="series_mismatch"
            )
        observations.append(
            MacroObservation(
                metric_id=metric_id,
                source="BOK_ECOS",
                label=_required_text(row, "ITEM_NAME1", source="BOK"),
                period=_bok_period(_required_text(row, "TIME", source="BOK"), cycle),
                value=_decimal(row.get("DATA_VALUE"), source="BOK", field="DATA_VALUE"),
                unit=_required_text(row, "UNIT_NAME", source="BOK"),
                source_reference="https://ecos.bok.or.kr/api/",
                dimensions={"stat_code": stat_code, "item_code": item_code},
            )
        )
    observations.sort(key=lambda observation: observation.period)
    return _raw_response(
        source="BOK_ECOS", request_params=request_params, raw=raw
    ), observations


def fetch_kosis_series(
    client: httpx.Client,
    *,
    api_key: str,
    metric_id: str,
    org_id: str,
    table_id: str,
    item_id: str,
    object_l1: str,
    object_l2: str,
    latest_period_count: int,
) -> tuple[RawMacroResponse, list[MacroObservation]]:
    request_params: dict[str, str | int] = {
        "method": "getList",
        "itmId": item_id,
        "objL1": object_l1,
        "objL2": object_l2,
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "Y",
        "newEstPrdCnt": latest_period_count,
        "orgId": org_id,
        "tblId": table_id,
    }
    provider_params = {"apiKey": api_key, **request_params}
    for level in range(3, 9):
        provider_params[f"objL{level}"] = ""
    try:
        response = client.get(KOSIS_ENDPOINT, params=provider_params)
    except httpx.HTTPError as exc:
        raise MacroApiError("KOSIS transport failed", code="transport_error") from exc
    payload, raw = _decode_json(response, source="KOSIS")
    if isinstance(payload, dict) and "err" in payload:
        safe_code = str(payload.get("err", "unknown"))
        safe_code = safe_code if re.fullmatch(r"\d+", safe_code) else "unknown"
        raise MacroApiError(
            f"KOSIS rejected the request: code={safe_code}",
            code=f"provider_rejected_{safe_code}",
        )
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise MacroApiError("KOSIS response rows are invalid", code="invalid_contract")

    observations: list[MacroObservation] = []
    for row in payload:
        if _required_text(row, "ORG_ID", source="KOSIS") != org_id:
            raise MacroApiError(
                "KOSIS returned an unexpected organization", code="series_mismatch"
            )
        if _required_text(row, "TBL_ID", source="KOSIS") != table_id:
            raise MacroApiError(
                "KOSIS returned an unexpected table", code="series_mismatch"
            )
        if _required_text(row, "ITM_ID", source="KOSIS") != item_id:
            raise MacroApiError(
                "KOSIS returned an unexpected item", code="series_mismatch"
            )
        year = _required_text(row, "PRD_DE", source="KOSIS")
        if not re.fullmatch(r"\d{4}", year):
            raise MacroApiError("KOSIS PRD_DE must be a year", code="invalid_record")
        sex_code = _required_text(row, "C2", source="KOSIS")
        observations.append(
            MacroObservation(
                metric_id=f"{metric_id}_{sex_code.lower()}",
                source="KOSIS",
                label=(
                    f"{_required_text(row, 'ITM_NM', source='KOSIS')} "
                    f"({_required_text(row, 'C2_NM', source='KOSIS')})"
                ),
                period=f"{year}-01-01",
                value=_decimal(row.get("DT"), source="KOSIS", field="DT"),
                unit=str(row.get("UNIT_NM") or "년").strip(),
                source_reference="https://kosis.kr/openapi/",
                dimensions={
                    "org_id": org_id,
                    "table_id": table_id,
                    "country_code": _required_text(row, "C1", source="KOSIS"),
                    "country": _required_text(row, "C1_NM", source="KOSIS"),
                    "sex_code": sex_code,
                    "sex": _required_text(row, "C2_NM", source="KOSIS"),
                },
            )
        )
    observations.sort(
        key=lambda observation: (observation.metric_id, observation.period)
    )
    return _raw_response(
        source="KOSIS", request_params=request_params, raw=raw
    ), observations


def fetch_fred_series(
    client: httpx.Client,
    *,
    api_key: str,
    metric_id: str,
    series_id: str,
    label: str,
    unit: str,
    observation_start: str,
    observation_end: str,
    units: str = "lin",
) -> tuple[RawMacroResponse, list[MacroObservation]]:
    request_params: dict[str, str | int] = {
        "series_id": series_id,
        "file_type": "json",
        "observation_start": observation_start,
        "observation_end": observation_end,
        "sort_order": "asc",
        "units": units,
    }
    try:
        response = client.get(
            FRED_ENDPOINT, params={"api_key": api_key, **request_params}
        )
    except httpx.HTTPError as exc:
        raise MacroApiError("FRED transport failed", code="transport_error") from exc
    payload, raw = _decode_json(response, source="FRED")
    if not isinstance(payload, dict) or not isinstance(
        payload.get("observations"), list
    ):
        raise MacroApiError(
            "FRED response contract is invalid", code="invalid_contract"
        )

    observations: list[MacroObservation] = []
    for row in payload["observations"]:
        if not isinstance(row, dict):
            raise MacroApiError(
                "FRED observation must be an object", code="invalid_record"
            )
        value = row.get("value")
        if value == ".":
            continue
        period = _required_text(row, "date", source="FRED")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
            raise MacroApiError("FRED date is invalid", code="invalid_record")
        observations.append(
            MacroObservation(
                metric_id=metric_id,
                source="FRED",
                label=label,
                period=period,
                value=_decimal(value, source="FRED", field="value"),
                unit=unit,
                source_reference=f"https://fred.stlouisfed.org/series/{series_id}",
                dimensions={"series_id": series_id, "units_transform": units},
            )
        )
    observations.sort(key=lambda observation: observation.period)
    return _raw_response(
        source="FRED", request_params=request_params, raw=raw
    ), observations
