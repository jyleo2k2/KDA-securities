import argparse
import json

import httpx

from backend.app.settings import get_settings

from .naver_news import fetch_naver_news
from .naver_news_repository import NaverNewsRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call NAVER API HUB news search and optionally upsert metadata."
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--display", type=int, default=10)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--sort", choices=("date", "sim"), default="date")
    parser.add_argument("--fetch-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if (
        settings.naver_api_hub_client_id is None
        or settings.naver_api_hub_client_secret is None
    ):
        raise SystemExit("NAVER API HUB credentials are required")
    client_id = settings.naver_api_hub_client_id.get_secret_value().strip()
    client_secret = settings.naver_api_hub_client_secret.get_secret_value().strip()
    if not client_id or not client_secret:
        raise SystemExit("NAVER API HUB credentials are required")

    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else None
    )
    if not args.fetch_only and not database_url:
        raise SystemExit("DATABASE_URL is required unless --fetch-only is used")

    repository = None if args.fetch_only else NaverNewsRepository(database_url or "")
    run_id = None
    source_id = None
    if repository:
        run_id, source_id = repository.start_run(
            query=args.query,
            display=args.display,
            start=args.start,
            sort=args.sort,
        )
    try:
        with httpx.Client(timeout=30.0) as client:
            response = fetch_naver_news(
                client,
                client_id=client_id,
                client_secret=client_secret,
                query=args.query,
                display=args.display,
                start=args.start,
                sort=args.sort,
            )
        if repository and run_id is not None and source_id is not None:
            repository.complete_run(
                run_id=run_id,
                source_id=source_id,
                query=args.query,
                response=response,
            )
    except Exception as exc:
        if repository and run_id is not None:
            repository.fail_run(run_id, exc)
        raise

    print(
        json.dumps(
            {
                "database": "not_requested" if args.fetch_only else "loaded",
                "query": args.query,
                "total": response.total,
                "received": len(response.items),
                "sort": args.sort,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
