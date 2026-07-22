from datetime import date
from decimal import Decimal

from backend.app.ingestion.macro_clients import MacroObservation
from backend.app.structural_market_evidence import (
    build_long_horizon_diagnostics,
    build_structural_market_report,
    parse_damodaran_history,
    parse_fama_french_annual_returns,
)


def _damodaran_html() -> bytes:
    rows = []
    for year in range(1980, 2013):
        rows.append(
            f"<tr><td>{year}</td><td>5%</td><td>2%</td><td>100</td>"
            "<td>5</td><td>2</td><td>4%</td><td>4%</td><td>4%</td></tr>"
        )
    return ("<table>" + "".join(rows) + "</table>").encode()


def _fama_french_zip() -> bytes:
    import io
    import zipfile

    text = "header\n,Mkt-RF,SMB,HML,RF\n"
    for year in range(1971, 2023):
        text += f"{year}, 5.00, 0, 0, 1.00\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("factors.csv", text)
    return stream.getvalue()


def _observation(metric_id: str, value: str) -> MacroObservation:
    return MacroObservation(
        metric_id=metric_id,
        source="FRED",
        label=metric_id,
        period="2026-07-17",
        value=Decimal(value),
        unit="%",
        source_reference=f"https://fred.stlouisfed.org/series/{metric_id}",
        dimensions={"realtime_as_of": "2026-07-20"},
    )


def test_parsers_and_ten_year_diagnostics_are_deterministic():
    damodaran = parse_damodaran_history(_damodaran_html())
    returns = parse_fama_french_annual_returns(_fama_french_zip())
    diagnostics = build_long_horizon_diagnostics(damodaran, returns)

    assert len(damodaran) == 33
    assert returns[2001] == Decimal("6.00")
    assert diagnostics["horizon_years"] == 10
    assert diagnostics["metrics"]["dividend_yield_plus_smoothed_growth"][
        "mae_percent_point"
    ] == "0.0000"
    assert diagnostics["time_split"]["calibration"]["formation_year_end"] == 1990
    assert diagnostics["time_split"]["embargo"]["observation_count"] == 10
    assert diagnostics["time_split"]["holdout"]["formation_year_start"] == 2001


def test_report_builds_equity_and_bond_inputs_without_authorizing_adoption():
    report = build_structural_market_report(
        as_of=date(2026, 7, 20),
        damodaran_content=_damodaran_html(),
        fama_french_content=_fama_french_zip(),
        fred_rows={
            "us_treasury_10y": [_observation("DGS10", "4.25")],
            "us_investment_grade_effective_yield": [
                _observation("BAMLC0A0CMEY", "5.10")
            ],
            "us_high_yield_effective_yield": [
                _observation("BAMLH0A0HYM2EY", "6.80")
            ],
        },
        source_manifests=[],
    )

    equity = report["asset_inputs"]["us_large_cap_equity"]
    assert equity["structural_estimate_percent"] == "6.0000"
    assert equity["equilibrium_prior_percent"] == "8.0000"
    assert equity["view_confidence"] == "0.8000"
    assert equity["view_confidence_calibration"]["formation_year_end"] == 1990
    assert report["asset_inputs"]["us_high_yield"][
        "structural_estimate_percent"
    ] == "6.8000"
    assert len(report["annual_residuals"]) == 33
    assert report["production_parameter_change_authorized"] is False
    assert report["is_forecast"] is False
