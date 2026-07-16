import argparse
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import get_settings

from .kis_client import (
    KIS_BASE_URL,
    KIS_COMPONENT_ENDPOINT,
    KIS_PRICE_ENDPOINT,
    KisApiError,
    KisApiResponse,
    fetch_etf_components,
    fetch_etf_price,
    issue_access_token,
)

DEFAULT_KRX_CACHE_ROOT = Path("data/cache/krx")
DEFAULT_RAW_ROOT = Path("data/raw/kis")
DEFAULT_CACHE_ROOT = Path("data/cache/kis")
MAX_RETRIES = 3


@dataclass(frozen=True, slots=True)
class KisCollectionRecord:
    isu_code: str
    isu_name: str
    status: str
    component_count: int
    component_sha256: str | None
    price_sha256: str | None
    retrieved_at: str | None
    error: str | None = None


def _latest_krx_report(cache_root: Path) -> Path:
    candidates = sorted(cache_root.glob("etf_market_evidence_*.json"))
    if not candidates:
        raise FileNotFoundError(f"no KRX ETF report found under {cache_root}")
    return candidates[-1]


def load_krx_etf_universe(path: Path) -> tuple[str, list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        raise ValueError("KRX ETF report must contain a products array")
    as_of = payload.get("as_of")
    if not isinstance(as_of, str):
        raise ValueError("KRX ETF report must contain as_of")
    products: list[dict[str, str]] = []
    for position, product in enumerate(payload["products"]):
        if not isinstance(product, dict):
            raise ValueError(f"KRX ETF product {position} must be an object")
        code = product.get("isu_code")
        name = product.get("isu_name")
        if not isinstance(code, str) or not code:
            raise ValueError(f"KRX ETF product {position} has no isu_code")
        if not isinstance(name, str):
            raise ValueError(f"KRX ETF product {position} has no isu_name")
        products.append({"isu_code": code, "isu_name": name})
    if payload.get("product_count") != len(products):
        raise ValueError("KRX ETF report product_count does not match products")
    if len({item["isu_code"] for item in products}) != len(products):
        raise ValueError("KRX ETF report contains duplicate isu_code values")
    return as_of, products


def _raw_path(root: Path, endpoint_name: str, snapshot_date: date, code: str) -> Path:
    return root / endpoint_name / f"{snapshot_date:%Y-%m-%d}" / f"{code}.json"


def _write_raw(path: Path, response: KisApiResponse) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(response.raw_content)
    temporary.replace(path)
    return hashlib.sha256(response.raw_content).hexdigest()


def _load_payload(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("rt_cd") != "0":
        raise ValueError(f"invalid cached KIS response: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def _fetch_with_retry(fetch: Callable[[], KisApiResponse]) -> KisApiResponse:
    last_error: KisApiError | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fetch()
        except KisApiError as exc:
            last_error = exc
            if not exc.retryable or attempt == MAX_RETRIES:
                break
            time.sleep(2**attempt)
    if last_error is None:
        raise RuntimeError("KIS retry loop completed without a result")
    raise last_error


def _normalize_product(
    product: dict[str, str],
    component_payload: dict[str, Any],
    price_payload: dict[str, Any],
) -> dict[str, Any]:
    components = component_payload.get("output2")
    component_summary = component_payload.get("output1")
    price = price_payload.get("output")
    if not isinstance(components, list) or not isinstance(component_summary, dict):
        raise ValueError("cached KIS component response has an invalid schema")
    if not isinstance(price, dict):
        raise ValueError("cached KIS price response has an invalid schema")
    warnings: list[str] = []
    if not components:
        warnings.append("kis_component_list_empty")
    return {
        **product,
        "component_count": len(components),
        "component_summary": component_summary,
        "components": components,
        "price": price,
        "warnings": warnings,
    }


def collect_kis_etf_snapshot(
    *,
    app_key: str,
    app_secret: str,
    krx_report_path: Path,
    raw_root: Path,
    cache_root: Path,
    snapshot_date: date,
    delay_seconds: float,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if delay_seconds < 0:
        raise ValueError("delay-seconds must not be negative")
    krx_as_of, products = load_krx_etf_universe(krx_report_path)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        products = products[:limit]

    pending = []
    normalized_products: list[dict[str, Any]] = []
    records: list[KisCollectionRecord] = []
    for product in products:
        code = product["isu_code"]
        component_path = _raw_path(raw_root, "components", snapshot_date, code)
        price_path = _raw_path(raw_root, "price", snapshot_date, code)
        if component_path.exists() and price_path.exists() and not force:
            try:
                component_payload, component_hash = _load_payload(component_path)
                price_payload, price_hash = _load_payload(price_path)
                normalized = _normalize_product(
                    product, component_payload, price_payload
                )
                normalized_products.append(normalized)
                records.append(
                    KisCollectionRecord(
                        isu_code=code,
                        isu_name=product["isu_name"],
                        status="skipped_existing",
                        component_count=normalized["component_count"],
                        component_sha256=component_hash,
                        price_sha256=price_hash,
                        retrieved_at=None,
                    )
                )
                continue
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        pending.append(product)

    if pending:
        timeout = httpx.Timeout(30.0)
        with httpx.Client(
            base_url=KIS_BASE_URL,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "pension-copilot-kis/0.1",
            },
        ) as client:
            token = issue_access_token(
                client, app_key=app_key, app_secret=app_secret
            )
            for position, product in enumerate(pending, start=1):
                code = product["isu_code"]
                try:
                    component_response = _fetch_with_retry(
                        lambda code=code: fetch_etf_components(
                            client,
                            app_key=app_key,
                            app_secret=app_secret,
                            access_token=token.value,
                            isu_code=code,
                        )
                    )
                    if delay_seconds:
                        time.sleep(delay_seconds)
                    price_response = _fetch_with_retry(
                        lambda code=code: fetch_etf_price(
                            client,
                            app_key=app_key,
                            app_secret=app_secret,
                            access_token=token.value,
                            isu_code=code,
                        )
                    )
                    component_hash = _write_raw(
                        _raw_path(raw_root, "components", snapshot_date, code),
                        component_response,
                    )
                    price_hash = _write_raw(
                        _raw_path(raw_root, "price", snapshot_date, code),
                        price_response,
                    )
                    normalized = _normalize_product(
                        product,
                        component_response.payload,
                        price_response.payload,
                    )
                    normalized_products.append(normalized)
                    records.append(
                        KisCollectionRecord(
                            isu_code=code,
                            isu_name=product["isu_name"],
                            status="fetched",
                            component_count=normalized["component_count"],
                            component_sha256=component_hash,
                            price_sha256=price_hash,
                            retrieved_at=datetime.now(UTC).isoformat(),
                        )
                    )
                except KisApiError as exc:
                    records.append(
                        KisCollectionRecord(
                            isu_code=code,
                            isu_name=product["isu_name"],
                            status="failed",
                            component_count=0,
                            component_sha256=None,
                            price_sha256=None,
                            retrieved_at=datetime.now(UTC).isoformat(),
                            error=str(exc),
                        )
                    )
                if delay_seconds:
                    time.sleep(delay_seconds)
                if position % 25 == 0 or position == len(pending):
                    print(
                        json.dumps(
                            {
                                "completed": position,
                                "pending_total": len(pending),
                                "last_code": code,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )

    records.sort(key=lambda item: item.isu_code)
    normalized_products.sort(key=lambda item: item["isu_code"])
    generated_at = datetime.now(UTC).isoformat()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / f"etf_snapshot_{snapshot_date:%Y-%m-%d}.json"
    normalized_output = {
        "source": "Korea Investment & Securities Open Trading API",
        "krx_universe_as_of": krx_as_of,
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "requested_product_count": len(products),
        "product_count": len(normalized_products),
        "empty_component_product_count": sum(
            item["component_count"] == 0 for item in normalized_products
        ),
        "failed_product_count": sum(item.status == "failed" for item in records),
        "endpoints": {
            "components": KIS_COMPONENT_ENDPOINT,
            "price": KIS_PRICE_ENDPOINT,
        },
        "limitations": [
            "KIS public quotation data does not prove pension-account eligibility",
            "product fees and distribution history require separate verified sources",
            "empty component arrays are preserved and excluded from overlap "
            "calculations",
        ],
        "products": normalized_products,
    }
    temporary = cache_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(normalized_output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(cache_path)

    manifest_root = raw_root / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / f"etf_snapshot_{snapshot_date:%Y-%m-%d}.json"
    manifest = {
        "source": normalized_output["source"],
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "krx_report_path": krx_report_path.as_posix(),
        "requested_product_count": len(products),
        "fetched": sum(item.status == "fetched" for item in records),
        "skipped_existing": sum(
            item.status == "skipped_existing" for item in records
        ),
        "failed": sum(item.status == "failed" for item in records),
        "records": [asdict(item) for item in records],
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return {
        **{key: value for key, value in normalized_output.items() if key != "products"},
        "cache_path": cache_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect KIS ETF components and current price for the KRX universe."
    )
    parser.add_argument("--krx-report", type=Path)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache-output", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--snapshot-date", type=date.fromisoformat, default=date.today()
    )
    parser.add_argument("--delay-seconds", type=float, default=0.12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.kis_app_key is None or settings.kis_app_secret is None:
        raise SystemExit("KIS_APP_KEY and KIS_APP_SECRET are required")
    app_key = settings.kis_app_key.get_secret_value().strip()
    app_secret = settings.kis_app_secret.get_secret_value().strip()
    if not app_key or not app_secret:
        raise SystemExit("KIS_APP_KEY and KIS_APP_SECRET are required")
    krx_report = args.krx_report or _latest_krx_report(DEFAULT_KRX_CACHE_ROOT)
    result = collect_kis_etf_snapshot(
        app_key=app_key,
        app_secret=app_secret,
        krx_report_path=krx_report,
        raw_root=args.raw_output,
        cache_root=args.cache_output,
        snapshot_date=args.snapshot_date,
        delay_seconds=args.delay_seconds,
        limit=args.limit,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result["failed_product_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
