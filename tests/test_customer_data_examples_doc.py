import json
from pathlib import Path

from scripts.render_customer_data_examples_md import render_document

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
DOCUMENT = ROOT / "docs" / "30_스펙" / "고객_목데이터_전체_예시.md"


def test_customer_data_examples_document_is_current_and_exhaustive() -> None:
    examples = json.loads(
        (MOCK_DIR / "customer_data_examples.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    scenarios = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )

    expected = render_document(examples, manifest, scenarios)
    assert DOCUMENT.read_text(encoding="utf-8") == expected
    assert "고객 필드 29개 전체" in expected
    assert "KODEX·TIGER·ACE·RISE·SOL·HANARO" in expected
    assert "`statutory_exception` | `null`" in expected
    assert "`USR00001`" in expected
    assert "`USR03419`" in expected
