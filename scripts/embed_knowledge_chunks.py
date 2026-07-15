"""Embed knowledge chunks with BGE-M3 into Supabase (아키텍처.md §10).

실행(선택 의존성 그룹 필요):

    uv sync --group embeddings
    uv run --group embeddings python scripts/embed_knowledge_chunks.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.embeddings import (
    EMBEDDING_MODEL,
    BgeM3Embedder,
    embed_pending_chunks,
)
from backend.app.settings import get_settings


def main() -> int:
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    print(f"모델 로드 중: {EMBEDDING_MODEL} (최초 실행 시 다운로드)")
    embedder = BgeM3Embedder()
    count = embed_pending_chunks(database_url, embedder)
    print(f"임베딩 완료: {count}개 청크")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
