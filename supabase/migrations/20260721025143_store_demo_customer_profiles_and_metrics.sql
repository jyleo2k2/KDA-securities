-- Store the complete six-customer demo assessment and public metric contract.
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

insert into public.demo_investor_profiles (
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
        ('dc_dormant', 'demo-profile-dc-dormant-v1', 'stable', '안정형', 15, '16점 이하', '안정형 DC 원금보존 중심', '투자 경험과 금융지식이 부족하고 원금 보존을 최우선으로 보아 DC 적립금을 방어자산 중심으로 유지하는 고객', '원금이 줄어드는 것이 부담스러워 DC 계좌는 원리금보장과 현금 위주로 두었습니다. ETF는 가격 변동이 낮은 채권형만 보유했습니다.', 'SOL 종합채권(AA-이상)액티브는 원리금보장·현금 중심 구성에서 금리 변동을 조금 경험하는 보조 자산으로 두었습니다. 장기 투자기간에도 원금 보존이 우선이라 채권 ETF 비중을 서둘러 늘리지는 않았습니다.', array['436140']::text[], '우량 종합채권·금리 변동 완충', '시장금리가 오르내리는 동안 채권 가격도 움직인다는 점을 경험해, SOL 종합채권(AA-이상)액티브를 현금보다 한 단계 높은 변동성의 분산 수단으로 보고 있습니다.', '일반 위험자산 0%, 채권·원리금보장·현금 100%로 안정형 판단을 반영한다.', '{"guaranteed": 70, "investment": 5, "loan": 0, "other": 25}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "없음", "vulnerable_financial_consumer": true}'::jsonb, '{"dc": {"bond": 20, "cash": 25, "deposit": 55, "domestic_equity": 0, "global_equity": 0}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', true),
        ('tax_contribution_uninvested', 'demo-profile-tax-contribution-v1', 'stable_seeking', '안정추구형', 23, '17~24점', '안정추구형 세액공제 후 단계적 운용', '세액공제를 먼저 챙겼지만 상품 이해가 부족해 현금으로 대기하다가 채권과 분산 ETF부터 단계적으로 운용하려는 고객', '세액공제 혜택부터 챙겼지만 상품 구조가 익숙하지 않아 납입금 일부를 현금성으로 남겨두었습니다. 채권 ETF와 분산지수 ETF부터 천천히 운용하려고 합니다.', 'RISE 종합채권(A-이상)액티브와 HANARO 미국S&P500을 함께 담으니 채권 안정성과 글로벌 분산을 한 번에 확인하기 쉬웠습니다. 물가·금리 불확실성이 이어지는 시기에는 현금을 한꺼번에 옮기기보다 분할해서 비중을 늘리는 방식이 맞았습니다.', array['385540', '432840']::text[], '우량채권·미국 대형주 분산', '세액공제 후 현금으로 남아 있던 자금을 RISE 종합채권과 HANARO 미국S&P500에 나누면서, 금리 변화와 미국 증시 변동을 동시에 감수하지 않도록 단계적으로 투자했습니다.', '각 계좌의 일반 위험자산을 20%로 제한하고 채권·현금·원리금보장 비중을 높여 안정추구형을 반영한다.', '{"guaranteed": 65, "investment": 5, "loan": 0, "other": 30}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "없음", "vulnerable_financial_consumer": false}'::jsonb, '{"irp": {"bond": 35, "cash": 20, "deposit": 25, "domestic_equity": 8, "global_equity": 12}, "pension_savings": {"bond": 50, "cash": 30, "domestic_equity": 8, "global_equity": 12}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', true),
        ('overlap_risk_concentration', 'demo-profile-overlap-risk-v1', 'active', '적극투자형', 39, '33~40점', '적극투자형 계좌 중복 점검', '시장수익률 수준의 성장을 추구해 주식 ETF 비중을 높였지만 익숙한 글로벌·헬스케어 자산을 여러 계좌에 반복 보유한 고객', '은퇴까지 시간이 남아 있어 주식 ETF 비중을 높였습니다. 다만 익숙한 글로벌·헬스케어 ETF를 계좌마다 반복해서 담아 중복 위험을 정기적으로 점검하고 있습니다.', 'HANARO 미국S&P500과 TIGER S&P글로벌헬스케어(합성)를 세 계좌에 반복 보유해 미국 대형주·헬스케어 흐름이 전체 연금자산을 함께 움직였습니다. 고령화에 따른 헬스케어 수요는 장기 테마로 봤지만, 지정학·달러 변동까지 겹치면 중복 보유가 분산이 아니라는 점을 확인했습니다.', array['432840', '248270']::text[], '미국 대형주·글로벌 헬스케어 중복', '미국 대형주 성장과 고령화·의료 수요 흐름을 함께 보고 두 ETF를 선택했지만, 동일 상품을 여러 계좌에 반복 보유해 테마 노출이 예상보다 커졌습니다.', 'DC·IRP는 일반 위험자산 65%, 연금저축은 70%로 적극투자형을 반영하되 계좌 한도를 지킨다.', '{"guaranteed": 20, "investment": 25, "loan": 5, "other": 50}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "없음", "vulnerable_financial_consumer": false}'::jsonb, '{"dc": {"bond": 20, "cash": 5, "deposit": 10, "domestic_equity": 25, "global_equity": 40}, "irp": {"bond": 20, "cash": 5, "deposit": 10, "domestic_equity": 20, "global_equity": 45}, "pension_savings": {"bond": 20, "cash": 10, "domestic_equity": 20, "global_equity": 50}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', true),
        ('young_retirement_distance', 'demo-profile-young-growth-v1', 'aggressive', '공격투자형', 44, '41점 이상', '공격투자형 장기 성장', '긴 투자기간과 높은 손실감내도를 바탕으로 성장자산 비중을 높이되 DC 위험자산 70% 한도를 지키는 청년 고객', '은퇴까지 시간이 많이 남아 단기 변동을 감수하고 글로벌 성장주 ETF 비중을 높였습니다. DC는 70% 한도를 지키고 연금저축은 장기 성장에 더 집중했습니다.', 'RISE 미국반도체NYSE와 ACE AI반도체TOP3+는 AI 데이터센터 투자 확대와 반도체 공급망 재편 흐름을 보고 선택했습니다. 26년 투자기간을 활용해 변동을 감수하되, 산업 사이클과 특정 종목 집중 위험은 별도로 점검하고 있습니다.', array['469060', '469150']::text[], 'AI 반도체·글로벌 공급망', '생성형 AI 확산으로 데이터센터와 첨단 반도체 투자가 늘어나는 산업 흐름에 주목했습니다. 다만 국가별 공급망 정책과 반도체 업황 사이클에 따라 변동이 커질 수 있어 장기 보유 중에도 비중을 확인합니다.', 'DC는 일반 위험자산 70%, 연금저축은 90%로 장기 공격투자형의 차이를 계좌 규칙 안에서 표현한다.', '{"guaranteed": 10, "investment": 40, "loan": 0, "other": 50}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "3년 이상", "vulnerable_financial_consumer": false}'::jsonb, '{"dc": {"bond": 20, "cash": 5, "deposit": 5, "domestic_equity": 20, "global_equity": 50}, "pension_savings": {"bond": 7, "cash": 3, "domestic_equity": 25, "global_equity": 65}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', true),
        ('family_budget_pressure', 'demo-profile-family-balance-v1', 'risk_neutral', '위험중립형', 32, '25~32점', '위험중립형 가계균형', '자녀·주거비 지출과 노후 준비를 함께 고려해 성장자산과 방어자산을 비슷한 수준으로 나누는 중년 고객', '자녀와 주거비 지출이 커서 추가 납입은 IRP 중심으로 하고 있습니다. 연금자산은 주식·채권·현금을 나눠 성장과 생활비 부담을 함께 고려했습니다.', 'TIGER 미국배당다우존스와 SOL 금융지주플러스고배당은 생활비 지출이 큰 상황에서도 배당 중심 기업의 현금흐름을 이해하기 쉬워 대표 테마로 삼았습니다. 금리·경기 변화에 따라 금융주와 배당주의 성과가 달라질 수 있어 채권·현금 비중을 함께 유지했습니다.', array['458730', '484880']::text[], '미국·국내 고배당 현금흐름', '가계지출로 추가 납입 여력이 제한돼 성장주만 좇기보다 미국 배당주와 국내 금융지주 고배당 테마를 대표 자산으로 골랐습니다. 금리 환경에 민감한 금융주 특성을 고려해 채권과 현금을 같이 보유합니다.', 'DC·IRP 일반 위험자산 45%, 연금저축 50%로 성장과 방어자산의 균형을 맞춘다.', '{"guaranteed": 20, "investment": 15, "loan": 40, "other": 25}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "없음", "vulnerable_financial_consumer": false}'::jsonb, '{"dc": {"bond": 25, "cash": 10, "deposit": 20, "domestic_equity": 20, "global_equity": 25}, "irp": {"bond": 25, "cash": 15, "deposit": 15, "domestic_equity": 15, "global_equity": 30}, "pension_savings": {"bond": 35, "cash": 15, "domestic_equity": 20, "global_equity": 30}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', true),
        ('pension_payout_transition', 'demo-profile-payout-stable-v1', 'stable', '안정형', 16, '16점 이하', '안정형 연금 수령 전환', '연금 수령 단계에 들어가 투자수익 확대보다 인출 재원과 자산 변동 축소를 우선하는 시연 로그인 제외 고객', '연금 수령 단계라 수익 확대보다 현금흐름과 자산 변동 축소가 중요합니다. 주식 ETF는 제외하고 채권·원리금보장·현금성 자산으로 인출 재원을 준비했습니다.', 'ACE 종합채권(AA-이상)액티브와 RISE 종합채권(A-이상)액티브를 중심으로 두되 인출 재원을 모두 ETF에 두지 않고 원리금보장·현금과 나눴습니다. 금리 전환기에 채권 평가금액도 움직일 수 있어 5년 수령 준비기간에는 유동성을 더 중요하게 봤습니다.', array['356540', '385540']::text[], '우량 종합채권·연금 인출 안정', '연금 수령을 앞두고 우량채권 ETF의 이자수익 기반과 가격 변동을 함께 살폈습니다. 시장금리 방향을 맞히기보다 현금성 자산을 별도로 두어 필요한 시점의 인출 재원을 확보했습니다.', '일반 위험자산 0%로 안정형을 반영하며, 시연 로그인 후보에서는 제외하고 공개 포트폴리오 비교 대상으로만 유지한다.', '{"guaranteed": 70, "investment": 5, "loan": 0, "other": 25}'::jsonb, '{"assessment_validity_consent": true, "derivative_experience": "없음", "vulnerable_financial_consumer": false}'::jsonb, '{"irp": {"bond": 40, "cash": 25, "deposit": 35, "domestic_equity": 0, "global_equity": 0}, "pension_savings": {"bond": 60, "cash": 40, "domestic_equity": 0, "global_equity": 0}}'::jsonb, '["docs/20_리서치/신한증권_투자권유준칙_투자자정보확인서_배점표.md", "docs/20_리서치/신한증권_투자성향진단_설문및점수로직.md"]'::jsonb, 'shinhan-personal-general-2021-05-20-demo-v1', false)
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

insert into public.demo_investor_profile_answers (
    scenario_id, question_code, selected_option, score, basis
)
select profile.scenario_id, data.question_code, data.selected_option,
       data.score, data.basis
from (values
        ('dc_dormant', 'q1_total_net_assets', '1억원 미만', 1, '대표 고객 합성 가정'),
        ('dc_dormant', 'q2_annual_income', '5천만원 이상~7천만원 미만', 3, '총급여 64,640,000원'),
        ('dc_dormant', 'q3_investment_product_share', '0~9%', 1, '투자성 상품 비중 합성 가정'),
        ('dc_dormant', 'q3_loan_product_share', '0~9%', 1, '대출성 상품 비중 합성 가정'),
        ('dc_dormant', 'q4_experienced_product', '투자경험 없음', 0, '방치형·투자 무관심 시나리오'),
        ('dc_dormant', 'q4_experience_period', '투자경험 없음', 0, '방치형·투자 무관심 시나리오'),
        ('dc_dormant', 'q6_financial_knowledge', '금융투자상품 투자 경험 없음', 1, 'investment_readiness=DISENGAGED'),
        ('dc_dormant', 'q7_investment_purpose', '생활비', 1, '원금 보존 우선 합성 가정'),
        ('dc_dormant', 'q8_risk_attitude', '투자수익보다 원금 보존이 중요', 1, 'preferred_management_type=PRINCIPAL_GUARANTEED'),
        ('dc_dormant', 'q9_investment_horizon', '5년 이상', 5, '은퇴 예정까지 26년'),
        ('dc_dormant', 'q10_loss_tolerance', '제한적 손실·시중금리 수준 수익 기대', 1, '안정형 손실감내 합성 응답'),
        ('tax_contribution_uninvested', 'q1_total_net_assets', '1억원 미만', 1, '대표 고객 합성 가정'),
        ('tax_contribution_uninvested', 'q2_annual_income', '5천만원 이상~7천만원 미만', 3, '총급여 61,730,000원'),
        ('tax_contribution_uninvested', 'q3_investment_product_share', '0~9%', 1, '현금대기형 투자성 상품 비중'),
        ('tax_contribution_uninvested', 'q3_loan_product_share', '0~9%', 1, '대출성 상품 비중 합성 가정'),
        ('tax_contribution_uninvested', 'q4_experienced_product', '채권형펀드 등 저위험 상품', 3, '안정투자 선호 합성 경험'),
        ('tax_contribution_uninvested', 'q4_experience_period', '1년 미만', 1, '상품 이해 부족 시나리오'),
        ('tax_contribution_uninvested', 'q6_financial_knowledge', '주식·채권·펀드 구조와 위험을 일정 부분 이해', 3, 'investment_readiness=NEEDS_GUIDANCE'),
        ('tax_contribution_uninvested', 'q7_investment_purpose', '자산증식', 3, '연금자산 장기 증식 목적'),
        ('tax_contribution_uninvested', 'q8_risk_attitude', '투자수익보다 원금 보존이 중요', 1, '안정투자 선호'),
        ('tax_contribution_uninvested', 'q9_investment_horizon', '5년 이상', 5, '은퇴 예정까지 17년'),
        ('tax_contribution_uninvested', 'q10_loss_tolerance', '제한적 손실·시중금리 수준 수익 기대', 1, '안정추구형 하단 손실감내 합성 응답'),
        ('overlap_risk_concentration', 'q1_total_net_assets', '5억원 이상~10억원 미만', 3, '대표 고객 합성 가정'),
        ('overlap_risk_concentration', 'q2_annual_income', '7천만원 이상~1억원 미만', 4, '총급여 97,500,000원'),
        ('overlap_risk_concentration', 'q3_investment_product_share', '20~29%', 3, '투자성 상품 비중 합성 가정'),
        ('overlap_risk_concentration', 'q3_loan_product_share', '0~9%', 1, '대출성 상품 비중 합성 가정'),
        ('overlap_risk_concentration', 'q4_experienced_product', '주식·주식형펀드 등 고위험 상품', 5, '복수 계좌 주식 ETF 보유 경험'),
        ('overlap_risk_concentration', 'q4_experience_period', '3년 이상', 5, '적극투자형 합성 경험'),
        ('overlap_risk_concentration', 'q6_financial_knowledge', '일반 금융투자상품 구조와 위험을 깊이 이해', 4, '복수 계좌 직접 운용'),
        ('overlap_risk_concentration', 'q7_investment_purpose', '자산증식', 3, '장기 성장 목적'),
        ('overlap_risk_concentration', 'q8_risk_attitude', '원금 보존을 고려하나 투자수익이 더 중요', 3, '적극투자 선호'),
        ('overlap_risk_concentration', 'q9_investment_horizon', '5년 이상', 5, '은퇴 예정까지 18년'),
        ('overlap_risk_concentration', 'q10_loss_tolerance', '원금 일부 손실·시중금리보다 높은 수익 기대', 3, '적극투자형 손실감내 합성 응답'),
        ('young_retirement_distance', 'q1_total_net_assets', '1억원 미만', 1, '대표 고객 합성 가정'),
        ('young_retirement_distance', 'q2_annual_income', '2천만원 이상~5천만원 미만', 2, '총급여 38,810,000원'),
        ('young_retirement_distance', 'q3_investment_product_share', '30~49%', 4, '성장자산 중심 합성 가정'),
        ('young_retirement_distance', 'q3_loan_product_share', '0~9%', 1, '대출성 상품 비중 합성 가정'),
        ('young_retirement_distance', 'q4_experienced_product', '초고위험 금융투자상품', 6, '공격투자형 시연을 위한 합성 경험'),
        ('young_retirement_distance', 'q4_experience_period', '3년 이상', 5, '20대부터의 투자 경험 합성 가정'),
        ('young_retirement_distance', 'q6_financial_knowledge', '파생상품을 포함한 대부분의 상품 구조와 위험 이해', 5, '공격투자형 시연을 위한 합성 응답'),
        ('young_retirement_distance', 'q7_investment_purpose', '자산증식', 3, '장기 성장 목적'),
        ('young_retirement_distance', 'q8_risk_attitude', '손실 위험이 있더라도 투자수익이 더 중요', 5, '높은 손실감내'),
        ('young_retirement_distance', 'q9_investment_horizon', '5년 이상', 5, '은퇴 예정까지 26년'),
        ('young_retirement_distance', 'q10_loss_tolerance', '원금 초과 손실 감수·시장수익률 초과 추구', 7, '공격투자형 손실감내 합성 응답'),
        ('family_budget_pressure', 'q1_total_net_assets', '1억원 미만', 1, '연금자산 88,660,000원과 대표 고객 합성 가정'),
        ('family_budget_pressure', 'q2_annual_income', '5천만원 이상~7천만원 미만', 3, '총급여 54,050,000원'),
        ('family_budget_pressure', 'q3_investment_product_share', '10~19%', 2, '가계지출 압박을 반영한 합성 가정'),
        ('family_budget_pressure', 'q3_loan_product_share', '30~49%', 4, '주거비 부담을 반영한 합성 가정'),
        ('family_budget_pressure', 'q4_experienced_product', '혼합형펀드 등 중위험 상품', 4, '중립투자 선호 합성 경험'),
        ('family_budget_pressure', 'q4_experience_period', '1년 이상~3년 미만', 3, '중년기 연금 운용 경험 합성 가정'),
        ('family_budget_pressure', 'q6_financial_knowledge', '주식·채권·펀드 구조와 위험을 일정 부분 이해', 3, '중립투자 선호'),
        ('family_budget_pressure', 'q7_investment_purpose', '교육비', 1, '자녀 지출 시나리오'),
        ('family_budget_pressure', 'q8_risk_attitude', '원금 보존을 고려하나 투자수익이 더 중요', 3, '위험중립형 태도'),
        ('family_budget_pressure', 'q9_investment_horizon', '5년 이상', 5, '은퇴 예정까지 13년'),
        ('family_budget_pressure', 'q10_loss_tolerance', '원금 일부 손실·시중금리보다 높은 수익 기대', 3, '위험중립형 손실감내 합성 응답'),
        ('pension_payout_transition', 'q1_total_net_assets', '1억원 이상~5억원 미만', 2, '연금자산 157,430,000원과 대표 고객 합성 가정'),
        ('pension_payout_transition', 'q2_annual_income', '5천만원 이상~7천만원 미만', 3, '종합소득금액 53,440,000원'),
        ('pension_payout_transition', 'q3_investment_product_share', '0~9%', 1, '수령 전환기 투자성 상품 비중'),
        ('pension_payout_transition', 'q3_loan_product_share', '0~9%', 1, '대출성 상품 비중 합성 가정'),
        ('pension_payout_transition', 'q4_experienced_product', '국채·MMF 등 초저위험 상품', 1, '수령 전환기 방어자산 경험'),
        ('pension_payout_transition', 'q4_experience_period', '1년 미만', 1, '현재 인출용 운용 구간 합성 응답'),
        ('pension_payout_transition', 'q6_financial_knowledge', '주식·채권·펀드 구조와 위험을 일정 부분 이해', 3, '증권자산 보유 경험'),
        ('pension_payout_transition', 'q7_investment_purpose', '생활비', 1, '연금 수령 목적'),
        ('pension_payout_transition', 'q8_risk_attitude', '투자수익보다 원금 보존이 중요', 1, '수령기 안정성 우선'),
        ('pension_payout_transition', 'q9_investment_horizon', '1년 미만', 1, '현재 인출 재원의 운용기간'),
        ('pension_payout_transition', 'q10_loss_tolerance', '제한적 손실·시중금리 수준 수익 기대', 1, '안정형 손실감내 합성 응답')
) as data (scenario_code, question_code, selected_option, score, basis)
join public.mock_scenarios as scenario on scenario.code = data.scenario_code
join public.demo_investor_profiles as profile on profile.scenario_id = scenario.id;

insert into public.demo_public_portfolio_metrics (
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
        ('dc_dormant', 'USR09660', 7.72, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 126, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false),
        ('tax_contribution_uninvested', 'USR00540', 11.20, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 284, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false),
        ('overlap_risk_concentration', 'USR03419', 11.16, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 173, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false),
        ('young_retirement_distance', 'USR08633', 0.74, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 412, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false),
        ('family_budget_pressure', 'USR00109', 12.79, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 358, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false),
        ('pension_payout_transition', 'USR08609', 4.69, '2025-01-01', '2025-12-31', 'balance_weighted_trailing_12m_mock_return', '과거 12개월 계좌잔액 가중 합성수익률', 'Σ(계좌잔액×계좌 과거 12개월 수익률)÷총 계좌잔액', 'data/mock/accounts.csv 합성 계좌 수익률', false, false, 97, 'synthetic_demo_like_count', '추천(좋아요)', '2026-07-21', true, false)
) as data (
    scenario_code, benchmark_user_id, portfolio_trailing_12m_return_pct,
    return_period_start, return_period_end, return_metric_code,
    return_metric_label, return_calculation_basis, return_source_label,
    is_forecast, official_ranking_metric, like_count, like_metric_code,
    like_metric_label, like_as_of_date, is_synthetic, performance_based
)
join public.mock_scenarios as scenario on scenario.code = data.scenario_code;
