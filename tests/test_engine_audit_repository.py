from contextlib import contextmanager

from backend.app.engine.audit import EngineAuditRepository


def test_engine_audit_repository_uses_injected_pool_connection() -> None:
    connection = object()

    class FakePool:
        calls = 0

        @contextmanager
        def connection(self):
            self.calls += 1
            yield connection

    pool = FakePool()
    repository = EngineAuditRepository("postgresql://test", pool=pool)  # type: ignore[arg-type]

    with repository._connection() as acquired:
        assert acquired is connection

    assert pool.calls == 1


def test_engine_audit_repository_falls_back_to_direct_connection(monkeypatch) -> None:
    connection = object()
    calls = []

    @contextmanager
    def fake_connect(database_url: str):
        calls.append(database_url)
        yield connection

    monkeypatch.setattr("backend.app.engine.audit.psycopg.connect", fake_connect)
    repository = EngineAuditRepository("postgresql://test")

    with repository._connection() as acquired:
        assert acquired is connection

    assert calls == ["postgresql://test"]
