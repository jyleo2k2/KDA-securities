import argparse
import json
from pathlib import Path

from backend.app.chat.service import (
    LocalMarkdownKnowledgeRepository,
    get_chat_service,
)
from backend.app.retrieval.quality import (
    evaluate_knowledge_search,
    load_quality_cases,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure knowledge retrieval Hit Rate, MRR, and Recall."
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("data/search_quality/knowledge_v1.json"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--backend",
        choices=("local", "configured"),
        default="local",
        help="configured uses DATABASE_URL through server settings.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.backend == "local":
        repository = LocalMarkdownKnowledgeRepository()
    else:
        service = get_chat_service()
        if service.backend != "supabase":
            raise RuntimeError(
                "configured quality measurement requires DATABASE_URL"
            )
        repository = service.knowledge
    report = evaluate_knowledge_search(
        repository,
        load_quality_cases(args.benchmark),
        top_k=args.top_k,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if not report.missed_queries else 1


if __name__ == "__main__":
    raise SystemExit(main())
