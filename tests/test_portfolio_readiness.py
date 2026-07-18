from pathlib import Path

from backend.app.api import deps
from backend.app.api.deps import portfolio_return_master_readiness
from backend.app.engine import AccountType
from backend.app.settings import Settings


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


def test_warm_chat_dependencies_skips_local_return_check_when_database_is_configured(
    monkeypatch,
) -> None:
    def fail_if_called():
        raise AssertionError("local return readiness must not run in database mode")

    monkeypatch.setattr(deps, "portfolio_return_master_readiness", fail_if_called)
    monkeypatch.setattr(deps, "get_query_embedder", lambda: None)
    monkeypatch.setattr(deps, "get_chat_narrator", lambda settings: None)

    deps.warm_chat_dependencies(
        Settings(database_url="postgresql://user:password@example.com/database")
    )
