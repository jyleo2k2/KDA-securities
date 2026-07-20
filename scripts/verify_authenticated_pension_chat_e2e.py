"""Verify the live authenticated pension-overview path with a disposable user.

The script never prints credentials, access tokens, email addresses, or user ids.
It deletes the temporary chat session and Auth user in ``finally``.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

LOCAL_API = "http://127.0.0.1:8000"
TEST_NICKNAME = "검증사용자"
QUESTION = "연금계좌규칙 알려줘"
HIDDEN_OVERVIEW_TERMS = (
    "55세",
    "연금수령한도",
    "70세 미만",
    "사적연금",
    "중도인출",
    "해지",
)


def _required_secret(value, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise RuntimeError(f"{name} is not configured")
    return value.get_secret_value().strip()


def main() -> None:
    from backend.app.settings import Settings

    settings = Settings()
    supabase_url = (settings.supabase_url or "").rstrip("/")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    publishable_key = _required_secret(
        settings.supabase_publishable_key,
        "SUPABASE_PUBLISHABLE_KEY",
    )
    service_key = _required_secret(
        settings.supabase_secret_key,
        "SUPABASE_SECRET_KEY",
    )
    database_url = _required_secret(settings.database_url, "DATABASE_URL")

    email = f"pension-chat-e2e-{uuid4().hex}@example.invalid"
    password = f"E2e!{secrets.token_urlsafe(24)}"
    user_id: str | None = None
    session_id: str | None = None
    token: str | None = None
    admin_headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }

    with httpx.Client(timeout=30.0) as client:
        try:
            created_user = client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers=admin_headers,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                },
            )
            created_user.raise_for_status()
            user_id = str(created_user.json()["id"])

            with psycopg.connect(database_url) as connection:
                connection.execute(
                    """
                    insert into public.user_profiles (user_id, nickname)
                    values (%s, %s)
                    """,
                    (user_id, TEST_NICKNAME),
                )

            from backend.app.chat.user_context import DemoUserContextRepository

            stored_nickname = DemoUserContextRepository(database_url).get_nickname(
                UUID(user_id)
            )
            if stored_nickname != TEST_NICKNAME:
                raise RuntimeError(
                    "temporary nickname was not readable from PostgreSQL"
                )

            signed_in = client.post(
                f"{supabase_url}/auth/v1/token?grant_type=password",
                headers={"apikey": publishable_key},
                json={"email": email, "password": password},
            )
            signed_in.raise_for_status()
            token = str(signed_in.json()["access_token"])

            chat = client.post(
                f"{LOCAL_API}/chat",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={"message": QUESTION},
            )
            chat.raise_for_status()
            payload = chat.json()
            response = payload["response"]
            session_id = payload.get("session_id")

            if response["data_mode"] != "verified_pension_account_overview":
                raise RuntimeError("authenticated overview used an unexpected mode")
            if response.get("salutation") != f"{TEST_NICKNAME}님":
                raise RuntimeError(
                    "authenticated nickname salutation was not applied: "
                    f"{response.get('salutation')!r}"
                )
            section_text = "\n".join(
                section.get("content", "") for section in response["sections"]
            )
            leaked = [term for term in HIDDEN_OVERVIEW_TERMS if term in section_text]
            if leaked:
                raise RuntimeError("deferred topics leaked into the overview")
            locators = [source["locator"] for source in response["sources"]]
            if not locators or not all(
                locator.startswith("https://") for locator in locators
            ):
                raise RuntimeError("official web source links were not returned")
            print(
                "PASS: authenticated pension overview, nickname, topic scope, "
                "and official sources"
            )
        finally:
            if session_id is not None and token is not None:
                client.delete(
                    f"{LOCAL_API}/chat/sessions/{session_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            if user_id is not None:
                client.delete(
                    f"{supabase_url}/auth/v1/admin/users/{user_id}",
                    headers=admin_headers,
                )


if __name__ == "__main__":
    main()
