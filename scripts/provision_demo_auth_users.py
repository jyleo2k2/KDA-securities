"""Prepare and provision six synthetic demo users in Supabase Auth.

The tracked manifest contains stable user ids and login ids, but never
passwords. Passwords are generated into the gitignored ``secrets/`` folder.
Remote provisioning requires server-only Supabase keys in ``.env``.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

DEFAULT_MANIFEST_PATH = REPOSITORY_ROOT / "data" / "mock" / "demo_scenario_users.json"
DEFAULT_CREDENTIALS_PATH = REPOSITORY_ROOT / "secrets" / "demo_scenario_auth.json"
DEMO_CONTEXT_AS_OF_DATE = date(2026, 7, 16)


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported demo user manifest schema_version")
    users = payload.get("users")
    if not isinstance(users, list) or not users:
        raise ValueError("demo user manifest must contain users")

    required = {
        "auth_user_id",
        "scenario_code",
        "nickname",
        "representative_age",
        "age_band",
        "login_id",
        "customer_context",
    }
    for user in users:
        if not isinstance(user, dict) or required - user.keys():
            raise ValueError("demo user manifest row is incomplete")
        parsed_user_id = UUID(str(user["auth_user_id"]))
        if parsed_user_id.version != 4:
            raise ValueError("demo auth_user_id must be UUID v4")
        if not str(user["login_id"]).endswith("@kda-demo.invalid"):
            raise ValueError("demo login_id must use @kda-demo.invalid")

    for key in ("auth_user_id", "scenario_code", "login_id"):
        values = [str(user[key]) for user in users]
        if len(values) != len(set(values)):
            raise ValueError(f"demo user manifest has duplicate {key}")
    return users


def prepare_credentials(
    users: list[dict[str, Any]], path: Path = DEFAULT_CREDENTIALS_PATH
) -> list[dict[str, str]]:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        credentials = payload.get("users")
        if payload.get("schema_version") != 1 or not isinstance(credentials, list):
            raise ValueError("invalid demo credentials file")
        _validate_credentials(users, credentials)
        return credentials

    credentials = [
        {
            "auth_user_id": str(user["auth_user_id"]),
            "scenario_code": str(user["scenario_code"]),
            "login_id": str(user["login_id"]),
            "password": f"KdaDemo!{secrets.token_urlsafe(24)}",
        }
        for user in users
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "users": credentials},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with suppress(OSError):
        path.chmod(0o600)
    return credentials


def _validate_credentials(
    users: list[dict[str, Any]], credentials: list[dict[str, Any]]
) -> None:
    expected = {
        (
            str(user["auth_user_id"]),
            str(user["scenario_code"]),
            str(user["login_id"]),
        )
        for user in users
    }
    actual = {
        (
            str(item.get("auth_user_id", "")),
            str(item.get("scenario_code", "")),
            str(item.get("login_id", "")),
        )
        for item in credentials
        if isinstance(item, dict)
    }
    if expected != actual or len(credentials) != len(users):
        raise ValueError("demo credentials do not match the tracked manifest")
    passwords = [str(item.get("password", "")) for item in credentials]
    if any(len(password) < 20 for password in passwords):
        raise ValueError("demo password is missing or too short")
    if len(passwords) != len(set(passwords)):
        raise ValueError("demo passwords must be unique")


def _required_secret(value: Any, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise RuntimeError(f"{name} is not configured")
    return value.get_secret_value().strip()


def _admin_headers(service_key: str) -> dict[str, str]:
    return {"apikey": service_key, "Authorization": f"Bearer {service_key}"}


def _list_users(
    client: httpx.Client, *, base_url: str, service_key: str
) -> list[dict[str, Any]]:
    response = client.get(
        f"{base_url}/auth/v1/admin/users",
        headers=_admin_headers(service_key),
        params={"page": 1, "per_page": 1000},
    )
    response.raise_for_status()
    payload = response.json()
    users = payload.get("users", [])
    if not isinstance(users, list):
        raise RuntimeError("Supabase Auth returned an invalid users payload")
    return users


def _auth_payload(
    user: dict[str, Any], credential: dict[str, str]
) -> dict[str, Any]:
    return {
        "id": str(user["auth_user_id"]),
        "email": str(user["login_id"]),
        "password": credential["password"],
        "email_confirm": True,
        "user_metadata": {
            "nickname": str(user["nickname"]),
            "representative_age": int(user["representative_age"]),
            "age_band": str(user["age_band"]),
        },
        "app_metadata": {
            "account_kind": "synthetic_demo",
            "demo_scenario_code": str(user["scenario_code"]),
        },
    }


def _create_user(
    client: httpx.Client,
    *,
    base_url: str,
    service_key: str,
    payload: dict[str, Any],
) -> None:
    response = client.post(
        f"{base_url}/auth/v1/admin/users",
        headers=_admin_headers(service_key),
        json=payload,
    )
    response.raise_for_status()


def _update_user(
    client: httpx.Client,
    *,
    base_url: str,
    service_key: str,
    user_id: str,
    payload: dict[str, Any],
) -> None:
    update_payload = dict(payload)
    update_payload.pop("id", None)
    response = client.put(
        f"{base_url}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(service_key),
        json=update_payload,
    )
    response.raise_for_status()


def _verify_sign_in(
    client: httpx.Client,
    *,
    base_url: str,
    publishable_key: str,
    credential: dict[str, str],
) -> None:
    response = client.post(
        f"{base_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": publishable_key},
        json={
            "email": credential["login_id"],
            "password": credential["password"],
        },
    )
    response.raise_for_status()
    payload = response.json()
    user = payload.get("user", {})
    if str(user.get("id")) != credential["auth_user_id"]:
        raise RuntimeError("demo login returned an unexpected user id")
    app_metadata = user.get("app_metadata", {})
    if app_metadata.get("demo_scenario_code") != credential["scenario_code"]:
        raise RuntimeError("demo login returned an unexpected scenario mapping")


def _sync_demo_financial_context(
    database_url: str,
    users: list[dict[str, Any]],
) -> None:
    rows = [
        (
            str(user["auth_user_id"]),
            str(user["nickname"]),
            int(user["representative_age"]),
            str(user["customer_context"]),
            DEMO_CONTEXT_AS_OF_DATE,
            str(user["scenario_code"]),
        )
        for user in users
    ]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.executemany(
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
                %s,
                %s,
                %s,
                2026,
                %s
            from public.mock_scenarios as scenario
            where scenario.code = %s
            on conflict (auth_user_id) do update set
                scenario_id = excluded.scenario_id,
                nickname = excluded.nickname,
                representative_age = excluded.representative_age,
                customer_context = excluded.customer_context,
                tax_year = excluded.tax_year,
                as_of_date = excluded.as_of_date,
                data_kind = 'mock',
                updated_at = now()
            """,
            rows,
        )
        cursor.execute(
            """
            select count(*)
            from public.demo_user_financial_context
            where auth_user_id = any(%s::uuid[])
            """,
            ([row[0] for row in rows],),
        )
        result = cursor.fetchone()
        if result is None or result[0] != len(rows):
            raise RuntimeError("demo financial context mapping is incomplete")


def provision_users(
    users: list[dict[str, Any]],
    credentials: list[dict[str, str]],
    *,
    rotate_existing: bool = False,
) -> None:
    from backend.app.settings import Settings

    settings = Settings()
    base_url = (settings.supabase_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    publishable_key = _required_secret(
        settings.supabase_publishable_key, "SUPABASE_PUBLISHABLE_KEY"
    )
    service_key = _required_secret(
        settings.supabase_secret_key, "SUPABASE_SECRET_KEY"
    )
    database_url = _required_secret(settings.database_url, "DATABASE_URL")

    credentials_by_scenario = {
        item["scenario_code"]: item for item in credentials
    }
    with httpx.Client(timeout=20.0) as client:
        existing_users = _list_users(
            client, base_url=base_url, service_key=service_key
        )
        by_id = {str(item.get("id")): item for item in existing_users}
        by_email = {str(item.get("email")): item for item in existing_users}

        for user in users:
            credential = credentials_by_scenario[str(user["scenario_code"])]
            user_id = str(user["auth_user_id"])
            login_id = str(user["login_id"])
            payload = _auth_payload(user, credential)
            existing_by_id = by_id.get(user_id)
            existing_by_email = by_email.get(login_id)
            if existing_by_email and str(existing_by_email.get("id")) != user_id:
                raise RuntimeError("demo login_id is owned by a different Auth user")
            if existing_by_id:
                if str(existing_by_id.get("email")) != login_id:
                    raise RuntimeError("demo Auth user id has an unexpected login_id")
                if rotate_existing:
                    _update_user(
                        client,
                        base_url=base_url,
                        service_key=service_key,
                        user_id=user_id,
                        payload=payload,
                    )
            else:
                _create_user(
                    client,
                    base_url=base_url,
                    service_key=service_key,
                    payload=payload,
                )

        for credential in credentials:
            _verify_sign_in(
                client,
                base_url=base_url,
                publishable_key=publishable_key,
                credential=credential,
            )
    _sync_demo_financial_context(database_url, users)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or provision six synthetic Supabase Auth users."
    )
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Generate the ignored credentials file without calling Supabase.",
    )
    parser.add_argument(
        "--rotate-existing",
        action="store_true",
        help="Explicitly replace passwords and metadata for existing demo users.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    users = load_manifest()
    credentials = prepare_credentials(users, args.credentials_file)
    if args.prepare_only:
        print(
            f"Prepared {len(credentials)} demo credentials at "
            f"{args.credentials_file.resolve()}"
        )
        return
    provision_users(users, credentials, rotate_existing=args.rotate_existing)
    print(f"PASS: provisioned and verified {len(credentials)} demo Auth users")


if __name__ == "__main__":
    main()
