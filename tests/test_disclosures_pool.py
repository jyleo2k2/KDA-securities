"""Disclosure reads must reuse the shared pool instead of opening a fresh
connection per query (fixes ~800ms connect handshake on every disclosure call)."""

from contextlib import contextmanager

from backend.app.engine import AccountType
from backend.app.retrieval import disclosures_repository as module
from backend.app.retrieval.disclosures_repository import DisclosureReadRepository


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None) -> None:
        pass

    def __iter__(self):
        return iter(())


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()


class _FakePool:
    def __init__(self) -> None:
        self.connection_calls = 0

    @contextmanager
    def connection(self):
        self.connection_calls += 1
        yield _FakeConnection()


def test_pooled_disclosure_read_never_opens_fresh_connection(monkeypatch) -> None:
    def _fail_connect(*args, **kwargs):
        raise AssertionError("psycopg.connect must not be called when a pool exists")

    monkeypatch.setattr(module.psycopg, "connect", _fail_connect)
    pool = _FakePool()
    repository = DisclosureReadRepository("postgresql://test", pool=pool)

    assert repository.latest_quarter_disclosures(AccountType.IRP) == []

    assert pool.connection_calls == 1
