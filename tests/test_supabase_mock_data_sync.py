import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "supabase" / "seed.sql"
MANIFEST = ROOT / "data" / "mock" / "demo_scenario_users.json"
FALLBACK_SCENARIOS = ROOT / "data" / "mock" / "chatbot_scenarios.json"
PROVISION_SCRIPT = ROOT / "scripts" / "provision_demo_auth_users.py"


def test_remote_mock_data_changes_are_reproducible_locally() -> None:
    migrations = list(
        (ROOT / "supabase" / "migrations").glob("*_sync_modified_mock_data.sql")
    )
    assert len(migrations) == 1, "원격 목데이터 동기화 migration이 필요합니다."

    expected_fragments = (
        "납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음",
        "각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음",
        "('0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid, 0::numeric, 0::numeric)",
        (
            "('1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid, "
            "3000000::numeric, 6000000::numeric)"
        ),
        (
            "('2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid, "
            "1500000::numeric, 2000000::numeric)"
        ),
        "('306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid, 2000000::numeric, 0::numeric)",
        (
            "('417ec083-71a2-4242-95e4-b155e6fb5005'::uuid, "
            "2400000::numeric, 2400000::numeric)"
        ),
    )

    for sql_path in (migrations[0], SEED):
        sql = sql_path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in sql, (
                f"{sql_path.name}에 원격 변경값이 없습니다: {fragment}"
            )


def test_remote_mock_data_sync_is_idempotent_and_non_destructive() -> None:
    migrations = list(
        (ROOT / "supabase" / "migrations").glob("*_sync_modified_mock_data.sql")
    )
    assert len(migrations) == 1, "원격 목데이터 동기화 migration이 필요합니다."

    sql = migrations[0].read_text(encoding="utf-8").lower()
    assert "on conflict" in sql
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "delete from" not in sql


def test_demo_user_manifest_reproduces_remote_context_and_contributions() -> None:
    users = {
        user["scenario_code"]: user
        for user in json.loads(MANIFEST.read_text(encoding="utf-8"))["users"]
    }
    expected = {
        "dc_dormant": (0, 0),
        "tax_contribution_uninvested": (0, 0),
        "overlap_risk_concentration": (3_840_000, 4_920_000),
        "young_retirement_distance": (0, 0),
        "family_budget_pressure": (0, 7_680_000),
        "pension_payout_transition": (0, 0),
    }

    for scenario_code, (pension_savings, irp) in expected.items():
        user = users[scenario_code]
        assert user["pension_savings_contribution_krw"] == pension_savings
        assert user["irp_contribution_krw"] == irp
        assert user["benchmark_user_id"].startswith("USR")

    script = PROVISION_SCRIPT.read_text(encoding="utf-8")
    assert "pension_savings_contribution_krw" in script
    assert "irp_contribution_krw" in script


def test_fallback_scenario_descriptions_match_remote_mock_data() -> None:
    scenarios = {
        scenario["scenario_code"]: scenario
        for scenario in json.loads(FALLBACK_SCENARIOS.read_text(encoding="utf-8"))
    }
    expected_descriptions = {
        "dc_dormant": (
            "회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객\n"
            "비고: 납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음"
        ),
        "tax_contribution_uninvested": (
            "세액공제를 위해 납입했지만 IRP·연금저축을 실제 운용하지 않은 고객\n"
            "비고: 각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음"
        ),
        "overlap_risk_concentration": (
            "DC·IRP·연금저축에 글로벌주식형 자산이 중복되어 위험자산 편중이 있는 고객"
        ),
        "young_retirement_distance": (
            "노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 청년층 고객"
        ),
        "family_budget_pressure": (
            "자녀·주거비로 추가 납입은 빠듯하지만 "
            "노후 준비를 걱정하기 시작한 중년층 고객"
        ),
    }

    for scenario_code, description in expected_descriptions.items():
        assert scenarios[scenario_code]["description"] == description
