import argparse
import json
from typing import Any

import httpx
import psycopg

from backend.app.settings import get_settings

from .fss_client import (
    PS_CORP_ENDPOINT,
    RP_CORP_ENDPOINT,
    FssApiError,
    fetch_fss_response,
    normalize_pension_savings,
    normalize_retirement,
)
from .fss_repository import (
    PS_SOURCE,
    RP_SOURCE,
    FssDisclosureRepository,
    FssRepositoryError,
    RunHandle,
)

_EXPECTED_INGESTION_ERRORS = (FssApiError, FssRepositoryError, psycopg.Error)


def _failure_result(error: Exception) -> dict[str, Any]:
    message = (
        "database operation failed" if isinstance(error, psycopg.Error) else str(error)
    )
    return {
        "outcome": "failed",
        "error_type": type(error).__name__,
        "error": message,
    }


def _record_failure(
    repository: FssDisclosureRepository | None,
    handle: RunHandle | None,
    error: Exception,
) -> bool:
    if repository is None or handle is None:
        return False
    try:
        repository.fail_run(handle.run_id, error)
    except psycopg.Error:
        return False
    return True


def run_live_ingestion(
    *,
    api_key: str,
    database_url: str | None,
    fetch_only: bool,
    ps_year: int,
    ps_quarter: int,
    rp_year: int,
    rp_quarter: int,
    rp_sys_type: int,
) -> dict[str, Any]:
    repository = None if fetch_only else FssDisclosureRepository(database_url or "")
    result: dict[str, Any] = {}
    endpoints: dict[str, dict[str, Any]] = {}

    with httpx.Client(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "pension-copilot-fss-ingestion/0.1"},
    ) as client:
        ps_params = {"year": ps_year, "quarter": ps_quarter}
        ps_handle = None
        try:
            ps_handle = (
                repository.start_run(PS_SOURCE, ps_params) if repository else None
            )
            ps_response = fetch_fss_response(
                client,
                endpoint=PS_CORP_ENDPOINT,
                api_key=api_key,
                request_params=ps_params,
            )
            ps_rows = normalize_pension_savings(ps_response)
            if repository and ps_handle:
                ps_upserted_count = repository.complete_pension_savings(
                    handle=ps_handle,
                    response=ps_response,
                    rows=ps_rows,
                    year=ps_year,
                    quarter=ps_quarter,
                )
            else:
                ps_upserted_count = 0
        except _EXPECTED_INGESTION_ERRORS as exc:
            endpoints["pension_savings"] = {
                "period": f"{ps_year}Q{ps_quarter}",
                **_failure_result(exc),
                "failure_recorded": _record_failure(repository, ps_handle, exc),
            }
        else:
            endpoints["pension_savings"] = {
                "outcome": "succeeded",
                "period": f"{ps_year}Q{ps_quarter}",
                "source_count": ps_response.source_count,
                "normalized_count": len(ps_rows),
                "upserted_count": ps_upserted_count,
            }
            result.update(
                {
                    "pension_savings_period": f"{ps_year}Q{ps_quarter}",
                    "pension_savings_source_count": ps_response.source_count,
                    "pension_savings_normalized_count": len(ps_rows),
                }
            )

        rp_params = {
            "year": rp_year,
            "quarter": rp_quarter,
            "sysType": rp_sys_type,
        }
        rp_handle = None
        try:
            rp_handle = (
                repository.start_run(RP_SOURCE, rp_params) if repository else None
            )
            rp_response = fetch_fss_response(
                client,
                endpoint=RP_CORP_ENDPOINT,
                api_key=api_key,
                request_params=rp_params,
            )
            rp_rows = normalize_retirement(rp_response)
            if repository and rp_handle:
                rp_upserted_count = repository.complete_retirement(
                    handle=rp_handle,
                    response=rp_response,
                    rows=rp_rows,
                    year=rp_year,
                    quarter=rp_quarter,
                    sys_type=rp_sys_type,
                )
            else:
                rp_upserted_count = 0
        except _EXPECTED_INGESTION_ERRORS as exc:
            endpoints["retirement"] = {
                "period": f"{rp_year}Q{rp_quarter}",
                "sys_type": rp_sys_type,
                **_failure_result(exc),
                "failure_recorded": _record_failure(repository, rp_handle, exc),
            }
        else:
            endpoints["retirement"] = {
                "outcome": "succeeded",
                "period": f"{rp_year}Q{rp_quarter}",
                "sys_type": rp_sys_type,
                "source_company_count": rp_response.source_count,
                "normalized_count": len(rp_rows),
                "upserted_count": rp_upserted_count,
            }
            result.update(
                {
                    "retirement_period": f"{rp_year}Q{rp_quarter}",
                    "retirement_sys_type": rp_sys_type,
                    "retirement_source_company_count": rp_response.source_count,
                    "retirement_normalized_count": len(rp_rows),
                }
            )

    endpoint_outcomes = [endpoint["outcome"] for endpoint in endpoints.values()]
    if all(outcome == "succeeded" for outcome in endpoint_outcomes):
        outcome = "succeeded"
    elif any(outcome == "succeeded" for outcome in endpoint_outcomes):
        outcome = "partial"
    else:
        outcome = "failed"
    result.update(
        {
            "database": (
                "not_requested"
                if fetch_only
                else "loaded"
                if outcome == "succeeded"
                else outcome
            ),
            "outcome": outcome,
            "endpoints": endpoints,
        }
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Call the FSS OpenAPI directly and optionally upsert disclosure rows."
        )
    )
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--ps-year", type=int, default=2025)
    parser.add_argument("--ps-quarter", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--rp-year", type=int, default=2026)
    parser.add_argument("--rp-quarter", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--rp-sys-type", type=int, choices=range(1, 6), default=3)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.pension_portal_api_key is None:
        raise SystemExit("PENSION_PORTAL_API_KEY is required")
    api_key = settings.pension_portal_api_key.get_secret_value().strip()
    if not api_key:
        raise SystemExit("PENSION_PORTAL_API_KEY is required")

    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else None
    )
    if not args.fetch_only and not database_url:
        raise SystemExit("DATABASE_URL is required unless --fetch-only is used")

    result = run_live_ingestion(
        api_key=api_key,
        database_url=database_url,
        fetch_only=args.fetch_only,
        ps_year=args.ps_year,
        ps_quarter=args.ps_quarter,
        rp_year=args.rp_year,
        rp_quarter=args.rp_quarter,
        rp_sys_type=args.rp_sys_type,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
