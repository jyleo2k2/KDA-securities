"""Prepare and provision six synthetic demo users in Supabase Auth.

The tracked manifest separates short presentation login ids from the internal
Auth email identifiers, but never stores passwords. Passwords are generated
into the gitignored ``secrets/`` folder.
Remote provisioning requires server-only Supabase keys in ``.env``.

Five users are presentation login candidates. The payout-transition user stays
available as scenario data and as an Auth user, but is excluded from that pool.
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
DEMO_CONTEXT_TAX_YEAR = 2026
NON_CANDIDATE_SCENARIO_CODE = "pension_payout_transition"
DEMO_PASSWORD_MIN_LENGTH = 6
DEMO_AUTH_DOMAIN = "@kda-demo.invalid"


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 4:
        raise ValueError("unsupported demo user manifest schema_version")
    users = payload.get("users")
    if not isinstance(users, list) or not users:
        raise ValueError("demo user manifest must contain users")

    required = {
        "auth_user_id",
        "benchmark_user_id",
        "scenario_code",
        "nickname",
        "representative_age",
        "age_band",
        "login_id",
        "auth_email",
        "is_demo_login_candidate",
        "customer_context",
        "pension_savings_contribution_krw",
        "irp_contribution_krw",
    }
    for user in users:
        if not isinstance(user, dict) or required - user.keys():
            raise ValueError("demo user manifest row is incomplete")
        parsed_user_id = UUID(str(user["auth_user_id"]))
        if parsed_user_id.version != 4:
            raise ValueError("demo auth_user_id must be UUID v4")
        login_id = str(user["login_id"])
        auth_email = str(user["auth_email"])
        if not login_id or "@" in login_id:
            raise ValueError("demo login_id must be a non-empty short ID")
        if auth_email != f"{login_id}{DEMO_AUTH_DOMAIN}":
            raise ValueError("demo auth_email must match the short login_id")
        if not isinstance(user["is_demo_login_candidate"], bool):
            raise ValueError("is_demo_login_candidate must be boolean")

    for key in (
        "auth_user_id",
        "benchmark_user_id",
        "scenario_code",
        "login_id",
        "auth_email",
    ):
        values = [str(user[key]) for user in users]
        if len(values) != len(set(values)):
            raise ValueError(f"demo user manifest has duplicate {key}")
    candidates = [user for user in users if user["is_demo_login_candidate"]]
    excluded = next(
        (
            user
            for user in users
            if user["scenario_code"] == NON_CANDIDATE_SCENARIO_CODE
        ),
        None,
    )
    if len(candidates) != 5 or excluded is None or excluded["is_demo_login_candidate"]:
        raise ValueError(
            "demo login candidates must be five users excluding payout transition"
        )
    return users


def prepare_credentials(
    users: list[dict[str, Any]], path: Path = DEFAULT_CREDENTIALS_PATH
) -> list[dict[str, str]]:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        credentials = payload.get("users")
        if payload.get("schema_version") not in {1, 2} or not isinstance(
            credentials, list
        ):
            raise ValueError("invalid demo credentials file")
        users_by_scenario = {str(user["scenario_code"]): user for user in users}
        upgraded_credentials = []
        for credential in credentials:
            if not isinstance(credential, dict):
                raise ValueError("invalid demo credentials row")
            user = users_by_scenario.get(str(credential.get("scenario_code", "")))
            if user is None:
                raise ValueError("demo credentials contain an unknown scenario")
            upgraded_credentials.append(
                {
                    "auth_user_id": str(credential.get("auth_user_id", "")),
                    "scenario_code": str(credential.get("scenario_code", "")),
                    "login_id": str(user["login_id"]),
                    "auth_email": str(user["auth_email"]),
                    "password": str(credential.get("password", "")),
                }
            )
        credentials = upgraded_credentials
        _validate_credentials(users, credentials)
        if payload.get("schema_version") != 2 or payload.get("users") != credentials:
            _write_credentials(path, credentials)
        return credentials

    credentials = [
        {
            "auth_user_id": str(user["auth_user_id"]),
            "scenario_code": str(user["scenario_code"]),
            "login_id": str(user["login_id"]),
            "auth_email": str(user["auth_email"]),
            "password": f"KdaDemo!{secrets.token_urlsafe(24)}",
        }
        for user in users
    ]
    _write_credentials(path, credentials)
    return credentials


def _write_credentials(path: Path, credentials: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 2, "users": credentials},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with suppress(OSError):
        path.chmod(0o600)


def _validate_credentials(
    users: list[dict[str, Any]], credentials: list[dict[str, Any]]
) -> None:
    expected = {
        (
            str(user["auth_user_id"]),
            str(user["scenario_code"]),
            str(user["login_id"]),
            str(user["auth_email"]),
        )
        for user in users
    }
    actual = {
        (
            str(item.get("auth_user_id", "")),
            str(item.get("scenario_code", "")),
            str(item.get("login_id", "")),
            str(item.get("auth_email", "")),
        )
        for item in credentials
        if isinstance(item, dict)
    }
    if expected != actual or len(credentials) != len(users):
        raise ValueError("demo credentials do not match the tracked manifest")
    passwords = [str(item.get("password", "")) for item in credentials]
    if any(len(password) < DEMO_PASSWORD_MIN_LENGTH for password in passwords):
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


def _auth_payload(user: dict[str, Any], credential: dict[str, str]) -> dict[str, Any]:
    return {
        "id": str(user["auth_user_id"]),
        "email": str(user["auth_email"]),
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
            "demo_login_id": str(user["login_id"]),
            "is_demo_login_candidate": bool(user["is_demo_login_candidate"]),
        },
    }


def _auth_metadata_payload(user: dict[str, Any]) -> dict[str, Any]:
    payload = _auth_payload(user, {"password": "unused"})
    return {
        "user_metadata": payload["user_metadata"],
        "app_metadata": payload["app_metadata"],
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
    expected_demo_login_candidate: bool,
) -> None:
    response = client.post(
        f"{base_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": publishable_key},
        json={
            "email": credential["auth_email"],
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
    if app_metadata.get("is_demo_login_candidate") is not expected_demo_login_candidate:
        raise RuntimeError("demo login returned an unexpected candidate flag")


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
            DEMO_CONTEXT_TAX_YEAR,
            DEMO_CONTEXT_AS_OF_DATE,
            str(user["benchmark_user_id"]),
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
                benchmark_user_id,
                gross_salary_krw,
                comprehensive_income_krw,
                pension_savings_contribution_krw,
                irp_contribution_krw,
                tax_year,
                as_of_date
            )
            select
                %s::uuid,
                scenario.id,
                %s,
                %s,
                %s,
                benchmark.user_id,
                nullif(benchmark.gross_salary_krw, '')::numeric,
                nullif(benchmark.comprehensive_income_krw, '')::numeric,
                benchmark.pension_savings_contribution_krw::numeric,
                benchmark.irp_contribution_krw::numeric,
                %s::smallint,
                %s
            from public.mock_scenarios as scenario
            join public.benchmark_mock_users as benchmark
              on benchmark.user_id = %s
            where scenario.code = %s
            on conflict (auth_user_id) do update set
                scenario_id = excluded.scenario_id,
                nickname = excluded.nickname,
                representative_age = excluded.representative_age,
                customer_context = excluded.customer_context,
                benchmark_user_id = excluded.benchmark_user_id,
                gross_salary_krw = excluded.gross_salary_krw,
                comprehensive_income_krw = excluded.comprehensive_income_krw,
                pension_savings_contribution_krw =
                    excluded.pension_savings_contribution_krw,
                irp_contribution_krw = excluded.irp_contribution_krw,
                tax_year = excluded.tax_year,
                as_of_date = excluded.as_of_date,
                data_kind = 'mock',
                updated_at = now()
            """,
            rows,
        )
        cursor.execute(
            """
            select count(*), min(tax_year), max(tax_year)
            from public.demo_user_financial_context
            where auth_user_id = any(%s::uuid[])
            """,
            ([row[0] for row in rows],),
        )
        result = cursor.fetchone()
        if result != (len(rows), DEMO_CONTEXT_TAX_YEAR, DEMO_CONTEXT_TAX_YEAR):
            raise RuntimeError("demo financial context mapping or tax year is invalid")


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
    service_key = _required_secret(settings.supabase_secret_key, "SUPABASE_SECRET_KEY")
    database_url = _required_secret(settings.database_url, "DATABASE_URL")

    credentials_by_scenario = {item["scenario_code"]: item for item in credentials}
    users_by_scenario = {str(item["scenario_code"]): item for item in users}
    with httpx.Client(timeout=20.0) as client:
        existing_users = _list_users(client, base_url=base_url, service_key=service_key)
        by_id = {str(item.get("id")): item for item in existing_users}
        by_email = {str(item.get("email")): item for item in existing_users}

        for user in users:
            credential = credentials_by_scenario[str(user["scenario_code"])]
            user_id = str(user["auth_user_id"])
            auth_email = str(user["auth_email"])
            payload = _auth_payload(user, credential)
            existing_by_id = by_id.get(user_id)
            existing_by_email = by_email.get(auth_email)
            if existing_by_email and str(existing_by_email.get("id")) != user_id:
                raise RuntimeError("demo auth_email is owned by a different Auth user")
            if existing_by_id:
                if (
                    str(existing_by_id.get("email")) != auth_email
                    and not rotate_existing
                ):
                    raise RuntimeError(
                        "demo auth_email changed; run with --rotate-existing"
                    )
                if rotate_existing:
                    _update_user(
                        client,
                        base_url=base_url,
                        service_key=service_key,
                        user_id=user_id,
                        payload=payload,
                    )
                else:
                    _update_user(
                        client,
                        base_url=base_url,
                        service_key=service_key,
                        user_id=user_id,
                        payload=_auth_metadata_payload(user),
                    )
            else:
                _create_user(
                    client,
                    base_url=base_url,
                    service_key=service_key,
                    payload=payload,
                )

        for credential in credentials:
            expected_user = users_by_scenario[credential["scenario_code"]]
            _verify_sign_in(
                client,
                base_url=base_url,
                publishable_key=publishable_key,
                credential=credential,
                expected_demo_login_candidate=bool(
                    expected_user["is_demo_login_candidate"]
                ),
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
