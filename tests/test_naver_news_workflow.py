from pathlib import Path


def test_daily_news_workflow_runs_atomic_market_news_pipeline() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "naver-pension-news.yml"
    ).read_text(encoding="utf-8")

    pipeline = (
        "uv run --group embeddings python -m backend.app.ingestion.naver_market_news"
    )
    assert pipeline in workflow
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
    assert "uv sync --locked --group embeddings" in workflow
    assert "NEWS_SUMMARY_PROMPT_VERSION: news-summary-v3" in workflow
    assert "steps.market_news.outputs.result).held_for_full_batch" in workflow
    assert "::warning::Market-news rotation is holding new articles" in workflow
