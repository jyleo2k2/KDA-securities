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
