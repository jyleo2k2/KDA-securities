import json
from datetime import date

from backend.app.etf_corporate_events import (
    build_etf_corporate_event_master,
)


def _write_kis_cache(root, observations):
    root.mkdir(parents=True)
    (root / "069500.json").write_text(
        json.dumps(
            {
                "isu_code": "069500",
                "isu_name": "KODEX 200",
                "endpoint": "/uapi/domestic-stock/v1/quotations/"
                "inquire-daily-itemchartprice",
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )


def test_event_master_links_exact_ex_date_and_classifies_explicit_split(
    tmp_path,
) -> None:
    adjusted_root = tmp_path / "adjusted"
    _write_kis_cache(
        adjusted_root,
        [
            {
                "date": "2026-07-10",
                "modified": "Y",
                "split_rate": "200.00",
                "revaluation_reason": "액면분할",
            }
        ],
    )
    distribution_report = {
        "coverage_start": "2020-01-01",
        "coverage_end": "2026-07-16",
        "events": [
            {
                "isu_code": "069500",
                "isu_name": "KODEX 200",
                "record_date": "2026-07-15",
                "payment_date": "2026-07-17",
                "distribution_per_share_krw": "100",
                "receipt_number": "distribution-1",
                "source_url": "https://kind.example/distribution",
            }
        ]
    }
    ex_date_report = {
        "coverage_start": "2020-01-01",
        "coverage_end": "2026-07-16",
        "failure_count": 0,
        "events": [
            {
                "isu_code": "049886",
                "isu_name": "KODEX 200",
                "effective_date": "2026-07-14",
                "reference_price_krw": "9990",
                "receipt_number": "ex-date-1",
                "source_url": "https://kind.example/ex-date",
            }
        ],
    }

    report = build_etf_corporate_event_master(
        distribution_report=distribution_report,
        ex_date_report=ex_date_report,
        adjusted_price_root=adjusted_root,
        source_files={},
        as_of=date(2026, 7, 16),
    )

    cash = next(
        event
        for event in report["events"]
        if event["event_type"] == "cash_distribution"
    )
    split = next(event for event in report["events"] if event["event_type"] == "split")
    assert cash["effective_date"] == "2026-07-14"
    assert cash["timing_basis"] == "exact_kind_ex_distribution_date"
    assert split["status"] == "confirmed_from_explicit_reason"
    assert split["ratio"] == "200.00"
    assert report["kind_distribution_coverage_start"] == "2020-01-01"
    assert report["kind_distribution_coverage_end"] == "2026-07-16"
    assert report["kind_ex_date_coverage_start"] == "2020-01-01"
    assert report["kind_ex_date_coverage_end"] == "2026-07-16"


def test_event_master_does_not_infer_action_from_normal_price_row(tmp_path) -> None:
    adjusted_root = tmp_path / "adjusted"
    _write_kis_cache(
        adjusted_root,
        [
            {
                "date": "2026-07-10",
                "modified": "N",
                "split_rate": "200.00",
                "revaluation_reason": "",
            }
        ],
    )

    report = build_etf_corporate_event_master(
        distribution_report={"events": []},
        ex_date_report=None,
        adjusted_price_root=adjusted_root,
        source_files={},
        as_of=date(2026, 7, 16),
    )

    assert report["kis_adjustment_event_count"] == 0
    assert report["events"] == []


def test_event_master_cross_validates_dividends_without_overwriting_kind(
    tmp_path,
) -> None:
    adjusted_root = tmp_path / "adjusted"
    _write_kis_cache(adjusted_root, [])
    distribution_report = {
        "events": [
            {
                "isu_code": "069500",
                "isu_name": "KODEX 200",
                "isin": "KR7069500007",
                "record_date": "2026-07-15",
                "payment_date": "2026-07-17",
                "distribution_per_share_krw": "100",
                "receipt_number": "distribution-1",
                "source_url": "https://kind.example/distribution",
            }
        ]
    }
    kis_report = {
        "output1": [
            {
                "sht_cd": "069500",
                "record_date": "20260715",
                "per_sto_divi_amt": "100.00",
                "divi_pay_dt": "20260717",
                "divi_kind": "분기배당",
            },
            {
                "sht_cd": "069500",
                "record_date": "20260815",
                "per_sto_divi_amt": "110",
                "divi_pay_dt": "20260820",
                "divi_kind": "분기배당",
            },
        ]
    }
    fsc_report = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "isinCd": "KR7069500007",
                            "dvdnBasDt": "20260715",
                            "cashDvdnPayDt": "20260718",
                            "stckGenrDvdnAmt": "100",
                            "basDt": "20260716",
                            "stckIssuCmpyNm": "삼성자산운용",
                        }
                    ]
                }
            }
        }
    }

    report = build_etf_corporate_event_master(
        distribution_report=distribution_report,
        ex_date_report=None,
        adjusted_price_root=adjusted_root,
        source_files={},
        as_of=date(2026, 7, 16),
        kis_dividend_report=kis_report,
        fsc_dividend_report=fsc_report,
    )

    cash = next(
        event
        for event in report["events"]
        if event["event_type"] == "cash_distribution"
    )
    scheduled = next(
        event
        for event in report["events"]
        if event["event_type"] == "scheduled_cash_distribution"
    )
    assert cash["cash_per_share_krw"] == "100"
    assert cash["payment_date"] == "2026-07-17"
    assert cash["status"] == "confirmed_cash_flow"
    assert cash["cross_validation"]["status"] == "source_conflict_review_required"
    assert cash["cross_validation"]["conflicts"] == [
        {
            "source_type": "fsc_stock_dividend_information",
            "fields": ["payment_date"],
        }
    ]
    assert report["source_conflict_event_count"] == 1
    assert report["scheduled_kis_dividend_count"] == 1
    assert scheduled["status"] == "excluded_from_historical_total_return"
    assert scheduled["timing_basis"] == "record_date_schedule_not_ex_date"
