from pathlib import Path

from backend.app.api.deps import portfolio_return_master_readiness
from backend.app.engine import AccountType


def test_return_master_readiness_reports_each_account_independently(
    tmp_path: Path,
) -> None:
    (tmp_path / "dc_etf_cost_return_2026-07-16.json").write_text(
        "{}", encoding="utf-8"
    )

    readiness = portfolio_return_master_readiness(tmp_path)

    assert readiness == {
        AccountType.DC: True,
        AccountType.IRP: False,
        AccountType.PENSION_SAVINGS: False,
    }
