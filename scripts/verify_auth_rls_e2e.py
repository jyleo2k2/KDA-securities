"""Live, disposable Supabase Auth/RLS and DB runtime verification.

Run from a directory containing the private .env file:
    uv run python <DB_WORKTREE>/scripts/verify_auth_rls_e2e.py

It never prints credentials, tokens, email addresses, or user ids. Test users
and their chat session are removed in a finally block, including on failure.
The NAVER ingestion start SQL runs in a transaction that is always rolled back.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

def _required_secret(value, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise RuntimeError(f"{name} is not configured")
    return value.get_secret_value().strip()


def _create_user(
    client: httpx.Client, *, base_url: str, service_key: str, password: str
) -> tuple[str, str]:
    email = f"rls-e2e-{uuid4().hex}@example.invalid"
    response = client.post(
        f"{base_url}/auth/v1/admin/users",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        json={"email": email, "password": password, "email_confirm": True},
    )
    response.raise_for_status()
    return str(response.json()["id"]), email


def _sign_in(
    client: httpx.Client,
    *,
    base_url: str,
    publishable_key: str,
    email: str,
    password: str,
) -> str:
    response = client.post(
        f"{base_url}/auth/v1/token?grant_type=password",
        headers={"apikey": publishable_key},
        json={"email": email, "password": password},
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _user_headers(publishable_key: str, token: str) -> dict[str, str]:
    return {"apikey": publishable_key, "Authorization": f"Bearer {token}"}


def _final_sse_response(body: str) -> dict[str, object]:
    for block in body.strip().split("\n\n"):
        if block.startswith("event: response"):
            return json.loads(block.split("data: ", 1)[1])
    raise RuntimeError("chat stream did not return a final response event")


def _require_result(response: httpx.Response, *, label: str) -> dict[str, object]:
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError(f"{label} returned no remote rows")
    return payload


class _RollbackConnection:
    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> psycopg.Connection:
        return self._connection

    def __exit__(self, *_: object) -> None:
        self._connection.rollback()
        self._connection.close()


def _verify_naver_start_sql(database_url: str) -> None:
    from backend.app.ingestion import naver_news_repository as repository_module
    from backend.app.ingestion.naver_news_repository import NaverNewsRepository

    real_connect = psycopg.connect
    with real_connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) from public.ingestion_runs")
        before_count = int(cursor.fetchone()[0])

    def rollback_connect(_: str) -> _RollbackConnection:
        return _RollbackConnection(real_connect(database_url))

    repository = NaverNewsRepository(database_url)
    with patch.object(
        repository_module.psycopg,
        "connect",
        side_effect=rollback_connect,
    ):
        run_id, source_id = repository.start_run(
            query="연금 코파일럿 원격 SQL 회귀 검증",
            display=1,
            start=1,
            sort="date",
            max_pages=1,
            max_age_days=1,
        )
    if run_id is None or source_id <= 0:
        raise RuntimeError("NAVER ingestion start SQL returned an invalid identity")

    with real_connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) from public.ingestion_runs")
        after_count = int(cursor.fetchone()[0])
    if after_count != before_count:
        raise RuntimeError("NAVER rollback verification changed ingestion_runs")


def _attach_temporary_demo_context(database_url: str, *, user_id: str) -> None:
    """Attach the disposable Auth user to one existing synthetic scenario."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.demo_user_financial_context (
                auth_user_id,
                scenario_id,
                nickname,
                representative_age,
                customer_context,
                tax_year,
                as_of_date
            )
            select
                %s::uuid,
                scenario.id,
                '원격 계좌 E2E 임시 사용자',
                35,
                '원격 계좌 API 검증 전용 임시 컨텍스트',
                2026,
                date '2026-07-16'
            from public.mock_scenarios as scenario
            where scenario.code = 'dc_dormant'
            """,
            (user_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("temporary demo context was not created")


def main() -> None:
    from backend.app.settings import Settings

    settings = Settings()
    base_url = (settings.supabase_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    publishable_key = _required_secret(
        settings.supabase_publishable_key, "SUPABASE_PUBLISHABLE_KEY"
    )
    service_key = _required_secret(settings.supabase_secret_key, "SUPABASE_SECRET_KEY")
    database_url = _required_secret(settings.database_url, "DATABASE_URL")
    password = f"E2e!{secrets.token_urlsafe(24)}"
    user_ids: list[str] = []
    session_id: str | None = None

    with httpx.Client(timeout=20.0) as client:
        try:
            user_a_id, user_a_email = _create_user(
                client, base_url=base_url, service_key=service_key, password=password
            )
            user_b_id, user_b_email = _create_user(
                client, base_url=base_url, service_key=service_key, password=password
            )
            user_ids.extend([user_a_id, user_b_id])
            token_a = _sign_in(
                client,
                base_url=base_url,
                publishable_key=publishable_key,
                email=user_a_email,
                password=password,
            )
            token_b = _sign_in(
                client,
                base_url=base_url,
                publishable_key=publishable_key,
                email=user_b_email,
                password=password,
            )
            _attach_temporary_demo_context(database_url, user_id=user_a_id)
            created = client.post(
                f"{base_url}/rest/v1/chat_sessions",
                headers={
                    **_user_headers(publishable_key, token_a),
                    "Prefer": "return=representation",
                },
                json={"owner_id": user_a_id, "title": "RLS E2E temporary"},
            )
            created.raise_for_status()
            session_id = str(created.json()[0]["id"])

            foreign_read = client.get(
                f"{base_url}/rest/v1/chat_sessions?id=eq.{session_id}",
                headers=_user_headers(publishable_key, token_b),
            )
            foreign_read.raise_for_status()
            if foreign_read.json() != []:
                raise RuntimeError("RLS violation: user B read user A session")

            foreign_insert = client.post(
                f"{base_url}/rest/v1/chat_messages",
                headers={
                    **_user_headers(publishable_key, token_b),
                    "Prefer": "return=representation",
                },
                json={"session_id": session_id, "role": "user", "content": "forbidden"},
            )
            if foreign_insert.status_code < 400:
                raise RuntimeError("RLS violation: user B wrote user A session")

            previous_pytest_current_test = os.environ.get("PYTEST_CURRENT_TEST")
            os.environ["PYTEST_CURRENT_TEST"] = "verify_auth_rls_e2e"
            try:
                from fastapi.testclient import TestClient

                from backend.app.api.deps import get_chat_narrator
                from backend.app.main import app

                app.dependency_overrides[get_chat_narrator] = lambda: None
                with TestClient(app) as api_client:
                    pension_accounts = api_client.get(
                        "/me/pension-accounts",
                        headers={"Authorization": f"Bearer {token_a}"},
                    )
                    pension_accounts.raise_for_status()
                    pension_payload = pension_accounts.json()
                    accounts = pension_payload.get("accounts")
                    if (
                        pension_payload.get("data_boundary") != "mock"
                        or not isinstance(accounts, list)
                        or not accounts
                        or not accounts[0].get("holdings")
                    ):
                        raise RuntimeError(
                            "pension accounts API returned no demo holdings"
                        )
                    idempotency_key = str(uuid4())
                    chat_headers = {
                        "Authorization": f"Bearer {token_a}",
                        "Idempotency-Key": idempotency_key,
                    }
                    chat_request = {
                        "message": "IRP 위험자산 한도를 알려줘",
                        "session_id": session_id,
                    }
                    first_chat = api_client.post(
                        "/chat/stream",
                        json=chat_request,
                        headers=chat_headers,
                    )
                    first_chat.raise_for_status()
                    first_payload = _final_sse_response(first_chat.text)
                    if (
                        first_payload.get("persisted") is not True
                        or first_payload.get("idempotency_replayed") is not False
                        or first_payload.get("session_id") != session_id
                    ):
                        raise RuntimeError("first chat stream persistence failed")

                    replayed_chat = api_client.post(
                        "/chat/stream",
                        json=chat_request,
                        headers=chat_headers,
                    )
                    replayed_chat.raise_for_status()
                    replayed_payload = _final_sse_response(replayed_chat.text)
                    if (
                        replayed_payload.get("persisted") is not True
                        or replayed_payload.get("idempotency_replayed") is not True
                        or replayed_payload.get("session_id") != session_id
                    ):
                        raise RuntimeError("chat idempotency replay failed")

                    _require_result(
                        api_client.get(
                            "/retrieval/knowledge",
                            params={"query": "연금저축 세액공제", "limit": 3},
                        ),
                        label="knowledge retrieval",
                    )
                    _require_result(
                        api_client.get(
                            "/retrieval/news",
                            params={"search_query": "한국 증시", "limit": 3},
                        ),
                        label="news retrieval",
                    )
                    _require_result(
                        api_client.get(
                            "/disclosures/pension-savings",
                            params={"year": 2025, "quarter": 3, "limit": 1},
                        ),
                        label="pension savings disclosures",
                    )
                    _require_result(
                        api_client.get(
                            "/disclosures/retirement",
                            params={
                                "scheme": "dc",
                                "year": 2026,
                                "quarter": 1,
                                "limit": 1,
                            },
                        ),
                        label="retirement disclosures",
                    )
                    portfolio = api_client.post(
                        "/engine/educational-portfolio",
                        json={
                            "account_type": "irp",
                            "age": 35,
                            "retirement_start_age": 60,
                            "risk_profile": "risk_neutral",
                            "loss_tolerance_percent": "20",
                            "max_etfs": 5,
                        },
                    )
                    portfolio.raise_for_status()
                    if not portfolio.json().get("candidates"):
                        raise RuntimeError("ETF portfolio returned no candidates")
            finally:
                if "app" in locals():
                    app.dependency_overrides.pop(get_chat_narrator, None)
                if previous_pytest_current_test is None:
                    os.environ.pop("PYTEST_CURRENT_TEST", None)
                else:
                    os.environ["PYTEST_CURRENT_TEST"] = previous_pytest_current_test

            _verify_naver_start_sql(database_url)
            print(
                "PASS: Auth/RLS, pension accounts API, chat persistence/replay, "
                "RAG/news/disclosures/ETF, and rollback-only NAVER SQL"
            )
        finally:
            if session_id is not None:
                client.delete(
                    f"{base_url}/rest/v1/chat_sessions?id=eq.{session_id}",
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                    },
                )
            for user_id in user_ids:
                client.delete(
                    f"{base_url}/auth/v1/admin/users/{user_id}",
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                    },
                )


if __name__ == "__main__":
    main()
