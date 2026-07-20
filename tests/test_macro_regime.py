import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api import macro as macro_api
from backend.app.api.deps import get_macro_evidence_repository
from backend.app.engine.macro_regime import (
    MACRO_REGIME_METRIC_IDS,
    MacroRegimeMatch,
    MonthlyMacroRegimeObservation,
    calculate_macro_analog_regimes,
)
from backend.app.engine.macro_regime_outcomes import (
    calculate_post_regime_etf_outcomes,
)
from backend.app.engine.models import AccountType, SourceChip
from backend.app.ingestion.macro import (
    build_macro_evidence_report,
    build_macro_regime_dataset,
)
from backend.app.ingestion.macro_clients import MacroObservation
from backend.app.macro_evidence import MacroEvidenceRepository
from backend.app.main import app


def _month(start: date, offset: int) -> date:
    index = start.year * 12 + start.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _observation(
    metric_id: str,
    period: date,
    value: Decimal,
    *,
    source: str,
    label: str | None = None,
    unit: str = "%",
) -> MacroObservation:
    references = {
        "BOK_ECOS": "https://ecos.bok.or.kr/api/",
        "FRED": "https://fred.stlouisfed.org/",
    }
    return MacroObservation(
        metric_id=metric_id,
        source=source,
        label=label or metric_id,
        period=period.isoformat(),
        value=value,
        unit=unit,
        source_reference=references[source],
        dimensions={},
    )


def _historical_observations(month_count: int = 96) -> list[MacroObservation]:
    start = date(2010, 1, 1)
    rows: list[MacroObservation] = []
    for offset in range(-12, month_count):
        month = _month(start, offset)
        rows.append(
            _observation(
                "kr_cpi_index",
                month,
                Decimal("100") + Decimal(offset + 12) / Decimal("10"),
                source="BOK_ECOS",
                label="소비자물가지수",
                unit="index",
            )
        )
    for offset in range(month_count):
        month = _month(start, offset)
        cycle = Decimal(offset % 24)
        if offset % 6 == 0:
            rows.append(
                _observation(
                    "kr_base_rate",
                    month.replace(day=15),
                    Decimal("1.5") + cycle / Decimal("20"),
                    source="BOK_ECOS",
                    label="한국은행 기준금리",
                )
            )
        rows.extend(
            [
                _observation(
                    "us_federal_funds_rate",
                    month,
                    Decimal("1.0") + cycle / Decimal("15"),
                    source="FRED",
                ),
                _observation(
                    "us_cpi_yoy",
                    month,
                    Decimal("1.8") + cycle / Decimal("30"),
                    source="FRED",
                ),
                _observation(
                    "us_treasury_10y",
                    month.replace(day=5),
                    Decimal("2.0") + cycle / Decimal("20"),
                    source="FRED",
                ),
                _observation(
                    "us_treasury_10y",
                    month.replace(day=20),
                    Decimal("2.2") + cycle / Decimal("20"),
                    source="FRED",
                ),
                _observation(
                    "us_breakeven_inflation_10y",
                    month.replace(day=5),
                    Decimal("1.5") + cycle / Decimal("40"),
                    source="FRED",
                ),
                _observation(
                    "us_breakeven_inflation_10y",
                    month.replace(day=20),
                    Decimal("1.7") + cycle / Decimal("40"),
                    source="FRED",
                ),
            ]
        )
    return rows


def _month_distance(left: date, right: date) -> int:
    return abs((left.year - right.year) * 12 + left.month - right.month)


def test_macro_regime_dataset_normalizes_six_complete_monthly_features() -> None:
    dataset = build_macro_regime_dataset(_historical_observations())

    assert dataset["outcome"] == "ready"
    assert dataset["metric_ids"] == list(MACRO_REGIME_METRIC_IDS)
    assert dataset["quality"]["complete_month_count"] == 96
    assert dataset["rows"][0]["period"] == "2010-01-01"
    assert dataset["rows"][0]["values"]["us_treasury_10y"] == "2.1"
    assert dataset["rows"][5]["values"]["kr_base_rate"] == "1.5"
    assert dataset["rows"][6]["values"]["kr_base_rate"] != "1.5"


def test_macro_regime_engine_is_deterministic_and_separates_matches() -> None:
    dataset = build_macro_regime_dataset(_historical_observations())
    observations = [
        MonthlyMacroRegimeObservation.model_validate(row) for row in dataset["rows"]
    ]

    first = calculate_macro_analog_regimes(observations)
    second = calculate_macro_analog_regimes(observations)

    assert first == second
    assert len(first.matches) == 5
    assert first.is_forecast is False
    assert first.planning_return_input is False
    assert first.allocation_weight_input is False
    assert first.rebalancing_trigger_input is False
    assert first.historical_outcomes_included is False
    assert all(
        _month_distance(first.current_period, match.period) >= 12
        for match in first.matches
    )
    assert all(
        _month_distance(left.period, right.period) >= 12
        for index, left in enumerate(first.matches)
        for right in first.matches[index + 1 :]
    )


def _regime_match(period: date) -> MacroRegimeMatch:
    values = {metric_id: Decimal("1") for metric_id in MACRO_REGIME_METRIC_IDS}
    return MacroRegimeMatch(
        period=period,
        distance=Decimal("0.2500"),
        values=values,
        expanding_z_scores=values,
    )


def _outcome_history() -> dict[date, Decimal]:
    values = {
        date(2024, 2, 1): "100",
        date(2024, 3, 1): "120",
        date(2024, 4, 1): "90",
        date(2024, 5, 1): "110",
        date(2024, 6, 3): "115",
        date(2024, 7, 1): "125",
        date(2024, 8, 1): "130",
        date(2024, 9, 2): "128",
        date(2024, 10, 1): "135",
        date(2024, 11, 1): "140",
        date(2024, 12, 2): "138",
        date(2025, 1, 2): "145",
        date(2025, 2, 3): "150",
    }
    return {observed_on: Decimal(value) for observed_on, value in values.items()}


def test_post_regime_etf_outcomes_use_realized_total_return_and_drawdown() -> None:
    result = calculate_post_regime_etf_outcomes(
        matches=[_regime_match(date(2024, 1, 1))],
        isu_codes=["069500"],
        names_by_code={"069500": "KODEX 200"},
        histories={"069500": _outcome_history()},
        history_sources={"069500": "kis_adjusted_close_plus_kind_cash_distribution"},
        source_chips={
            "069500": SourceChip(
                label="한투 수정주가·KIND 현금분배 반영 원화 총수익지수",
                reference="https://openapi.koreainvestment.com/",
                as_of=date(2025, 2, 3),
            )
        },
    )

    etf = result.groups[0].etfs[0]
    assert result.is_forecast is False
    assert result.rebalancing_trigger_input is False
    assert [item.horizon_months for item in etf.horizons] == [3, 6, 12]
    assert etf.horizons[0].total_return_percent == Decimal("10.0000")
    assert etf.horizons[0].maximum_drawdown_percent == Decimal("25.0000")
    assert etf.horizons[-1].total_return_percent == Decimal("50.0000")
    assert etf.gaps == []


def test_post_regime_etf_outcomes_keep_missing_periods_explicit() -> None:
    result = calculate_post_regime_etf_outcomes(
        matches=[_regime_match(date(2011, 2, 1))],
        isu_codes=["069500"],
        names_by_code={"069500": "KODEX 200"},
        histories={"069500": _outcome_history()},
        history_sources={"069500": "kis_adjusted_close_plus_kind_cash_distribution"},
        source_chips={
            "069500": SourceChip(
                label="총수익지수",
                reference="https://openapi.koreainvestment.com/",
                as_of=date(2025, 2, 3),
            )
        },
    )

    etf = result.groups[0].etfs[0]
    assert etf.horizons == []
    assert [gap.reason for gap in etf.gaps] == [
        "start_observation_unavailable",
        "start_observation_unavailable",
        "start_observation_unavailable",
    ]


def test_post_regime_etf_outcomes_allow_long_exchange_holiday() -> None:
    history = {
        date(2017, 4, 3): Decimal("100"),
        date(2017, 10, 10): Decimal("110"),
    }
    result = calculate_post_regime_etf_outcomes(
        matches=[_regime_match(date(2017, 3, 1))],
        isu_codes=["069500"],
        names_by_code={"069500": "KODEX 200"},
        histories={"069500": history},
        history_sources={
            "069500": "kis_adjusted_close_plus_kind_cash_distribution"
        },
        source_chips={
            "069500": SourceChip(
                label="총수익지수",
                reference="https://openapi.koreainvestment.com/",
                as_of=date(2017, 10, 10),
            )
        },
    )

    etf = result.groups[0].etfs[0]
    six_month = next(
        item for item in etf.horizons if item.horizon_months == 6
    )
    assert six_month.end_date == date(2017, 10, 10)
    assert six_month.total_return_percent == Decimal("10.0000")


def test_macro_analog_regime_api_returns_only_sanitized_contract(
    tmp_path: Path,
) -> None:
    report = build_macro_evidence_report(
        observations=_historical_observations(),
        as_of=date(2018, 1, 20),
    )
    report["source_manifests"] = [
        {
            "path": "data/raw/macro/private.json",
            "request_params": {"api_key": "must-not-leak"},
            "sha256": "private-hash",
        }
    ]
    report_path = tmp_path / "macro.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    repository = MacroEvidenceRepository(report_path)
    app.dependency_overrides[get_macro_evidence_repository] = lambda: repository
    try:
        response = TestClient(app).get("/macro/analog-regimes")
    finally:
        app.dependency_overrides.pop(get_macro_evidence_repository, None)

    assert response.status_code == 200
    body = response.json()
    assert body["complete_month_count"] == 96
    assert len(body["analysis"]["matches"]) == 5
    assert body["analysis"]["is_forecast"] is False
    serialized = json.dumps(body)
    assert "data/raw/macro" not in serialized
    assert "must-not-leak" not in serialized
    assert "private-hash" not in serialized


def test_macro_analog_regime_etf_outcome_api_links_selected_codes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = build_macro_evidence_report(
        observations=_historical_observations(month_count=200),
        as_of=date(2026, 7, 20),
    )
    report_path = tmp_path / "macro.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    macro_repository = MacroEvidenceRepository(report_path)

    class EtfRepository:
        products = [{"isu_code": "069500", "isu_name": "KODEX 200"}]
        histories = {"069500": _outcome_history()}
        history_sources = {"069500": "kis_adjusted_close_plus_kind_cash_distribution"}

        @staticmethod
        def load_total_return_histories(isu_codes):
            assert isu_codes == {"069500"}
            return EtfRepository.histories, EtfRepository.history_sources

    def load_repository(account_type, database_url=""):
        assert account_type == AccountType.IRP
        return EtfRepository()

    monkeypatch.setattr(
        macro_api,
        "get_portfolio_universe_repository",
        load_repository,
    )
    app.dependency_overrides[get_macro_evidence_repository] = lambda: macro_repository
    try:
        response = TestClient(app).post(
            "/macro/analog-regimes/etf-outcomes",
            json={"account_type": "irp", "isu_codes": ["069500"]},
        )
    finally:
        app.dependency_overrides.pop(get_macro_evidence_repository, None)

    assert response.status_code == 200
    body = response.json()
    assert body["etf_outcomes"]["is_forecast"] is False
    assert len(body["etf_outcomes"]["groups"]) == 5
    assert all(
        group["etfs"][0]["isu_code"] == "069500"
        for group in body["etf_outcomes"]["groups"]
    )


def test_macro_analog_regime_api_fails_closed_without_history(
    tmp_path: Path,
) -> None:
    repository = MacroEvidenceRepository(tmp_path / "missing.json")
    app.dependency_overrides[get_macro_evidence_repository] = lambda: repository
    try:
        response = TestClient(app).get("/macro/analog-regimes")
    finally:
        app.dependency_overrides.pop(get_macro_evidence_repository, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Historical macro regime evidence is not available"
    }
