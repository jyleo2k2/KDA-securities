from pathlib import Path


def test_production_code_does_not_import_scenario_fixtures() -> None:
    production_files = Path("backend").rglob("*.py")
    offenders = [
        str(path)
        for path in production_files
        if "from tests.scenario_fixtures" in path.read_text(encoding="utf-8")
        or "import tests.scenario_fixtures" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_step_two_does_not_change_supabase_schema() -> None:
    # Contract guard: this implementation must consume the existing generated
    # search_vector/GIN index, not introduce runtime schema mutation.
    ingestion_files = list(Path("backend/app/ingestion").rglob("*.py"))
    forbidden = ("alter table", "create table", "create index", "drop table")

    for path in ingestion_files:
        content = path.read_text(encoding="utf-8").lower()
        assert not any(statement in content for statement in forbidden), path
