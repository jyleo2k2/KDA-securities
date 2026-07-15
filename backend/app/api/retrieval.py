"""Read endpoints for verified-knowledge search and latest news metadata."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from ..retrieval.repository import RetrievalRepository
from .deps import get_retrieval_repository

router = APIRouter(tags=["retrieval"])

KNOWLEDGE_SOURCE_LABEL = "검증 공식 문서 RAG(PostgreSQL 전문검색)"
NEWS_SOURCE_LABEL = "NAVER 검색 API 뉴스 메타데이터"


class KnowledgeMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    # SQL 함수가 uuid를 반환한다. JSON 직렬화는 문자열로 나간다.
    document_id: UUID
    title: str
    source_url: str
    content: str
    text_rank: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    source_label: str
    results: list[KnowledgeMatchOut]


class NewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    title: str
    description: str | None
    original_url: str
    portal_url: str | None
    published_at: datetime | None


class NewsListResponse(BaseModel):
    search_query: str
    source_label: str
    results: list[NewsItemOut]


@router.get("/retrieval/knowledge", response_model=KnowledgeSearchResponse)
def search_knowledge(
    repository: Annotated[RetrievalRepository, Depends(get_retrieval_repository)],
    query: str = Query(min_length=1),
    limit: int = Query(8, ge=1, le=50),
) -> KnowledgeSearchResponse:
    matches = repository.search_knowledge(query, limit=limit)
    return KnowledgeSearchResponse(
        query=query,
        source_label=KNOWLEDGE_SOURCE_LABEL,
        results=[KnowledgeMatchOut.model_validate(match) for match in matches],
    )


@router.get("/retrieval/news", response_model=NewsListResponse)
def latest_news(
    repository: Annotated[RetrievalRepository, Depends(get_retrieval_repository)],
    search_query: str = Query(min_length=1),
    limit: int = Query(10, ge=1, le=100),
) -> NewsListResponse:
    matches = repository.latest_news(search_query, limit=limit)
    return NewsListResponse(
        search_query=search_query,
        source_label=NEWS_SOURCE_LABEL,
        results=[NewsItemOut.model_validate(match) for match in matches],
    )
