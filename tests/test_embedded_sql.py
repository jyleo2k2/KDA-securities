import ast
import re
from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
SQL_MODULES = (
    ROOT / "backend" / "app" / "chat" / "disclosures.py",
    ROOT / "backend" / "app" / "engine" / "audit.py",
    ROOT / "backend" / "app" / "ingestion" / "embeddings.py",
    ROOT / "backend" / "app" / "ingestion" / "fss_repository.py",
    ROOT / "backend" / "app" / "ingestion" / "naver_news_repository.py",
    ROOT / "backend" / "app" / "retrieval" / "disclosures_repository.py",
    ROOT / "backend" / "app" / "retrieval" / "knowledge_repository.py",
    ROOT / "backend" / "app" / "retrieval" / "repository.py",
)
NAMED_PLACEHOLDER = re.compile(r"%\([^)]+\)s")


def test_embedded_postgres_statements_parse() -> None:
    parsed_count = 0
    for module in SQL_MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            sql = node.value.strip()
            if not sql.lower().startswith(
                ("delete ", "insert ", "select ", "update ", "with ")
            ):
                continue
            sql = NAMED_PLACEHOLDER.sub("null", sql).replace("%s", "null")
            parse_sql(sql)
            parsed_count += 1

    assert parsed_count >= 10
