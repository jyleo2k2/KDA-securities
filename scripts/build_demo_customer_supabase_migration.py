"""Render the additive Supabase migration for six demo customer profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
OUTPUT_PATH = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260721025143_store_demo_customer_profiles_and_metrics.sql"
)


DDL = """-- Store the complete six-customer demo assessment and public metric contract.
-- These server-managed MOCK tables are not exposed directly through the Data API.

create table public.demo_investor_profiles (
    scenario_id bigint primary key
        references public.mock_scenarios(id) on delete cascade,
    assessment_id text not null unique,
    investor_profile text not null check (
        investor_profile in (
            'stable', 'stable_seeking', 'risk_neutral', 'active', 'aggressive'
        )
    ),
    investor_profile_label text not null,
    total_score smallint not null check (total_score between 0 and 55),
    score_band text not null,
    scenario_name text not null,
    scenario_description text not null,
    investment_reason text not null,
    portfolio_opinion_review text not null,
    representative_etf_isu_codes text[] not null,
    representative_etf_theme text not null,
    representative_etf_theme_review text not null,
    portfolio_consistency_note text not null,
    financial_product_shares_percent jsonb not null,
    non_scored_answers jsonb not null,
    portfolio_allocations jsonb not null,
    source_documents jsonb not null,
    rule_version text not null,
    is_demo_login_candidate boolean not null,
    data_kind text not null default 'mock' check (data_kind = 'mock'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.demo_investor_profile_answers (
    scenario_id bigint not null
        references public.demo_investor_profiles(scenario_id) on delete cascade,
    question_code text not null,
    selected_option text not null,
    score smallint not null check (score between 0 and 7),
    basis text not null,
    created_at timestamptz not null default now(),
    primary key (scenario_id, question_code)
);

create table public.demo_public_portfolio_metrics (
    scenario_id bigint primary key
        references public.mock_scenarios(id) on delete cascade,
    benchmark_user_id text not null unique
        references public.benchmark_mock_users(user_id) on delete restrict,
    portfolio_trailing_12m_return_pct numeric(8, 4) not null,
    return_period_start date not null,
    return_period_end date not null,
    return_metric_code text not null,
    return_metric_label text not null,
    return_calculation_basis text not null,
    return_source_label text not null,
    is_forecast boolean not null check (is_forecast = false),
    official_ranking_metric boolean not null
        check (official_ranking_metric = false),
    like_count integer not null check (like_count >= 0),
    like_metric_code text not null,
    like_metric_label text not null,
    like_as_of_date date not null,
    is_synthetic boolean not null check (is_synthetic = true),
    performance_based boolean not null check (performance_based = false),
    data_kind text not null default 'mock' check (data_kind = 'mock'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (return_period_start <= return_period_end)
);

alter table public.demo_investor_profiles enable row level security;
alter table public.demo_investor_profile_answers enable row level security;
alter table public.demo_public_portfolio_metrics enable row level security;

revoke all privileges on table public.demo_investor_profiles
    from anon, authenticated;
revoke all privileges on table public.demo_investor_profile_answers
    from anon, authenticated;
revoke all privileges on table public.demo_public_portfolio_metrics
    from anon, authenticated;

grant all privileges on table public.demo_investor_profiles to service_role;
grant all privileges on table public.demo_investor_profile_answers to service_role;
grant all privileges on table public.demo_public_portfolio_metrics to service_role;

comment on table public.demo_investor_profiles is
    '대표 시나리오 6명의 신한 배점 기반 합성 투자성향·투자 이유·후기';
comment on table public.demo_investor_profile_answers is
    '대표 시나리오 고객별 합성 투자성향 채점 답변 11개';
comment on table public.demo_public_portfolio_metrics is
    '대표 시나리오 공개 포트폴리오의 과거 목수익률과 합성 좋아요';
comment on column
    public.demo_public_portfolio_metrics.portfolio_trailing_12m_return_pct is
    '계좌잔액 가중 과거 12개월 목수익률. 미래 예측·공식 랭킹 지표가 아님';

"""


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sql_text(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return f"{_sql_text(rendered)}::jsonb"


def _sql_text_array(values: list[str]) -> str:
    return "array[" + ", ".join(_sql_text(value) for value in values) + "]::text[]"


def _profile_insert(
    profile_payload: dict[str, Any], users_by_code: dict[str, dict[str, Any]]
) -> str:
    rows = []
    for profile in profile_payload["profiles"]:
        code = str(profile["scenario_code"])
        values = (
            _sql_text(code),
            _sql_text(profile["assessment_id"]),
            _sql_text(profile["investor_profile"]),
            _sql_text(profile["investor_profile_label"]),
            str(int(profile["total_score"])),
            _sql_text(profile["score_band"]),
            _sql_text(profile["scenario_name"]),
            _sql_text(profile["scenario_description"]),
            _sql_text(profile["investment_reason"]),
            _sql_text(profile["portfolio_opinion_review"]),
            _sql_text_array(profile["representative_etf_isu_codes"]),
            _sql_text(profile["representative_etf_theme"]),
            _sql_text(profile["representative_etf_theme_review"]),
            _sql_text(profile["portfolio_consistency_note"]),
            _sql_json(profile["financial_product_shares_percent"]),
            _sql_json(profile["non_scored_answers"]),
            _sql_json(profile["portfolio_allocations"]),
            _sql_json(profile_payload["source_documents"]),
            _sql_text(profile_payload["rule_version"]),
            "true" if users_by_code[code]["is_demo_login_candidate"] else "false",
        )
        rows.append("        (" + ", ".join(values) + ")")

    return """insert into public.demo_investor_profiles (
    scenario_id, assessment_id, investor_profile, investor_profile_label,
    total_score, score_band, scenario_name, scenario_description,
    investment_reason, portfolio_opinion_review, representative_etf_isu_codes,
    representative_etf_theme, representative_etf_theme_review,
    portfolio_consistency_note, financial_product_shares_percent,
    non_scored_answers, portfolio_allocations, source_documents, rule_version,
    is_demo_login_candidate
)
select
    scenario.id, data.assessment_id, data.investor_profile,
    data.investor_profile_label, data.total_score, data.score_band,
    data.scenario_name, data.scenario_description, data.investment_reason,
    data.portfolio_opinion_review, data.representative_etf_isu_codes,
    data.representative_etf_theme, data.representative_etf_theme_review,
    data.portfolio_consistency_note, data.financial_product_shares_percent,
    data.non_scored_answers, data.portfolio_allocations, data.source_documents,
    data.rule_version, data.is_demo_login_candidate
from (values
""" + ",\n".join(rows) + """
) as data (
    scenario_code, assessment_id, investor_profile, investor_profile_label,
    total_score, score_band, scenario_name, scenario_description,
    investment_reason, portfolio_opinion_review, representative_etf_isu_codes,
    representative_etf_theme, representative_etf_theme_review,
    portfolio_consistency_note, financial_product_shares_percent,
    non_scored_answers, portfolio_allocations, source_documents, rule_version,
    is_demo_login_candidate
)
join public.mock_scenarios as scenario on scenario.code = data.scenario_code;

"""


def _answer_insert(profile_payload: dict[str, Any]) -> str:
    rows = []
    for profile in profile_payload["profiles"]:
        for answer in profile["answers"]:
            values = (
                _sql_text(profile["scenario_code"]),
                _sql_text(answer["question_code"]),
                _sql_text(answer["selected_option"]),
                str(int(answer["score"])),
                _sql_text(answer["basis"]),
            )
            rows.append("        (" + ", ".join(values) + ")")
    return """insert into public.demo_investor_profile_answers (
    scenario_id, question_code, selected_option, score, basis
)
select profile.scenario_id, data.question_code, data.selected_option,
       data.score, data.basis
from (values
""" + ",\n".join(rows) + """
) as data (scenario_code, question_code, selected_option, score, basis)
join public.mock_scenarios as scenario on scenario.code = data.scenario_code
join public.demo_investor_profiles as profile on profile.scenario_id = scenario.id;

"""


def _metric_insert(metric_payload: dict[str, Any]) -> str:
    return_metric = metric_payload["return_metric"]
    like_metric = metric_payload["like_metric"]
    rows = []
    for metric in metric_payload["profiles"]:
        values = (
            _sql_text(metric["scenario_code"]),
            _sql_text(metric["benchmark_user_id"]),
            str(metric["portfolio_trailing_12m_return_pct"]),
            _sql_text(metric["return_period_start"]),
            _sql_text(metric["return_period_end"]),
            _sql_text(return_metric["metric_code"]),
            _sql_text(return_metric["label"]),
            _sql_text(return_metric["calculation_basis"]),
            _sql_text(return_metric["source_label"]),
            "false",
            "false",
            str(int(metric["like_count"])),
            _sql_text(like_metric["metric_code"]),
            _sql_text(like_metric["label"]),
            _sql_text(like_metric["as_of_date"]),
            "true",
            "false",
        )
        rows.append("        (" + ", ".join(values) + ")")
    return """insert into public.demo_public_portfolio_metrics (
    scenario_id, benchmark_user_id, portfolio_trailing_12m_return_pct,
    return_period_start, return_period_end, return_metric_code,
    return_metric_label, return_calculation_basis, return_source_label,
    is_forecast, official_ranking_metric, like_count, like_metric_code,
    like_metric_label, like_as_of_date, is_synthetic, performance_based
)
select
    scenario.id, data.benchmark_user_id,
    data.portfolio_trailing_12m_return_pct, data.return_period_start::date,
    data.return_period_end::date, data.return_metric_code,
    data.return_metric_label, data.return_calculation_basis,
    data.return_source_label, data.is_forecast, data.official_ranking_metric,
    data.like_count, data.like_metric_code, data.like_metric_label,
    data.like_as_of_date::date, data.is_synthetic, data.performance_based
from (values
""" + ",\n".join(rows) + """
) as data (
    scenario_code, benchmark_user_id, portfolio_trailing_12m_return_pct,
    return_period_start, return_period_end, return_metric_code,
    return_metric_label, return_calculation_basis, return_source_label,
    is_forecast, official_ranking_metric, like_count, like_metric_code,
    like_metric_label, like_as_of_date, is_synthetic, performance_based
)
join public.mock_scenarios as scenario on scenario.code = data.scenario_code;

"""


def render() -> str:
    profile_payload = _load(MOCK_DIR / "demo_investor_profiles.json")
    metric_payload = _load(MOCK_DIR / "demo_public_portfolio_metrics.json")
    users = _load(MOCK_DIR / "demo_scenario_users.json")["users"]
    users_by_code = {str(user["scenario_code"]): user for user in users}
    profile_codes = {
        str(profile["scenario_code"]) for profile in profile_payload["profiles"]
    }
    metric_codes = {
        str(profile["scenario_code"]) for profile in metric_payload["profiles"]
    }
    if profile_codes != set(users_by_code) or metric_codes != set(users_by_code):
        raise ValueError("demo Supabase inputs must contain the same six scenarios")
    rendered = (
        DDL
        + _profile_insert(profile_payload, users_by_code)
        + _answer_insert(profile_payload)
        + _metric_insert(metric_payload)
    )
    return rendered.rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        is_stale = (
            not OUTPUT_PATH.exists()
            or OUTPUT_PATH.read_text(encoding="utf-8") != rendered
        )
        if is_stale:
            raise SystemExit("demo customer Supabase migration is stale")
        print("PASS: demo customer Supabase migration is current")
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.name}")


if __name__ == "__main__":
    main()
