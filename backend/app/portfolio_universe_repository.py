import json
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.engine.models import AccountType
from backend.app.ingestion.krx_client import parse_krx_etf_payload

DEFAULT_RETURN_ROOT = Path("data/cache/returns")
DEFAULT_KRX_ROOT = Path("data/raw/krx")
DEFAULT_ADJUSTED_PRICE_ROOT = Path("data/cache/kis/adjusted_prices")
HISTORY_OBSERVATIONS = 253
HISTORY_FILE_LOOKBACK = 330


class PortfolioUniverseRepository:
    def __init__(
        self,
        *,
        account_type: AccountType,
        products: list[dict[str, Any]],
        histories: dict[str, dict[date, Decimal]],
        history_sources: dict[str, str],
        as_of: date,
        source_path: Path,
    ) -> None:
        self.account_type = account_type
        self.products = products
        self.histories = histories
        self.history_sources = history_sources
        self.as_of = as_of
        self.source_path = source_path

    @classmethod
    def from_latest_cache(
        cls,
        account_type: AccountType,
        *,
        return_root: Path = DEFAULT_RETURN_ROOT,
        krx_root: Path = DEFAULT_KRX_ROOT,
        adjusted_price_root: Path = DEFAULT_ADJUSTED_PRICE_ROOT,
    ) -> "PortfolioUniverseRepository":
        paths = sorted(return_root.glob(f"{account_type.value}_etf_cost_return_*.json"))
        if not paths:
            raise FileNotFoundError(
                f"no cost-return master for account {account_type.value}"
            )
        source_path = paths[-1]
        report = json.loads(source_path.read_text(encoding="utf-8"))
        products = report.get("products")
        if not isinstance(products, list):
            raise ValueError("cost-return master must contain products")
        as_of = date.fromisoformat(str(report["as_of"]))
        codes = {
            product["isu_code"]
            for product in products
            if isinstance(product, dict) and isinstance(product.get("isu_code"), str)
        }
        histories = _load_adjusted_histories(adjusted_price_root, codes)
        history_sources = {code: "kis_adjusted_close" for code in histories}
        missing_codes = codes.difference(histories)
        if missing_codes:
            krx_histories = _load_recent_histories(krx_root, missing_codes)
            histories.update(krx_histories)
            history_sources.update(
                {code: "krx_close_fallback" for code in krx_histories}
            )
        return cls(
            account_type=account_type,
            products=products,
            histories=histories,
            history_sources=history_sources,
            as_of=as_of,
            source_path=source_path,
        )

    @property
    def history_source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for source in self.history_sources.values():
            counts[source] += 1
        return dict(sorted(counts.items()))


def _close(raw: str) -> Decimal | None:
    if raw in {"", "-"}:
        return None
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("KRX closing price is invalid") from exc
    return value if value.is_finite() and value > 0 else None


def _load_recent_histories(
    krx_root: Path, codes: set[str]
) -> dict[str, dict[date, Decimal]]:
    files = sorted((krx_root / "etf_bydd_trd").glob("*/*/*.json"))[
        -HISTORY_FILE_LOOKBACK:
    ]
    if not files:
        raise FileNotFoundError(f"no KRX ETF history under {krx_root}")
    histories: dict[str, deque[tuple[date, Decimal]]] = defaultdict(
        lambda: deque(maxlen=HISTORY_OBSERVATIONS)
    )
    for path in files:
        base_date = date.fromisoformat(
            f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        )
        response = parse_krx_etf_payload(
            json.loads(path.read_bytes()), base_date=base_date
        )
        for row in response.records:
            code = row["ISU_CD"]
            if code not in codes:
                continue
            close = _close(row["TDD_CLSPRC"])
            if close is not None:
                histories[code].append((base_date, close))
    return {code: dict(values) for code, values in histories.items()}


def _latest_adjusted_price_directory(root: Path) -> Path | None:
    candidates = (
        sorted(path for path in root.iterdir() if path.is_dir())
        if root.exists()
        else []
    )
    return candidates[-1] if candidates else None


def _load_adjusted_histories(
    adjusted_price_root: Path, codes: set[str]
) -> dict[str, dict[date, Decimal]]:
    source_root = _latest_adjusted_price_directory(adjusted_price_root)
    if source_root is None:
        return {}
    histories: dict[str, dict[date, Decimal]] = {}
    for code in sorted(codes):
        path = source_root / f"{code}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        price_policy = payload.get("price_policy")
        if (
            not isinstance(price_policy, dict)
            or price_policy.get("FID_ORG_ADJ_PRC") != "0"
        ):
            raise ValueError(f"KIS history is not adjusted-price data: {path}")
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise ValueError(f"KIS adjusted-price cache has no observations: {path}")
        parsed = []
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError(f"KIS adjusted-price row must be an object: {path}")
            value = _close(str(observation.get("adjusted_close") or ""))
            if value is None:
                continue
            parsed.append((date.fromisoformat(str(observation["date"])), value))
        if parsed:
            histories[code] = dict(sorted(parsed)[-HISTORY_OBSERVATIONS:])
    return histories
