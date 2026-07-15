"""Live, disposable two-user Supabase Auth/RLS verification.

Run from a directory containing the private .env file:
    uv run python C:/dev/finance-project-1-pr6/scripts/verify_auth_rls_e2e.py

It never prints credentials, tokens, email addresses, or user ids.  Test users
and their chat session are removed in a finally block, including on failure.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from uuid import uuid4

import httpx

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
            print("PASS: two-user Auth token issuance and RLS read/write isolation")
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
