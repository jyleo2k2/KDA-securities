import json
from datetime import date
from pathlib import Path

import pytest

from backend.app.etf_product_description_repository import (
    EtfProductDescription,
    EtfProductDescriptionRepository,
    get_default_etf_product_description_repository,
)


def _description(name: str) -> EtfProductDescription:
    return EtfProductDescription(
        product_name=name,
        full_description="전체 설명",
        one_line_description="한 줄 설명",
        source_document_ids=("approved-document",),
        as_of_date=date(2026, 7, 21),
    )


def test_default_repository_joins_by_normalized_product_name() -> None:
    repository = get_default_etf_product_description_repository()

    description = repository.get("ＫＯＤＥＸ 자동차")

    assert description is not None
    assert description.product_name == "KODEX 자동차"
    assert description.one_line_description.startswith("KRX 자동차지수")
    assert repository.get("존재하지 않는 ETF") is None


def test_approved_shared_conversation_descriptions_are_loaded_by_name() -> None:
    repository = get_default_etf_product_description_repository()

    assert repository.get("SOL 조선TOP3플러스") is not None
    assert repository.get("TIGER 화장품") is not None
    assert repository.get("KODEX AI전력핵심설비") is not None
    assert repository.get("TIGER 반도체TOP10") is not None
    assert repository.get("RISE ESG사회책임투자") is not None
    assert repository.get("PLUS K방산") is not None
    assert len(repository) == 39


def test_merged_research_removes_salutation_and_keeps_all_source_messages() -> None:
    path = Path("docs/20_리서치/ETF_상품/ETF_상품_설명_통합원문.md")
    text = path.read_text(encoding="utf-8")

    assert "호연 님" not in text
    assert text.count("### 사용자 ") + text.count("### 어시스턴트 ") == 17
    assert text.count("https://chatgpt.com/share/") == 6
    assert "## [ETF:487240] KODEX AI전력핵심설비" in text


def test_repository_rejects_normalized_name_collisions() -> None:
    with pytest.raises(ValueError, match="normalized-name collision"):
        EtfProductDescriptionRepository(
            (_description("KODEX자동차"), _description("KODEX 자동차"))
        )


def test_local_catalog_rejects_unapproved_extra_fields(tmp_path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "catalog_version": "test",
        "products": [
            {
                **_description("테스트 ETF").model_dump(mode="json"),
                "generated_description": "추정해서 만든 설명",
            }
        ],
    }
    path = tmp_path / "descriptions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="generated_description"):
        EtfProductDescriptionRepository.from_local_path(path)
