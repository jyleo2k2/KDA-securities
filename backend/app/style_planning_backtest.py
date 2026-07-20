"""Point-in-time rolling-vintage calibration for ETF style planning returns."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from pathlib import Path
from statistics import median
from typing import Any

from backend.app.engine.educational_portfolio import _cma_mapping
from backend.app.engine.style_planning_return import (
    HISTORICAL_WEIGHTS,
    style_macro_sensitivities,
)
from backend.app.etf_style_planning_report import _group_keys, _region_bucket

ENGINE_NAME = "etf_style_planning_rolling_vintage_backtest"
ENGINE_VERSION = "2026-07-20.1"
POLICY_VERSION = "style-planning-backtest-2026-07-20.1"
PERCENT_QUANTUM = Decimal("0.0001")
HORIZON_DAYS = 365
MAX_TRADING_DATE_GAP_DAYS = 7
PREFERRED_MINIMUM_PEERS = 5
PERIOD_OBSERVATIONS = {"5y": 1260, "3y": 756, "1y": 252}
SUPPORTED_CMA_CODES = {
    "us_large_cap_equity",
    "global_equity",
    "emerging_markets_equity",
}

DEFAULT_RETURN_ROOT = Path("data/cache/returns")
DEFAULT_ADJUSTED_PRICE_ROOT = Path("data/cache/kis/adjusted_prices")
DEFAULT_EVENT_ROOT = Path("data/cache/events")
DEFAULT_VINTAGE_PATH = Path(
    "data/reference/style_planning_backtest_vintages_2022-2024.json"
)
DEFAULT_OUTPUT_ROOT = Path("data/cache/planning_returns")

HISTORY_SCALES = tuple(
    Decimal(value)
    for value in ("0", ".25", ".5", ".75", "1", "1.25", "1.5")
)
HISTORY_CAPS = tuple(Decimal(value) for value in (".25", ".5", ".75", "1"))
MACRO_SCALES = tuple(Decimal(value) for value in ("0", ".5", "1", "1.5"))
MACRO_CAPS = (Decimal(".25"), Decimal(".5"))
CURRENT_POLICY_PARAMETERS = {
    "history_scale": Decimal("1"),
    "history_cap_percent_point": Decimal("1"),
    "macro_scale": Decimal("1"),
    "macro_cap_percent_point": Decimal(".5"),
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _latest_file(root: Path, pattern: str) -> Path:
    paths = sorted(root.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No matching cache under {root}: {pattern}")
    return paths[-1]


def _latest_directory(root: Path) -> Path:
    paths = sorted(path for path in root.iterdir() if path.is_dir())
    if not paths:
        raise FileNotFoundError(f"No dated cache directory under {root}")
    return paths[-1]


def _decimal(value: Any, *, positive: bool = False) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or (positive and parsed <= 0):
        return None
    return parsed


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, limit: Decimal) -> Decimal:
    return max(-limit, min(limit, value))


def _load_distributions(event_path: Path) -> dict[str, dict[date, Decimal]]:
    payload = _load(event_path)
    result: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for event in payload.get("events") or []:
        if (
            not isinstance(event, dict)
            or event.get("event_type") != "cash_distribution"
            or event.get("status") != "confirmed_cash_flow"
        ):
            continue
        amount = _decimal(event.get("cash_per_share_krw"), positive=True)
        code = event.get("isu_code")
        effective_date = event.get("effective_date")
        if amount is None or not isinstance(code, str) or not effective_date:
            continue
        observed_on = date.fromisoformat(str(effective_date))
        result[code][observed_on] = (
            result[code].get(observed_on, Decimal("0")) + amount
        )
    return dict(result)


def _total_return_series(
    path: Path, distributions: dict[date, Decimal]
) -> tuple[list[date], list[Decimal]]:
    payload = _load(path)
    policy = payload.get("price_policy") or {}
    if policy.get("FID_ORG_ADJ_PRC") != "0":
        raise ValueError(f"KIS history is not adjusted-price data: {path}")
    observations = []
    for row in payload.get("observations") or []:
        if not isinstance(row, dict):
            continue
        close = _decimal(row.get("adjusted_close"), positive=True)
        if close is not None:
            observations.append((date.fromisoformat(str(row["date"])), close))
    observations.sort()
    if not observations:
        return [], []

    distribution_by_trading_date: dict[date, Decimal] = defaultdict(Decimal)
    trading_dates = [item[0] for item in observations]
    for effective_date, amount in distributions.items():
        index = bisect_left(trading_dates, effective_date)
        if index < len(trading_dates):
            distribution_by_trading_date[trading_dates[index]] += amount

    index_value = Decimal("100")
    index_values = [index_value]
    previous_close = observations[0][1]
    for observed_on, close in observations[1:]:
        cash = distribution_by_trading_date.get(observed_on, Decimal("0"))
        index_value *= (close + cash) / previous_close
        index_values.append(index_value)
        previous_close = close
    return trading_dates, index_values


def _load_series(
    adjusted_price_directory: Path,
    codes: set[str],
    distributions: dict[str, dict[date, Decimal]],
) -> dict[str, tuple[list[date], list[Decimal]]]:
    result = {}
    for code in sorted(codes):
        path = adjusted_price_directory / f"{code}.json"
        if not path.exists():
            continue
        dates, values = _total_return_series(path, distributions.get(code, {}))
        if dates:
            result[code] = (dates, values)
    return result


def _annualized_return(
    series: tuple[list[date], list[Decimal]],
    *,
    formation_date: date,
    periods: int,
) -> Decimal | None:
    dates, values = series
    end_index = bisect_left(dates, formation_date) - 1
    start_index = end_index - periods
    if start_index < 0:
        return None
    growth = values[end_index] / values[start_index]
    if growth <= 0:
        return None
    with localcontext() as context:
        context.prec = 28
        years = Decimal(periods) / Decimal("252")
        return ((growth.ln() / years).exp() - Decimal("1")) * Decimal("100")


def _forward_return(
    series: tuple[list[date], list[Decimal]], formation_date: date
) -> tuple[date, date, Decimal] | None:
    dates, values = series
    if not dates or dates[0] >= formation_date:
        return None
    start_index = bisect_right(dates, formation_date)
    if start_index >= len(dates):
        return None
    start_date = dates[start_index]
    if (start_date - formation_date).days > MAX_TRADING_DATE_GAP_DAYS:
        return None
    target_date = start_date + timedelta(days=HORIZON_DAYS)
    end_index = bisect_left(dates, target_date)
    if end_index >= len(dates):
        return None
    end_date = dates[end_index]
    if (end_date - target_date).days > MAX_TRADING_DATE_GAP_DAYS:
        return None
    realized = (values[end_index] / values[start_index] - Decimal("1")) * Decimal(
        "100"
    )
    return start_date, end_date, realized


def _history_by_code(
    products: list[dict[str, Any]],
    series_by_code: dict[str, tuple[list[date], list[Decimal]]],
    formation_date: date,
) -> dict[str, dict[str, Decimal]]:
    result: dict[str, dict[str, Decimal]] = {}
    for product in products:
        code = str(product.get("isu_code") or "")
        series = series_by_code.get(code)
        if series is None:
            continue
        periods = {}
        for label, observation_count in PERIOD_OBSERVATIONS.items():
            value = _annualized_return(
                series,
                formation_date=formation_date,
                periods=observation_count,
            )
            if value is not None:
                periods[label] = value
        if periods:
            result[code] = periods
    return result


def _history_pools(
    products: list[dict[str, Any]], history_by_code: dict[str, dict[str, Decimal]]
) -> dict[tuple[str, str], list[Decimal]]:
    pools: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for product in products:
        code = str(product.get("isu_code") or "")
        classification = product.get("classification") or {}
        for period, value in history_by_code.get(code, {}).items():
            for key in _group_keys(classification):
                pools[(key, period)].append(value)
    return pools


def _peer_history(
    classification: dict[str, Any],
    pools: dict[tuple[str, str], list[Decimal]],
) -> tuple[str, str, list[Decimal]] | None:
    keys = _group_keys(classification)
    for period in PERIOD_OBSERVATIONS:
        for key in keys:
            values = pools.get((key, period), [])
            if len(values) >= PREFERRED_MINIMUM_PEERS:
                return key, period, values
    for period in reversed(PERIOD_OBSERVATIONS):
        candidates = [
            (key, pools.get((key, period), []))
            for key in keys
            if pools.get((key, period))
        ]
        if candidates:
            key, values = max(candidates, key=lambda item: len(item[1]))
            return key, period, values
    return None


def _macro_raw(
    classification: dict[str, Any], vintage: dict[str, Any]
) -> tuple[str, Decimal, list[str]]:
    region = _region_bucket(str(classification.get("region") or "global"))
    signal = vintage["regional_revision_signals"][region]
    sensitivities = style_macro_sensitivities(
        asset_class=str(classification.get("asset_class") or "unknown"),
        strategy=str(classification.get("strategy") or "unspecified"),
    )
    raw = (
        Decimal(signal["growth_revision_percent_point"]) * sensitivities.growth
        + Decimal(signal["inflation_revision_percent_point"])
        * sensitivities.inflation
        + Decimal(signal["policy_rate_revision_percent_point"])
        * sensitivities.policy_rate
    )
    return region, raw, list(signal.get("missing_signal_ids") or [])


def _eligible_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for product in products:
        classification = product.get("classification") or {}
        if classification.get("asset_class") != "equity":
            continue
        if classification.get("leverage_type", "normal") != "normal":
            continue
        try:
            cma_code, _, _ = _cma_mapping(classification)
        except ValueError:
            continue
        if cma_code in SUPPORTED_CMA_CODES:
            result.append(product)
    return result


def _build_raw_rows(
    *,
    products: list[dict[str, Any]],
    series_by_code: dict[str, tuple[list[date], list[Decimal]]],
    vintages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows = []
    excluded = []
    for vintage in vintages:
        formation_date = date.fromisoformat(vintage["formation_date"])
        history_by_code = _history_by_code(products, series_by_code, formation_date)
        pools = _history_pools(products, history_by_code)
        for product in products:
            code = str(product.get("isu_code") or "")
            classification = product.get("classification") or {}
            series = series_by_code.get(code)
            if series is None:
                excluded.append(
                    {
                        "vintage_id": vintage["vintage_id"],
                        "isu_code": code,
                        "reason": "adjusted_price_series_missing",
                    }
                )
                continue
            realized = _forward_return(series, formation_date)
            if realized is None:
                excluded.append(
                    {
                        "vintage_id": vintage["vintage_id"],
                        "isu_code": code,
                        "reason": "complete_12m_forward_window_missing",
                    }
                )
                continue
            peer = _peer_history(classification, pools)
            if peer is None:
                excluded.append(
                    {
                        "vintage_id": vintage["vintage_id"],
                        "isu_code": code,
                        "reason": "point_in_time_style_history_missing",
                    }
                )
                continue
            cma_code, proxy_used, mapping_warnings = _cma_mapping(classification)
            cma_percent = Decimal(vintage["cma_percent"][cma_code])
            peer_key, historical_period, history_values = peer
            historical_percent = median(history_values)
            region, macro_raw, missing_signals = _macro_raw(
                classification, vintage
            )
            start_date, end_date, realized_percent = realized
            rows.append(
                {
                    "vintage_id": vintage["vintage_id"],
                    "split": vintage["split"],
                    "formation_date": formation_date,
                    "forward_start_date": start_date,
                    "forward_end_date": end_date,
                    "isu_code": code,
                    "isu_name": product.get("isu_name"),
                    "classification_style_key": _group_keys(classification)[0],
                    "history_peer_key": peer_key,
                    "asset_class": classification.get("asset_class"),
                    "strategy": classification.get("strategy"),
                    "region": classification.get("region"),
                    "macro_region": region,
                    "cma_assumption_code": cma_code,
                    "cma_proxy_used": proxy_used,
                    "cma_percent": cma_percent,
                    "historical_period": historical_period,
                    "historical_peer_count": len(history_values),
                    "historical_annualized_return_percent": historical_percent,
                    "historical_gap_percent_point": historical_percent - cma_percent,
                    "base_historical_weight": HISTORICAL_WEIGHTS[
                        historical_period
                    ],
                    "macro_raw_adjustment_percent_point": macro_raw,
                    "missing_macro_signal_ids": missing_signals,
                    "realized_12m_total_return_percent": realized_percent,
                    "warnings": mapping_warnings,
                }
            )
    return rows, excluded


def _prediction(
    row: dict[str, Any],
    *,
    history_scale: Decimal,
    history_cap: Decimal,
    macro_scale: Decimal,
    macro_cap: Decimal,
) -> Decimal:
    history_adjustment = _clamp(
        row["historical_gap_percent_point"]
        * row["base_historical_weight"]
        * history_scale,
        history_cap,
    )
    macro_adjustment = _clamp(
        row["macro_raw_adjustment_percent_point"] * macro_scale,
        macro_cap,
    )
    return row["cma_percent"] + history_adjustment + macro_adjustment


def _style_vintage_points(
    rows: list[dict[str, Any]], predictions: list[Decimal]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for row, prediction in zip(rows, predictions, strict=True):
        key = (row["vintage_id"], row["classification_style_key"])
        grouped[key].append(
            (prediction, row["realized_12m_total_return_percent"])
        )
    points = []
    for (vintage_id, style_key), values in sorted(grouped.items()):
        points.append(
            {
                "vintage_id": vintage_id,
                "style_key": style_key,
                "etf_count": len(values),
                "prediction_percent": median(item[0] for item in values),
                "realized_percent": median(item[1] for item in values),
            }
        )
    return points


def _metrics(actual: list[Decimal], predicted: list[Decimal]) -> dict[str, Any]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("metrics require paired non-empty observations")
    errors = [
        prediction - outcome
        for prediction, outcome in zip(predicted, actual, strict=True)
    ]
    absolute_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    count = Decimal(len(errors))
    return {
        "observation_count": len(errors),
        "mae_percent_point": _percent(sum(absolute_errors) / count),
        "rmse_percent_point": _percent((sum(squared_errors) / count).sqrt()),
        "mean_bias_percent_point": _percent(sum(errors) / count),
        "median_absolute_error_percent_point": _percent(median(absolute_errors)),
    }


def _evaluation(
    rows: list[dict[str, Any]], predictions: list[Decimal]
) -> dict[str, Any]:
    actual = [row["realized_12m_total_return_percent"] for row in rows]
    style_points = _style_vintage_points(rows, predictions)
    return {
        "etf_level": _metrics(actual, predictions),
        "style_vintage_level": _metrics(
            [point["realized_percent"] for point in style_points],
            [point["prediction_percent"] for point in style_points],
        ),
        "style_vintage_points": style_points,
    }


def _parameter_payload(
    history_scale: Decimal,
    history_cap: Decimal,
    macro_scale: Decimal,
    macro_cap: Decimal,
) -> dict[str, Decimal]:
    return {
        "history_scale": history_scale,
        "history_cap_percent_point": history_cap,
        "macro_scale": macro_scale,
        "macro_cap_percent_point": macro_cap,
    }


def _tune(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    best_key = None
    best_parameters = None
    for history_scale in HISTORY_SCALES:
        for history_cap in HISTORY_CAPS:
            for macro_scale in MACRO_SCALES:
                for macro_cap in MACRO_CAPS:
                    predictions = [
                        _prediction(
                            row,
                            history_scale=history_scale,
                            history_cap=history_cap,
                            macro_scale=macro_scale,
                            macro_cap=macro_cap,
                        )
                        for row in rows
                    ]
                    metrics = _evaluation(rows, predictions)[
                        "style_vintage_level"
                    ]
                    key = (
                        metrics["mae_percent_point"],
                        metrics["rmse_percent_point"],
                        history_scale,
                        macro_scale,
                        history_cap,
                        macro_cap,
                    )
                    if best_key is None or key < best_key:
                        best_key = key
                        best_parameters = _parameter_payload(
                            history_scale,
                            history_cap,
                            macro_scale,
                            macro_cap,
                        )
    if best_parameters is None:
        raise ValueError("parameter grid produced no candidate")
    return best_parameters


def _predict_model(
    rows: list[dict[str, Any]],
    parameters: dict[str, Decimal],
    *,
    history: bool,
    macro: bool,
) -> list[Decimal]:
    return [
        _prediction(
            row,
            history_scale=(parameters["history_scale"] if history else Decimal("0")),
            history_cap=parameters["history_cap_percent_point"],
            macro_scale=(parameters["macro_scale"] if macro else Decimal("0")),
            macro_cap=parameters["macro_cap_percent_point"],
        )
        for row in rows
    ]


def _model_comparison(
    rows: list[dict[str, Any]], parameters: dict[str, Decimal]
) -> dict[str, Any]:
    splits = {
        "training": [row for row in rows if row["split"] == "training"],
        "holdout": [row for row in rows if row["split"] == "holdout"],
        "all": rows,
    }
    result = {}
    for split, split_rows in splits.items():
        if not split_rows:
            raise ValueError(f"backtest split is empty: {split}")
        result[split] = {
            "cma_only": _evaluation(
                split_rows, [row["cma_percent"] for row in split_rows]
            ),
            "history_only": _evaluation(
                split_rows,
                _predict_model(split_rows, parameters, history=True, macro=False),
            ),
            "macro_only": _evaluation(
                split_rows,
                _predict_model(split_rows, parameters, history=False, macro=True),
            ),
            "combined": _evaluation(
                split_rows,
                _predict_model(split_rows, parameters, history=True, macro=True),
            ),
            "current_policy_combined": _evaluation(
                split_rows,
                _predict_model(
                    split_rows,
                    CURRENT_POLICY_PARAMETERS,
                    history=True,
                    macro=True,
                ),
            ),
        }
    return result


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(_percent(value), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def build_rolling_vintage_backtest(
    *,
    return_master_path: Path,
    adjusted_price_directory: Path,
    event_path: Path,
    vintage_path: Path,
) -> dict[str, Any]:
    master = _load(return_master_path)
    vintage_payload = _load(vintage_path)
    products = _eligible_products(list(master.get("products") or []))
    codes = {str(product.get("isu_code") or "") for product in products}
    distributions = _load_distributions(event_path)
    series_by_code = _load_series(
        adjusted_price_directory,
        codes,
        distributions,
    )
    rows, excluded = _build_raw_rows(
        products=products,
        series_by_code=series_by_code,
        vintages=list(vintage_payload.get("vintages") or []),
    )
    training_rows = [row for row in rows if row["split"] == "training"]
    if not training_rows:
        raise ValueError("rolling-vintage backtest has no training rows")
    selected_parameters = _tune(training_rows)
    comparisons = _model_comparison(rows, selected_parameters)
    holdout = comparisons["holdout"]
    cma_metrics = holdout["cma_only"]["style_vintage_level"]
    combined_metrics = holdout["combined"]["style_vintage_level"]
    row_count = holdout["combined"]["etf_level"]["observation_count"]
    style_count = combined_metrics["observation_count"]
    mae_improved = (
        combined_metrics["mae_percent_point"] < cma_metrics["mae_percent_point"]
    )
    rmse_improved = (
        combined_metrics["rmse_percent_point"] < cma_metrics["rmse_percent_point"]
    )
    coverage_sufficient = row_count >= 100 and style_count >= 10
    short_horizon_gate_passed = mae_improved and rmse_improved and coverage_sufficient

    predictions = _predict_model(rows, selected_parameters, history=True, macro=True)
    result_rows = []
    for row, prediction in zip(rows, predictions, strict=True):
        result_rows.append(
            {
                **row,
                "cma_only_percent": row["cma_percent"],
                "combined_percent": prediction,
                "combined_error_percent_point": (
                    prediction - row["realized_12m_total_return_percent"]
                ),
            }
        )

    status = (
        "passes_12m_calibration_gate_but_long_horizon_unvalidated"
        if short_horizon_gate_passed
        else "rejected_no_12m_holdout_improvement"
    )
    report = {
        "report_type": "etf_style_planning_rolling_vintage_backtest",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": master.get("as_of"),
        "usage_label": "short_horizon_calibration_not_long_term_return_forecast",
        "is_forecast": False,
        "evaluation_horizon_days": HORIZON_DAYS,
        "source_cma_horizon_years": [10, 15],
        "input_paths": {
            "return_master": return_master_path.as_posix(),
            "adjusted_prices": adjusted_price_directory.as_posix(),
            "corporate_events": event_path.as_posix(),
            "vintages": vintage_path.as_posix(),
        },
        "scope": {
            "current_master_product_count": len(master.get("products") or []),
            "supported_current_equity_product_count": len(products),
            "loaded_price_series_count": len(series_by_code),
            "evaluated_etf_vintage_count": len(rows),
            "excluded_etf_vintage_count": len(excluded),
            "vintage_count": len(vintage_payload.get("vintages") or []),
            "training_vintage_count": len(
                {
                    row["vintage_id"] for row in rows if row["split"] == "training"
                }
            ),
            "holdout_vintage_count": len(
                {
                    row["vintage_id"] for row in rows if row["split"] == "holdout"
                }
            ),
        },
        "anti_leakage_controls": [
            (
                "Historical total-return observations are strictly earlier than "
                "each formation date."
            ),
            "Forward returns begin strictly after each formation date.",
            (
                "Parameter selection uses training vintages only; the 2025 CMA "
                "vintage is holdout-only."
            ),
            (
                "Macro inputs must have official publication dates no later than "
                "each CMA formation date."
            ),
            (
                "Historical fee vintages are unavailable, so costs are excluded "
                "from every compared model."
            ),
        ],
        "parameter_search": {
            "objective": "minimum_training_style_vintage_mae_then_rmse",
            "history_scales": list(HISTORY_SCALES),
            "history_caps_percent_point": list(HISTORY_CAPS),
            "macro_scales": list(MACRO_SCALES),
            "macro_caps_percent_point": list(MACRO_CAPS),
            "candidate_count": (
                len(HISTORY_SCALES)
                * len(HISTORY_CAPS)
                * len(MACRO_SCALES)
                * len(MACRO_CAPS)
            ),
            "selected_parameters": selected_parameters,
        },
        "model_comparison": comparisons,
        "adoption_gate": {
            "status": status,
            "short_horizon_gate_passed": short_horizon_gate_passed,
            "requirements": {
                "holdout_style_vintage_mae_better_than_cma": mae_improved,
                "holdout_style_vintage_rmse_better_than_cma": rmse_improved,
                "holdout_etf_count_at_least_100": row_count >= 100,
                "holdout_style_vintage_count_at_least_10": style_count >= 10,
            },
            "production_parameter_change_authorized": False,
            "reason": (
                "A 12-month test cannot validate a 10-to-15-year CMA overlay; "
                "production constants remain unchanged pending longer history."
            ),
        },
        "etf_vintage_results": result_rows,
        "excluded_etf_vintages": excluded,
        "limitations": list(vintage_payload.get("limitations") or [])
        + [
            (
                "Only three public CMA vintages are available, with two training "
                "vintages and one holdout vintage."
            ),
            (
                "The universe contains only ETFs still listed and pension-eligible "
                "in the current master."
            ),
            (
                "Current ETF classifications are applied historically because "
                "classification vintages are unavailable."
            ),
            (
                "The results do not establish statistical significance or future "
                "performance."
            ),
        ],
    }
    return _json_ready(report)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a no-lookahead ETF style rolling-vintage calibration."
    )
    parser.add_argument("--return-master", type=Path)
    parser.add_argument("--return-root", type=Path, default=DEFAULT_RETURN_ROOT)
    parser.add_argument("--adjusted-prices", type=Path)
    parser.add_argument(
        "--adjusted-price-root", type=Path, default=DEFAULT_ADJUSTED_PRICE_ROOT
    )
    parser.add_argument("--events", type=Path)
    parser.add_argument("--event-root", type=Path, default=DEFAULT_EVENT_ROOT)
    parser.add_argument("--vintages", type=Path, default=DEFAULT_VINTAGE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return_master_path = args.return_master or _latest_file(
        args.return_root, "pension_etf_cost_return_master_*.json"
    )
    adjusted_price_directory = args.adjusted_prices or _latest_directory(
        args.adjusted_price_root
    )
    event_path = args.events or _latest_file(
        args.event_root, "etf_corporate_events_*.json"
    )
    report = build_rolling_vintage_backtest(
        return_master_path=return_master_path,
        adjusted_price_directory=adjusted_price_directory,
        event_path=event_path,
        vintage_path=args.vintages,
    )
    output_path = args.output / f"etf_style_backtest_{report['as_of']}.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "status": report["adoption_gate"]["status"],
                "evaluated_etf_vintage_count": report["scope"][
                    "evaluated_etf_vintage_count"
                ],
                "selected_parameters": report["parameter_search"][
                    "selected_parameters"
                ],
                "output_path": output_path.as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
