from dataclasses import dataclass
from typing import Any

import httpx

LAW_OPEN_ENDPOINT = "https://www.law.go.kr/DRF/lawService.do"
VALID_TARGETS = frozenset({"law", "admrul"})


class LawOpenApiError(RuntimeError):
    """A sanitized law-open-data transport or contract failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class LawOpenDocument:
    target: str
    requested_name: str
    returned_name: str
    effective_date: str
    payload: dict[str, Any]
    raw_content: bytes


def _document_metadata(
    payload: dict[str, Any],
    *,
    target: str,
) -> tuple[str, str]:
    if target == "law":
        root = payload.get("법령")
        info_key = "기본정보"
        name_key = "법령명_한글"
    elif target == "admrul":
        root = payload.get("AdmRulService")
        info_key = "행정규칙기본정보"
        name_key = "행정규칙명"
    else:
        raise LawOpenApiError(f"unsupported law-open-data target: {target}")
    if not isinstance(root, dict):
        raise LawOpenApiError(f"law-open-data {target} response root is invalid")
    info = root.get(info_key)
    if not isinstance(info, dict):
        raise LawOpenApiError(f"law-open-data {target} metadata is invalid")
    returned_name = info.get(name_key)
    effective_date = info.get("시행일자")
    if not isinstance(returned_name, str) or not returned_name.strip():
        raise LawOpenApiError("law-open-data document name is missing")
    if not isinstance(effective_date, str) or len(effective_date) != 8:
        raise LawOpenApiError("law-open-data effective date is invalid")
    if target == "admrul" and info.get("현행여부") != "Y":
        raise LawOpenApiError("law-open-data returned a non-current rule")
    return returned_name.strip(), effective_date


def parse_law_open_payload(
    payload: Any,
    *,
    target: str,
    requested_name: str,
    raw_content: bytes = b"",
) -> LawOpenDocument:
    if target not in VALID_TARGETS:
        raise LawOpenApiError(f"unsupported law-open-data target: {target}")
    if not isinstance(payload, dict):
        raise LawOpenApiError("law-open-data response must be a JSON object")
    returned_name, effective_date = _document_metadata(payload, target=target)
    if returned_name.replace(" ", "") != requested_name.replace(" ", ""):
        raise LawOpenApiError("law-open-data returned an unexpected document")
    return LawOpenDocument(
        target=target,
        requested_name=requested_name,
        returned_name=returned_name,
        effective_date=effective_date,
        payload=payload,
        raw_content=raw_content,
    )


def fetch_law_open_document(
    client: httpx.Client,
    *,
    api_key: str,
    target: str,
    name: str,
) -> LawOpenDocument:
    if target not in VALID_TARGETS:
        raise LawOpenApiError(f"unsupported law-open-data target: {target}")
    try:
        response = client.get(
            LAW_OPEN_ENDPOINT,
            params={"OC": api_key, "target": target, "type": "JSON", "LM": name},
        )
    except httpx.HTTPError as exc:
        raise LawOpenApiError("law-open-data transport failed") from exc
    if response.status_code != 200:
        raise LawOpenApiError(
            f"law-open-data returned HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise LawOpenApiError("law-open-data returned invalid JSON") from exc
    return parse_law_open_payload(
        payload,
        target=target,
        requested_name=name,
        raw_content=response.content,
    )
