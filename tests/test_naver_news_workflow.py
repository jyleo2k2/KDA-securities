from pathlib import Path


def test_daily_news_workflow_runs_ingestion_before_summarization() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "naver-pension-news.yml"
    ).read_text(encoding="utf-8")

    ingestion = "uv run python -m backend.app.ingestion.naver"
    summarization = "uv run python -m backend.app.ingestion.naver_summaries"
    assert ingestion in workflow
    assert summarization in workflow
    assert workflow.index(ingestion) < workflow.index(summarization)
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
    assert "--lookback-days 7" in workflow
