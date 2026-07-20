import json
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.engine.models import AccountType
from backend.app.ingestion.krx_client import parse_krx_etf_payload

DEFAULT_RETURN_ROOT = Path("data/cache/returns")
DEFAULT_KRX_ROOT = Path("data/raw/krx")
DEFAULT_ADJUSTED_PRICE_ROOT = Path("data/cache/kis/adjusted_prices")
DEFAULT_EVENT_ROOT = Path("data/cache/events")
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
        historical_history_loader: Callable[
            [set[str]],
            tuple[dict[str, dict[date, Decimal]], dict[str, str]],
        ]
        | None = None,
    ) -> None:
        self.account_type = account_type
        self.products = products
        self.histories = histories
        self.history_sources = history_sources
        self.as_of = as_of
        self.latest_history_as_of = max(
            (max(history) for history in histories.values() if history),
            default=as_of,
        )
        self.score_cache: dict[
            tuple[str, tuple[str, ...]], list[tuple[dict[str, Any], Any]]
        ] = {}
        self.source_path = source_path
        self._historical_history_loader = historical_history_loader

    def load_total_return_histories(
        self, isu_codes: set[str]
    ) -> tuple[dict[str, dict[date, Decimal]], dict[str, str]]:
        """Load full verified histories only for the requested ETF codes."""

        requested = set(isu_codes)
        histories: dict[str, dict[date, Decimal]] = {}
        sources: dict[str, str] = {}
        if self._historical_history_loader is not None:
            histories, sources = self._historical_history_loader(requested)
        for code in requested.difference(histories):
            if code in self.histories:
                histories[code] = self.histories[code]
                if code in self.history_sources:
                    sources[code] = self.history_sources[code]
        return histories, sources

    @classmethod
    def from_latest_cache(
        cls,
        account_type: AccountType,
        *,
        return_root: Path = DEFAULT_RETURN_ROOT,
        krx_root: Path = DEFAULT_KRX_ROOT,
        adjusted_price_root: Path = DEFAULT_ADJUSTED_PRICE_ROOT,
        event_root: Path = DEFAULT_EVENT_ROOT,
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
        histories, total_return_codes = _load_adjusted_histories(
            adjusted_price_root,
            codes,
            event_root=event_root,
        )
        history_sources = {
            code: (
                "kis_adjusted_close_plus_kind_cash_distribution"
                if code in total_return_codes
                else "kis_adjusted_close"
            )
            for code in histories
        }
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
            historical_history_loader=lambda requested_codes: (
                _load_historical_total_return_histories(
                    adjusted_price_root,
                    requested_codes,
                    event_root=event_root,
                )
            ),
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


def _cash_distributions_by_code(
    event_root: Path,
    codes: set[str],
) -> tuple[dict[str, dict[date, Decimal]], date | None, date | None]:
    paths = sorted(event_root.glob("etf_corporate_events_*.json"))
    if not paths:
        return {}, None, None
    payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("ETF corporate-event cache must contain events")
    coverage_start = payload.get("kind_distribution_coverage_start")
    coverage_end = payload.get("kind_distribution_coverage_end")
    if not coverage_start or not coverage_end:
        source_files = payload.get("source_files")
        distribution_path = (
            Path(str(source_files.get("kind_distributions")))
            if isinstance(source_files, dict) and source_files.get("kind_distributions")
            else None
        )
        if distribution_path is not None and distribution_path.exists():
            distribution_report = json.loads(
                distribution_path.read_text(encoding="utf-8")
            )
            coverage_start = distribution_report.get("coverage_start")
            coverage_end = distribution_report.get("coverage_end")
    distributions: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for event in events:
        if (
            not isinstance(event, dict)
            or event.get("event_type") != "cash_distribution"
            or event.get("status") != "confirmed_cash_flow"
            or event.get("isu_code") not in codes
        ):
            continue
        amount = _close(str(event.get("cash_per_share_krw") or ""))
        if amount is None:
            continue
        effective_date = date.fromisoformat(str(event["effective_date"]))
        code = str(event["isu_code"])
        distributions[code][effective_date] = (
            distributions[code].get(effective_date, Decimal("0")) + amount
        )
    return (
        dict(distributions),
        date.fromisoformat(str(coverage_start)) if coverage_start else None,
        date.fromisoformat(str(coverage_end)) if coverage_end else None,
    )


def _total_return_history(
    prices: list[tuple[date, Decimal]],
    distributions: dict[date, Decimal],
    *,
    observation_limit: int | None = HISTORY_OBSERVATIONS,
) -> dict[date, Decimal]:
    ordered = sorted(prices)
    selected = ordered[-observation_limit:] if observation_limit else ordered
    if not selected:
        return {}
    index_value = Decimal("100")
    history = {selected[0][0]: index_value}
    previous_price = selected[0][1]
    for observed_on, price in selected[1:]:
        distribution = distributions.get(observed_on, Decimal("0"))
        index_value *= (price + distribution) / previous_price
        history[observed_on] = index_value
        previous_price = price
    return history


def _load_adjusted_histories(
    adjusted_price_root: Path,
    codes: set[str],
    *,
    event_root: Path,
    observation_limit: int | None = HISTORY_OBSERVATIONS,
) -> tuple[dict[str, dict[date, Decimal]], set[str]]:
    source_root = _latest_adjusted_price_directory(adjusted_price_root)
    if source_root is None:
        return {}, set()
    distributions_by_code, distribution_start, distribution_end = (
        _cash_distributions_by_code(event_root, codes)
    )
    histories: dict[str, dict[date, Decimal]] = {}
    total_return_codes: set[str] = set()
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
            observed_on = date.fromisoformat(str(observation["date"]))
            if (
                distribution_start is not None
                and distribution_end is not None
                and not distribution_start <= observed_on <= distribution_end
            ):
                continue
            parsed.append((observed_on, value))
        if parsed:
            histories[code] = _total_return_history(
                parsed,
                distributions_by_code.get(code, {}),
                observation_limit=observation_limit,
            )
            if (
                distribution_start is not None
                and distribution_end is not None
            ) or code in distributions_by_code:
                total_return_codes.add(code)
    return histories, total_return_codes


def _load_historical_total_return_histories(
    adjusted_price_root: Path,
    codes: set[str],
    *,
    event_root: Path,
) -> tuple[dict[str, dict[date, Decimal]], dict[str, str]]:
    histories, total_return_codes = _load_adjusted_histories(
        adjusted_price_root,
        codes,
        event_root=event_root,
        observation_limit=None,
    )
    return histories, {
        code: (
            "kis_adjusted_close_plus_kind_cash_distribution"
            if code in total_return_codes
            else "kis_adjusted_close"
        )
        for code in histories
    }
