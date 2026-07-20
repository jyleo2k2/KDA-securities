import json
from pathlib import Path

from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.engine.scenario import evaluate_mock_scenario
from scripts.provision_demo_auth_users import (
    _auth_payload,
    _sync_demo_financial_context,
    _validate_credentials,
    load_manifest,
    prepare_credentials,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "mock" / "demo_scenario_users.json"
SCENARIOS = ROOT / "data" / "mock" / "chatbot_scenarios.json"


def test_demo_manifest_maps_six_unique_users_to_six_scenarios() -> None:
    users = load_manifest(MANIFEST)
    scenario_codes = {
        item["scenario_code"]
        for item in json.loads(SCENARIOS.read_text(encoding="utf-8"))
    }

    assert len(users) == 6
    assert {item["scenario_code"] for item in users} == scenario_codes
    assert len({item["login_id"] for item in users}) == 6
    assert len({item["benchmark_user_id"] for item in users}) == 6
    assert sum(item["is_demo_login_candidate"] for item in users) == 5
    assert next(
        item
        for item in users
        if item["scenario_code"] == "pension_payout_transition"
    )["is_demo_login_candidate"] is False
    assert all(item["login_id"].endswith("@kda-demo.invalid") for item in users)
    assert "password" not in MANIFEST.read_text(encoding="utf-8").lower()


def test_auth_payload_keeps_candidate_flag_in_server_managed_metadata() -> None:
    users = load_manifest(MANIFEST)
    payout_user = next(
        item
        for item in users
        if item["scenario_code"] == "pension_payout_transition"
    )
    payload = _auth_payload(payout_user, {"password": "not-a-real-password"})

    assert payload["app_metadata"]["is_demo_login_candidate"] is False
    assert "is_demo_login_candidate" not in payload["user_metadata"]


def test_prepare_credentials_generates_unique_passwords_once(tmp_path: Path) -> None:
    users = load_manifest(MANIFEST)
    credentials_path = tmp_path / "demo_auth.json"

    first = prepare_credentials(users, credentials_path)
    second = prepare_credentials(users, credentials_path)

    assert first == second
    assert len(first) == 6
    assert len({item["password"] for item in first}) == 6
    assert all(len(item["password"]) >= 20 for item in first)


def test_demo_credentials_allow_short_unique_demo_passwords() -> None:
    users = load_manifest(MANIFEST)
    credentials = [
        {
            "auth_user_id": user["auth_user_id"],
            "scenario_code": user["scenario_code"],
            "login_id": user["login_id"],
            "password": f"KDA!{index}Demo",
        }
        for index, user in enumerate(users, start=1)
    ]

    _validate_credentials(users, credentials)


def test_financial_context_sync_maps_all_users_with_mock_contributions(
    monkeypatch,
) -> None:
    users = load_manifest(MANIFEST)

    class FakeCursor:
        def __init__(self) -> None:
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def executemany(self, query, rows) -> None:
            assert "benchmark_user_id" in query
            assert "gross_salary_krw" in query
            assert "pension_savings_contribution_krw" in query
            assert "irp_contribution_krw" in query
            self.rows = list(rows)

        def execute(self, query, params) -> None:
            assert "select count(*)" in query
            assert "min(tax_year)" in query
            assert len(params[0]) == len(self.rows)

        def fetchone(self):
            return (len(self.rows), 2026, 2026)

    cursor = FakeCursor()

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def cursor(self):
            return cursor

    monkeypatch.setattr(
        "scripts.provision_demo_auth_users.psycopg.connect",
        lambda _: FakeConnection(),
    )

    _sync_demo_financial_context("postgresql://test", users)

    assert len(cursor.rows) == 6
    rows_by_scenario = {row[-1]: row for row in cursor.rows}
    assert rows_by_scenario["tax_contribution_uninvested"][-2] == "USR00540"


def test_lifecycle_scenarios_have_expected_totals_and_respect_account_caps() -> None:
    repository = LocalScenarioRepository()
    expected_totals = {
        "young_retirement_distance": "23210000.00",
        "family_budget_pressure": "88660000.00",
        "pension_payout_transition": "157430000.00",
    }

    for scenario_code, total in expected_totals.items():
        scenario = repository.get(scenario_code)
        assert scenario is not None
        evaluation = evaluate_mock_scenario(scenario)
        assert str(evaluation.total_amount_krw) == total
        assert all(
            account.within_limit is not False
            for account in evaluation.account_evaluations
        )
