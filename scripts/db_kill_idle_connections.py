"""Supabase 세션 풀러(5432)의 좀비 idle 연결을 조회·정리한다 (이재용 직접 실행용).

`EMAXCONNSESSION: max clients reached in session mode` 에러가 뜰 때, 놀고 있는
(idle) 애플리케이션 연결이 세션 풀러 상한(기본 15)을 다 차지한 경우를 푼다.

기본은 현황만 출력하는 dry-run이다. 실제로 끊으려면 --kill 을 준다.

    uv run python scripts/db_kill_idle_connections.py            # 현황만
    uv run python scripts/db_kill_idle_connections.py --kill     # 5분+ idle 정리
    uv run python scripts/db_kill_idle_connections.py --kill --min-idle 60
    uv run python scripts/db_kill_idle_connections.py --kill --all-idle

안전장치:
- 자기 자신(pg_backend_pid)과 활성(active) 연결은 절대 끊지 않는다.
- Supabase 시스템 연결(Supavisor 풀러, pg_cron, pg_net, WAL, 백그라운드 워커,
  authenticator/supabase_* 등)은 제외하고 애플리케이션 유저 연결만 대상으로 한다.
- 기본은 5분 이상 idle 한 연결만 끊는다(--min-idle 로 조정, --all-idle 로 해제).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from backend.app.settings import get_settings

# 끊지 않을 시스템 유저(풀러·인증·백그라운드 서비스).
PROTECTED_USERS = (
    "supabase_admin",
    "supabase_auth_admin",
    "supabase_replication_admin",
    "supabase_storage_admin",
    "authenticator",
    "pgbouncer",
    "supabase_read_only_user",
)

# 애플리케이션 연결로 취급할 유저(백엔드 API·수집 스크립트가 쓰는 역할).
APP_USERS = ("postgres",)


def _database_url() -> str | None:
    settings = get_settings()
    if settings.database_url is None:
        return None
    url = settings.database_url.get_secret_value().strip()
    return url or None


def _fetch_activity(cursor: psycopg.Cursor) -> list[tuple]:
    cursor.execute(
        """
        select
            pid,
            usename,
            application_name,
            state,
            coalesce(
                extract(epoch from (now() - state_change))::int, 0
            ) as idle_seconds,
            client_addr::text
        from pg_stat_activity
        where datname = current_database()
          and pid <> pg_backend_pid()
        order by state, idle_seconds desc
        """
    )
    return cursor.fetchall()


def _is_app_idle(row: tuple) -> bool:
    _pid, usename, _app, state, _idle, _addr = row
    if state != "idle":
        return False
    if usename in PROTECTED_USERS:
        return False
    return usename in APP_USERS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kill",
        action="store_true",
        help="실제로 idle 연결을 끊는다. 생략하면 현황만 출력한다.",
    )
    parser.add_argument(
        "--min-idle",
        type=int,
        default=300,
        help="이 초 이상 idle 한 연결만 끊는다 (기본 300초=5분).",
    )
    parser.add_argument(
        "--all-idle",
        action="store_true",
        help="idle 시간과 무관하게 모든 애플리케이션 idle 연결을 끊는다.",
    )
    args = parser.parse_args()

    database_url = _database_url()
    if database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1

    with psycopg.connect(database_url, connect_timeout=8) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            rows = _fetch_activity(cursor)

            print("=== 현재 연결 현황 (이 database) ===")
            for pid, usename, app, state, idle_s, addr in rows:
                tag = "APP-IDLE" if _is_app_idle(
                    (pid, usename, app, state, idle_s, addr)
                ) else "keep"
                print(
                    f"[{tag:8}] pid={pid:<7} user={usename or '-':22} "
                    f"state={state or '-':7} idle={idle_s:>6}s "
                    f"app={app or '-'}"
                )
            print(f"--- 총 {len(rows)}개 연결 ---")

            threshold = 0 if args.all_idle else args.min_idle
            targets = [
                row
                for row in rows
                if _is_app_idle(row) and row[4] >= threshold
            ]

            if not targets:
                print(
                    f"\n끊을 대상이 없습니다 "
                    f"(idle >= {threshold}s 인 애플리케이션 연결 0개)."
                )
                return 0

            print(
                f"\n대상: idle >= {threshold}s 인 애플리케이션 연결 "
                f"{len(targets)}개 (pid: "
                f"{', '.join(str(r[0]) for r in targets)})"
            )

            if not args.kill:
                print("dry-run 입니다. 실제로 끊으려면 --kill 을 추가하세요.")
                return 0

            killed = 0
            for row in targets:
                pid = row[0]
                cursor.execute("select pg_terminate_backend(%s)", (pid,))
                ok = cursor.fetchone()[0]
                print(f"  terminate pid={pid}: {'OK' if ok else 'FAILED'}")
                if ok:
                    killed += 1
            print(f"\n{killed}/{len(targets)}개 연결을 정리했습니다.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
