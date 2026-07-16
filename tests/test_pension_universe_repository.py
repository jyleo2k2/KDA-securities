import json
from pathlib import Path

import pytest

from backend.app.pension_universe_repository import PensionAccountUniverse


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _account_payload() -> dict[str, object]:
    return {
        "report_type": "pension_account_eligible_etfs_by_account",
        "algorithm_input": True,
        "product_scope": "account_eligible_only",
        "account_type": "dc",
        "as_of": "2026-07-15",
        "product_count": 1,
        "products": [
            {
                "isu_code": "000001",
                "classification": {
                    "asset_class": "equity",
                    "leverage_type": "normal",
                },
                "account_eligibility": {"eligible": True},
            }
        ],
    }


def test_loads_account_eligible_algorithm_universe(tmp_path: Path) -> None:
    path = tmp_path / "dc_eligible_etfs_2026-07-15.json"
    _write(path, _account_payload())

    universe = PensionAccountUniverse.from_path(path, expected_account="dc")

    assert universe.account_type == "dc"
    assert [product["isu_code"] for product in universe.products] == ["000001"]


def test_rejects_945_product_source_classification(tmp_path: Path) -> None:
    path = tmp_path / "etf_asset_classification_2026-07-15.json"
    _write(path, {"product_count": 945, "products": []})

    with pytest.raises(ValueError, match="account-specific"):
        PensionAccountUniverse.from_path(path, expected_account="dc")


def test_rejects_ineligible_or_leveraged_product(tmp_path: Path) -> None:
    payload = _account_payload()
    products = payload["products"]
    assert isinstance(products, list)
    product = products[0]
    assert isinstance(product, dict)
    classification = product["classification"]
    assert isinstance(classification, dict)
    classification["leverage_type"] = "leveraged"
    path = tmp_path / "dc_eligible_etfs_2026-07-15.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="leveraged or inverse"):
        PensionAccountUniverse.from_path(path, expected_account="dc")
