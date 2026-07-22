import json
from pathlib import Path

import pytest

from backend.app.etf_theme_repository import EtfThemeRepository
from backend.app.ingestion.etf_theme_verification import (
    ETF_THEME_CONTENT_TOPICS,
    ThemeEvidenceManifestError,
    load_theme_evidence_manifest,
)
from backend.app.ingestion.knowledge import load_approved_documents
from backend.app.retrieval.knowledge_policy import is_allowed_official_source_url
from scripts.load_etf_theme_verifications import main as load_main

CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")
EVIDENCE_PATH = Path("data/knowledge/etf_theme_evidence.json")


def _repository() -> EtfThemeRepository:
    return EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )


def test_theme_evidence_covers_all_105_approved_question_types() -> None:
    repository = _repository()
    manifest = load_theme_evidence_manifest(repository)
    approved_document = next(
        document
        for document in load_approved_documents()
        if document.metadata["document_id"] == manifest.knowledge_document_id
    )

    assert len(manifest.themes) == 21
    assert len(manifest.themes) * len(ETF_THEME_CONTENT_TOPICS) == 105
    assert {binding.theme_id for binding in manifest.themes} == {
        theme.theme_id for theme in repository.list()
    }
    official_urls = approved_document.metadata["official_source_urls"]
    for binding in manifest.themes:
        assert is_allowed_official_source_url(binding.official_source_url)
        assert binding.official_source_url in official_urls
        marker = f"[theme:{binding.theme_id}]"
        assert sum(marker in chunk for chunk in approved_document.chunks) == 1


def test_theme_evidence_rejects_catalog_drift(tmp_path: Path) -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    payload["catalog_version"] = "stale-version"
    stale_path = tmp_path / "stale.json"
    stale_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ThemeEvidenceManifestError, match="catalog_version"):
        load_theme_evidence_manifest(_repository(), stale_path)


def test_theme_evidence_validate_only_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert load_main(["--validate-only"]) == 0
    assert "105개 질문 유형" in capsys.readouterr().out
