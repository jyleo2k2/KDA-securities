import io
import zipfile

from backend.app.fama_french_vintage_validation import build_revision_report


def _factors(annual_return: float, end_year: int) -> bytes:
    text = "header\n,Mkt-RF,SMB,HML,RF\n"
    for year in range(2000, end_year + 1):
        text += f"{year}, {annual_return - 1:.2f}, 0, 0, 1.00\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("factors.csv", text)
    return stream.getvalue()


def test_revision_report_prefers_archived_outcome_cut():
    reference = {
        "vintages": [
            {
                "formation_year": 2011,
                "release_month": "2022-08",
                "url": "https://example.test/archive.zip",
                "path": "archive.zip",
            }
        ]
    }
    report = build_revision_report(
        reference=reference,
        current_content=_factors(6.1, 2021),
        vintage_contents={2011: _factors(6.0, 2021)},
    )

    row = report["vintages"][0]
    assert row["archived_realized_cagr_percent"] == "6.0000"
    assert row["current_cut_realized_cagr_percent"] == "6.1000"
    assert row["current_minus_archived_cagr_percent_point"] == "0.1000"
    assert report["summary"]["current_cut_substitution_allowed"] is False
    assert report["is_forecast"] is False
