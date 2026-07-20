"""Collect and validate structural market anchors for planning assumptions.

The output is evidence for an educational planning-return candidate.  It is not
a return forecast and it never authorizes a production parameter change.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from backend.app.ingestion._files import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_hex,
)
from backend.app.ingestion._secrets import require_secret
from backend.app.ingestion.macro_clients import (
    MacroApiError,
    MacroObservation,
    RawMacroResponse,
    fetch_fred_series,
)
from backend.app.settings import Settings

DAMODARAN_URL = (
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimpl.html"
)
FAMA_FRENCH_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_CSV.zip"
)
DEFAULT_RAW_ROOT = Path("data/raw/structural-market")
DEFAULT_REPORT_PATH = Path(
    "data/cache/planning_returns/structural_market_evidence_latest.json"
)
PERCENT_QUANTUM = Decimal("0.0001")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _parse_percent(value: str) -> Decimal:
    return Decimal(value.strip().replace("%", "").replace(",", ""))


def parse_damodaran_history(content: bytes) -> list[dict[str, Decimal | int]]:
    parser = _TableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    result = []
    for row in parser.rows:
        if len(row) < 9 or not row[0].isdigit() or len(row[0]) != 4:
            continue
        try:
            result.append(
                {
                    "year": int(row[0]),
                    "earnings_yield_percent": _parse_percent(row[1]),
                    "dividend_yield_percent": _parse_percent(row[2]),
                    "sp500_level": _parse_percent(row[3]),
                    "earnings": _parse_percent(row[4]),
                    "dividends": _parse_percent(row[5]),
                    "treasury_bond_rate_percent": _parse_percent(row[6]),
                    "smoothed_growth_percent": _parse_percent(row[7]),
                    "implied_erp_percent": _parse_percent(row[8]),
                }
            )
        except ArithmeticError:
            continue
    if not result:
        raise ValueError("Damodaran history contains no parseable annual rows")
    return sorted(result, key=lambda item: int(item["year"]))


def parse_fama_french_annual_returns(content: bytes) -> dict[int, Decimal]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError("Fama-French archive must contain exactly one file")
        text = archive.read(names[0]).decode("utf-8", errors="strict")
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise ValueError("Fama-French archive is invalid") from exc

    result: dict[int, Decimal] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        year_text = row[0].strip()
        if len(year_text) != 4 or not year_text.isdigit():
            continue
        year = int(year_text)
        result[year] = Decimal(row[1].strip()) + Decimal(row[4].strip())
    if not result:
        raise ValueError("Fama-French archive contains no annual factor rows")
    return result


def _annualized_return(values: list[Decimal]) -> Decimal:
    wealth = Decimal("1")
    for value in values:
        wealth *= Decimal("1") + value / Decimal("100")
    years = Decimal(len(values))
    return _percent(
        Decimal(str(math.pow(float(wealth), float(Decimal("1") / years)) - 1))
        * Decimal("100")
    )


def _metrics(errors: list[Decimal]) -> dict[str, str | int]:
    if not errors:
        raise ValueError("at least one error is required")
    count = Decimal(len(errors))
    mae = sum(abs(error) for error in errors) / count
    rmse = (sum(error * error for error in errors) / count).sqrt()
    bias = sum(errors) / count
    return {
        "observation_count": len(errors),
        "mae_percent_point": str(_percent(mae)),
        "rmse_percent_point": str(_percent(rmse)),
        "mean_bias_percent_point": str(_percent(bias)),
    }


def build_long_horizon_diagnostics(
    damodaran_rows: list[dict[str, Decimal | int]],
    annual_returns: dict[int, Decimal],
    *,
    horizon_years: int = 10,
) -> dict[str, Any]:
    rows = []
    for item in damodaran_rows:
        year = int(item["year"])
        forward_years = list(range(year + 1, year + horizon_years + 1))
        trailing_years = list(range(year - horizon_years + 1, year + 1))
        if not all(value in annual_returns for value in forward_years):
            continue
        if not all(value in annual_returns for value in trailing_years):
            continue
        realized = _annualized_return(
            [annual_returns[value] for value in forward_years]
        )
        trailing = _annualized_return(
            [annual_returns[value] for value in trailing_years]
        )
        structural = _percent(
            Decimal(item["dividend_yield_percent"])
            + Decimal(item["smoothed_growth_percent"])
        )
        equilibrium = _percent(
            Decimal(item["treasury_bond_rate_percent"])
            + Decimal(item["implied_erp_percent"])
        )
        rows.append(
            {
                "formation_year": year,
                "realized_window": f"{forward_years[0]}-{forward_years[-1]}",
                "structural_percent": str(structural),
                "equilibrium_percent": str(equilibrium),
                "trailing_return_percent": str(trailing),
                "realized_return_percent": str(realized),
                "structural_error_percent_point": str(_percent(structural - realized)),
                "equilibrium_error_percent_point": str(
                    _percent(equilibrium - realized)
                ),
                "trailing_error_percent_point": str(_percent(trailing - realized)),
            }
        )
    if not rows:
        raise ValueError("no complete long-horizon validation windows")

    def errors(key: str) -> list[Decimal]:
        return [Decimal(row[key]) for row in rows]

    return {
        "horizon_years": horizon_years,
        "vintage_definition": "reconstructed_annual_observation_not_archived_release",
        "metrics": {
            "dividend_yield_plus_smoothed_growth": _metrics(
                errors("structural_error_percent_point")
            ),
            "treasury_rate_plus_implied_erp": _metrics(
                errors("equilibrium_error_percent_point")
            ),
            "trailing_10y_return": _metrics(errors("trailing_error_percent_point")),
        },
        "vintages": rows,
    }


def build_prior_year_residuals(
    damodaran_rows: list[dict[str, Decimal | int]],
    annual_returns: dict[int, Decimal],
) -> list[dict[str, str | int]]:
    by_year = {int(item["year"]): item for item in damodaran_rows}
    result = []
    for year, realized in sorted(annual_returns.items()):
        prior = by_year.get(year - 1)
        if prior is None:
            continue
        anchor = _percent(
            Decimal(prior["dividend_yield_percent"])
            + Decimal(prior["smoothed_growth_percent"])
        )
        result.append(
            {
                "year": year,
                "prior_year_structural_anchor_percent": str(anchor),
                "realized_market_return_percent": str(_percent(realized)),
                "residual_percent_point": str(_percent(realized - anchor)),
            }
        )
    return result


def _download_public(client: httpx.Client, url: str, source: str) -> bytes:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise MacroApiError(
            f"{source} transport failed", code="transport_error"
        ) from exc
    if response.status_code != 200:
        raise MacroApiError(
            f"{source} returned HTTP {response.status_code}", code="http_error"
        )
    return response.content


def _save_fred_raw(
    root: Path, response: RawMacroResponse, metric_id: str
) -> dict[str, Any]:
    path = root / "fred" / f"{metric_id}.json"
    atomic_write_bytes(path, response.raw_content)
    return {
        "source": response.source,
        "reference": "https://fred.stlouisfed.org/",
        "path": path.as_posix(),
        "request_params": response.request_params,
        "sha256": response.sha256,
    }


def _latest(rows: list[MacroObservation]) -> MacroObservation:
    if not rows:
        raise ValueError("official series has no observations through as-of date")
    return rows[-1]


def _source_chip(label: str, reference: str, as_of: str) -> dict[str, str]:
    return {"label": label, "reference": reference, "as_of": as_of}


def build_structural_market_report(
    *,
    as_of: date,
    damodaran_content: bytes,
    fama_french_content: bytes,
    fred_rows: dict[str, list[MacroObservation]],
    source_manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    damodaran_rows = parse_damodaran_history(damodaran_content)
    annual_returns = parse_fama_french_annual_returns(fama_french_content)
    latest_damodaran = damodaran_rows[-1]
    source_year = int(latest_damodaran["year"])
    structural_equity = _percent(
        Decimal(latest_damodaran["dividend_yield_percent"])
        + Decimal(latest_damodaran["smoothed_growth_percent"])
    )
    equilibrium_equity = _percent(
        Decimal(latest_damodaran["treasury_bond_rate_percent"])
        + Decimal(latest_damodaran["implied_erp_percent"])
    )
    diagnostics = build_long_horizon_diagnostics(damodaran_rows, annual_returns)
    structural_metric = diagnostics["metrics"][
        "dividend_yield_plus_smoothed_growth"
    ]
    equilibrium_metric = diagnostics["metrics"]["treasury_rate_plus_implied_erp"]
    structural_rmse = Decimal(structural_metric["rmse_percent_point"])
    equilibrium_rmse = Decimal(equilibrium_metric["rmse_percent_point"])
    confidence = equilibrium_rmse / (structural_rmse + equilibrium_rmse)
    confidence = min(Decimal("0.80"), max(Decimal("0.20"), confidence))

    damodaran_source = _source_chip(
        "NYU Stern Damodaran Historical Implied Equity Risk Premiums",
        DAMODARAN_URL,
        f"{source_year}-12-31",
    )
    asset_inputs: dict[str, Any] = {
        "us_large_cap_equity": {
            "structural_estimate_percent": str(structural_equity),
            "structural_method": "dividend_yield_plus_smoothed_growth",
            "equilibrium_prior_percent": str(equilibrium_equity),
            "view_confidence": str(_percent(confidence)),
            "source": damodaran_source,
            "components": {
                "dividend_yield_percent": str(
                    latest_damodaran["dividend_yield_percent"]
                ),
                "smoothed_growth_percent": str(
                    latest_damodaran["smoothed_growth_percent"]
                ),
                "treasury_bond_rate_percent": str(
                    latest_damodaran["treasury_bond_rate_percent"]
                ),
                "implied_erp_percent": str(latest_damodaran["implied_erp_percent"]),
            },
        }
    }
    fixed_income_mapping = {
        "us_10y_treasury": "us_treasury_10y",
        "us_investment_grade_credit": "us_investment_grade_effective_yield",
        "us_high_yield": "us_high_yield_effective_yield",
    }
    for asset_code, metric_id in fixed_income_mapping.items():
        observation = _latest(fred_rows[metric_id])
        asset_inputs[asset_code] = {
            "structural_estimate_percent": str(_percent(observation.value)),
            "structural_method": "starting_effective_yield_anchor",
            "equilibrium_prior_percent": None,
            "view_confidence": None,
            "source": _source_chip(
                observation.label,
                observation.source_reference,
                observation.period,
            ),
            "components": {"starting_yield_percent": str(observation.value)},
        }

    return {
        "report_type": "structural_market_evidence",
        "schema_version": "2026-07-20.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "usage_label": "research_candidate_not_return_forecast",
        "is_forecast": False,
        "production_parameter_change_authorized": False,
        "asset_inputs": asset_inputs,
        "long_horizon_diagnostics": diagnostics,
        "annual_residuals": build_prior_year_residuals(
            damodaran_rows, annual_returns
        ),
        "source_manifests": source_manifests,
        "anti_leakage_controls": [
            "FRED requests lock realtime_start and realtime_end to the as-of date.",
            "Each realized ten-year window begins after its formation year.",
            "No diagnostic parameter is fitted to a future realized window.",
        ],
        "limitations": [
            (
                "Damodaran and Fama-French files are current historical cuts, "
                "not archived release vintages."
            ),
            (
                "The equity building block omits explicit margin, dilution and "
                "valuation-normalization terms."
            ),
            (
                "Starting yield is a bond return anchor, not a duration/default-loss "
                "forecast."
            ),
            (
                "The diagnostics do not include comparable CMA values for every "
                "historical vintage."
            ),
            (
                "The evidence cannot establish future accuracy or authorize "
                "production adoption."
            ),
        ],
    }


def run_live_collection(
    *,
    fred_api_key: str,
    as_of: date,
    raw_root: Path = DEFAULT_RAW_ROOT,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    snapshot_root = raw_root / as_of.isoformat()
    manifests: list[dict[str, Any]] = []
    fred_rows: dict[str, list[MacroObservation]] = {}
    with httpx.Client(
        timeout=httpx.Timeout(45.0),
        headers={"User-Agent": "pension-copilot-structural-evidence/0.1"},
        follow_redirects=True,
    ) as client:
        public_sources = (
            ("damodaran", DAMODARAN_URL, "damodaran_histimpl.html"),
            ("fama_french", FAMA_FRENCH_URL, "fama_french_factors.zip"),
        )
        public_contents = {}
        for source, url, filename in public_sources:
            content = _download_public(client, url, source)
            path = snapshot_root / source / filename
            atomic_write_bytes(path, content)
            public_contents[source] = content
            manifests.append(
                {
                    "source": source,
                    "reference": url,
                    "path": path.as_posix(),
                    "request_params": {},
                    "sha256": sha256_hex(content),
                }
            )

        fred_specs = (
            ("us_treasury_10y", "DGS10", "미국 10년 국채금리"),
            (
                "us_investment_grade_effective_yield",
                "BAMLC0A0CMEY",
                "ICE BofA 미국 투자등급 회사채 유효수익률",
            ),
            (
                "us_high_yield_effective_yield",
                "BAMLH0A0HYM2EY",
                "ICE BofA 미국 하이일드 회사채 유효수익률",
            ),
        )
        observation_start = f"{as_of.year - 1}-01-01"
        for metric_id, series_id, label in fred_specs:
            response, rows = fetch_fred_series(
                client,
                api_key=fred_api_key,
                metric_id=metric_id,
                series_id=series_id,
                label=label,
                unit="%",
                observation_start=observation_start,
                observation_end=as_of.isoformat(),
                realtime_as_of=as_of.isoformat(),
            )
            manifests.append(_save_fred_raw(snapshot_root, response, metric_id))
            fred_rows[metric_id] = rows

    report = build_structural_market_report(
        as_of=as_of,
        damodaran_content=public_contents["damodaran"],
        fama_french_content=public_contents["fama_french"],
        fred_rows=fred_rows,
        source_manifests=manifests,
    )
    atomic_write_json(report_path, report)
    return {
        "as_of": as_of.isoformat(),
        "asset_input_count": len(report["asset_inputs"]),
        "long_horizon_vintage_count": len(
            report["long_horizon_diagnostics"]["vintages"]
        ),
        "annual_residual_count": len(report["annual_residuals"]),
        "production_parameter_change_authorized": False,
        "report_path": report_path.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)
    result = run_live_collection(
        fred_api_key=require_secret(settings.fred_api_key, "FRED_API_KEY"),
        as_of=args.as_of,
        raw_root=args.raw_root,
        report_path=args.report_path,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
