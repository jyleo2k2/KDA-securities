from datetime import date
from pathlib import Path

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatRequest, DataBoundary
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.etf_theme_repository import EtfThemeRepository
from backend.app.etf_theme_verification_repository import (
    PostgresEtfThemeVerificationRepository,
    ThemeContentEvidence,
    etf_theme_content_sha256,
)

CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")


def _theme_repository() -> EtfThemeRepository:
    return EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )


class _VerificationReader:
    def __init__(
        self,
        evidence: tuple[ThemeContentEvidence, ...] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self.evidence = evidence
        self.error = error
        self.requests: list[tuple[str, str, str, str]] = []

    def verified_evidence(
        self,
        *,
        catalog_version: str,
        theme_id: str,
        topic: str,
        content_sha256: str,
    ) -> tuple[ThemeContentEvidence, ...]:
        self.requests.append(
            (catalog_version, theme_id, topic, content_sha256)
        )
        if self.error is not None:
            raise self.error
        return self.evidence


def _service(reader: _VerificationReader | None = None) -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        theme_verification=reader,
    )


def test_theme_content_hash_changes_only_with_the_selected_topic() -> None:
    theme = _theme_repository().get("semiconductor")
    assert theme is not None

    overview_hash = etf_theme_content_sha256(theme, "overview")
    considerations_hash = etf_theme_content_sha256(
        theme, "investment_considerations"
    )
    changed = theme.model_copy(
        update={"one_line_analogy": "검증 해시 변경용 비유입니다."}
    )

    assert len(overview_hash) == 64
    assert overview_hash != etf_theme_content_sha256(changed, "overview")
    assert considerations_hash == etf_theme_content_sha256(
        changed, "investment_considerations"
    )


def test_verified_theme_topic_omits_only_the_draft_limitation() -> None:
    reader = _VerificationReader(
        (
            ThemeContentEvidence(
                evidence_id="knowledge:42",
                label="반도체 테마 공식 근거",
                locator="https://example.com/official-semiconductor",
                publisher="공식 발행기관",
                as_of=date(2026, 7, 20),
            ),
        )
    )

    response = _service(reader).ask(ChatRequest(message="반도체 테마가 뭐야?"))

    assert len(reader.requests) == 1
    assert reader.requests[0][:3] == (
        "2026-07-20.2",
        "semiconductor",
        "overview",
    )
    assert not any("공식 문서 검증 전 초안" in item for item in response.limitations)
    assert any("미래 성과" in item for item in response.limitations)
    verified = next(
        source
        for source in response.sources
        if source.evidence_id == "knowledge:42"
    )
    assert verified.data_boundary == DataBoundary.VERIFIED_KNOWLEDGE
    assert "knowledge:42" in response.sections[0].evidence_ids


def test_missing_or_failed_verification_keeps_the_draft_limitation() -> None:
    for reader in (
        _VerificationReader(),
        _VerificationReader(error=RuntimeError("database unavailable")),
    ):
        response = _service(reader).ask(
            ChatRequest(message="반도체 테마가 뭐야?")
        )

        assert any(
            "공식 문서 검증 전 초안" in item
            for item in response.limitations
        )


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.params: tuple[object, ...] | None = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, _sql: str, params: tuple[object, ...]) -> None:
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


class _Pool:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.cursor = _Cursor(rows)

    def connection(self) -> _Connection:
        return _Connection(self.cursor)


def _verification_row(
    *,
    content_hash: str,
    review_due: date = date(2026, 10, 20),
) -> tuple[object, ...]:
    return (
        content_hash,
        review_due,
        11,
        "반도체 테마 공식 근거",
        "https://example.com/official-semiconductor",
        "공식 발행기관",
        date(2026, 7, 20),
        "permitted",
        {
            "contains_personal_data": False,
            "data_boundary": "verified_knowledge",
            "is_mock": False,
            "official_source_urls": [
                "https://example.com/official-semiconductor"
            ],
            "review_due_date": "2026-10-20",
        },
        42,
        {
            "data_boundary": "verified_knowledge",
            "is_active": True,
        },
    )


def test_postgres_verification_rejects_stale_or_hash_mismatched_rows() -> None:
    expected_hash = "a" * 64
    undocumented_source = list(
        _verification_row(content_hash=expected_hash)
    )
    undocumented_source[8] = {
        **undocumented_source[8],
        "official_source_urls": ["https://example.com/different-source"],
    }
    cases = (
        _verification_row(content_hash="b" * 64),
        _verification_row(
            content_hash=expected_hash,
            review_due=date(2026, 7, 19),
        ),
        tuple(undocumented_source),
    )

    for row in cases:
        repository = PostgresEtfThemeVerificationRepository(
            "postgresql://unused",
            pool=_Pool([row]),
            today=lambda: date(2026, 7, 20),
        )

        assert repository.verified_evidence(
            catalog_version="2026-07-20.2",
            theme_id="semiconductor",
            topic="overview",
            content_sha256=expected_hash,
        ) == ()


def test_postgres_verification_returns_only_current_verified_evidence() -> None:
    expected_hash = "a" * 64
    pool = _Pool([_verification_row(content_hash=expected_hash)])
    repository = PostgresEtfThemeVerificationRepository(
        "postgresql://unused",
        pool=pool,
        today=lambda: date(2026, 7, 20),
    )

    evidence = repository.verified_evidence(
        catalog_version="2026-07-20.2",
        theme_id="semiconductor",
        topic="overview",
        content_sha256=expected_hash,
    )

    assert evidence == (
        ThemeContentEvidence(
            evidence_id="knowledge:42",
            label="반도체 테마 공식 근거",
            locator="https://example.com/official-semiconductor",
            publisher="공식 발행기관",
            as_of=date(2026, 7, 20),
        ),
    )
    assert pool.cursor.params == (
        "2026-07-20.2",
        "semiconductor",
        "overview",
    )
