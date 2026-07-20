import json
from datetime import date, timedelta

import pytest

from backend.app.engine.models import AccountType
from backend.app.portfolio_universe_repository import (
    PortfolioUniverseRepository,
)


def _write_return_master(root) -> None:
    root.mkdir(parents=True)
    (root / "dc_etf_cost_return_2026-07-16.json").write_text(
        json.dumps(
            {
                "as_of": "2026-07-16",
                "products": [{"isu_code": "069500", "isu_name": "KODEX 200"}],
            }
        ),
        encoding="utf-8",
    )


def _write_adjusted_history(root, *, policy: str = "0") -> None:
    product_root = root / "2026-07-15"
    product_root.mkdir(parents=True)
    start = date(2025, 1, 1)
    observations = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "adjusted_close": str(10_000 + index),
        }
        for index in range(260)
    ]
    (product_root / "069500.json").write_text(
        json.dumps(
            {
                "price_policy": {"FID_ORG_ADJ_PRC": policy},
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )


def _write_event_master(root) -> None:
    root.mkdir(parents=True)
    (root / "etf_corporate_events_2026-07-16.json").write_text(
        json.dumps(
            {
                "kind_distribution_coverage_start": "2025-01-05",
                "kind_distribution_coverage_end": "2025-09-10",
                "events": [],
            }
        ),
        encoding="utf-8",
    )


def test_repository_prefers_kis_adjusted_close_and_keeps_253_rows(tmp_path) -> None:
    return_root = tmp_path / "returns"
    adjusted_root = tmp_path / "adjusted"
    _write_return_master(return_root)
    _write_adjusted_history(adjusted_root)

    repository = PortfolioUniverseRepository.from_latest_cache(
        AccountType.DC,
        return_root=return_root,
        adjusted_price_root=adjusted_root,
        krx_root=tmp_path / "krx-not-needed",
        event_root=tmp_path / "events-not-needed",
    )

    assert len(repository.histories["069500"]) == 253
    assert repository.history_sources == {"069500": "kis_adjusted_close"}
    assert repository.latest_history_as_of == max(repository.histories["069500"])
    assert repository.history_source_counts == {"kis_adjusted_close": 1}


def test_repository_rejects_non_adjusted_kis_history(tmp_path) -> None:
    return_root = tmp_path / "returns"
    adjusted_root = tmp_path / "adjusted"
    _write_return_master(return_root)
    _write_adjusted_history(adjusted_root, policy="1")

    with pytest.raises(ValueError, match="not adjusted-price"):
        PortfolioUniverseRepository.from_latest_cache(
            AccountType.DC,
            return_root=return_root,
            adjusted_price_root=adjusted_root,
            krx_root=tmp_path / "krx-not-needed",
            event_root=tmp_path / "events-not-needed",
        )


def test_repository_uses_only_kind_covered_dates_for_verified_total_return(
    tmp_path,
) -> None:
    return_root = tmp_path / "returns"
    adjusted_root = tmp_path / "adjusted"
    event_root = tmp_path / "events"
    _write_return_master(return_root)
    _write_adjusted_history(adjusted_root)
    _write_event_master(event_root)

    repository = PortfolioUniverseRepository.from_latest_cache(
        AccountType.DC,
        return_root=return_root,
        adjusted_price_root=adjusted_root,
        krx_root=tmp_path / "krx-not-needed",
        event_root=event_root,
    )
    histories, sources = repository.load_total_return_histories({"069500"})

    assert min(histories["069500"]) == date(2025, 1, 5)
    assert max(histories["069500"]) == date(2025, 9, 10)
    assert sources == {
        "069500": "kis_adjusted_close_plus_kind_cash_distribution"
    }
