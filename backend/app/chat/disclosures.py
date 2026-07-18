"""Question-ranked view over live FSS snapshots.

SQL·행 모델은 retrieval 저장소(아키텍처.md §10 통합)에 있고, 이 모듈은
질문-회사명 매칭 랭킹만 책임진다. fixtures are never queried here.
"""

import re
from decimal import Decimal

from psycopg_pool import ConnectionPool

from ..engine import AccountType
from ..retrieval.disclosures_repository import (
    DisclosureReadRepository as DisclosureStatsRepository,
)
from ..retrieval.disclosures_repository import ProviderDisclosure

__all__ = ["DisclosureReadRepository", "ProviderDisclosure"]


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", value.lower()).replace("주식회사", "")


def _rank(question: str, row: ProviderDisclosure) -> tuple[int, Decimal]:
    query = _normalized(question)
    company = _normalized(row.company_name)
    exact = 1 if company and company in query else 0
    reserve = row.reserve_krw or Decimal("0")
    return (exact, reserve)


class DisclosureReadRepository:
    """Rank live-ingested provider rows against the user question."""

    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        self._stats = DisclosureStatsRepository(database_url, pool=pool)

    def search(
        self,
        question: str,
        *,
        account_type: AccountType,
        limit: int,
    ) -> list[ProviderDisclosure]:
        rows = self._stats.latest_quarter_disclosures(account_type)
        ranked = sorted(rows, key=lambda row: _rank(question, row), reverse=True)
        explicit = [row for row in ranked if _rank(question, row)[0] == 1]
        selected = explicit if explicit else ranked
        return selected[: max(1, min(limit, 5))]
