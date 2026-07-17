insert into public.data_sources (
    code, name, source_type, authority, base_url, default_source_unit, metadata
)
values
    (
        'fss_ps_corp_list',
        '통합연금포털 연금저축 회사별 수익률·수수료율',
        'regulator_api',
        '금융감독원',
        'https://www.fss.or.kr/openapi/api/psCorpList.json',
        'million_krw',
        '{"request_unit_note":"API 응답에는 단위가 포함되지 않으며 프로젝트 검증 문서의 백만원 표기를 적용한다."}'::jsonb
    ),
    (
        'fss_rp_corp_result_list',
        '통합연금포털 퇴직연금 사업자별 수익률',
        'regulator_api',
        '금융감독원',
        'https://www.fss.or.kr/openapi/api/rpCorpResultList.json',
        'hundred_million_krw',
        '{"request_unit_note":"API 응답에는 단위가 포함되지 않으며 프로젝트 검증 문서의 억원 표기를 적용한다."}'::jsonb
    ),
    (
        'naver_search_news',
        'NAVER API HUB 뉴스 검색',
        'news_api',
        'NAVER Cloud',
        'https://naverapihub.apigw.ntruss.com/search/v1/news',
        null,
        '{"storage_policy":"제목·설명·링크·발행시각 등 검색 메타데이터만 저장하고 기사 본문은 저장하지 않는다."}'::jsonb
    ),
    (
        'retirement_pension_official_rules',
        '퇴직연금 공식 규칙 근거',
        'official_document',
        '국가법령정보센터·금융감독원',
        'https://www.law.go.kr',
        null,
        '{"project_reference":"docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준"}'::jsonb
    ),
    (
        'project_verified_knowledge',
        '연금 코파일럿 검증 지식',
        'curated',
        '연금 코파일럿 팀',
        'project://docs',
        null,
        '{"scope":"공식 근거를 프로젝트가 요약·검증한 RAG 데모 지식"}'::jsonb
    )
on conflict (code) do update set
    name = excluded.name,
    source_type = excluded.source_type,
    authority = excluded.authority,
    base_url = excluded.base_url,
    default_source_unit = excluded.default_source_unit,
    metadata = excluded.metadata,
    is_active = true,
    updated_at = now();

insert into public.asset_classes (code, name, is_general_risky, sort_order)
values
    ('cash', '현금성 자산', false, 10),
    ('deposit', '원리금보장 예금', false, 20),
    ('bond', '채권', false, 30),
    ('domestic_equity', '국내 주식', true, 40),
    ('global_equity', '글로벌 주식', true, 50),
    ('alternative', '대체자산', true, 60),
    ('eligible_tdf', '적격 TDF', false, 70),
    ('default_option', '디폴트옵션', false, 80)
on conflict (code) do update set
    name = excluded.name,
    is_general_risky = excluded.is_general_risky,
    sort_order = excluded.sort_order;

insert into public.mock_scenarios (
    code, name, description, age_band, risk_profile, investment_horizon_years
)
values
    ('dc_dormant', 'DC형 방치', E'회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객\n비고: 납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음', '40대', 'balanced', 20),
    ('tax_contribution_uninvested', '세액공제 후 미운용', E'세액공제를 위해 납입했지만 IRP·연금저축을 실제 운용하지 않은 고객\n비고: 각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음', '30대', 'balanced', 25),
    ('overlap_risk_concentration', '계좌별 중복·위험 편중', 'DC·IRP·연금저축에 글로벌주식형 자산이 중복되어 위험자산 편중이 있는 고객', '30대', 'growth', 28),
    ('young_retirement_distance', '연금이 멀게 느껴지는 청년층', '노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 청년층 고객', '20~39세', 'balanced', 35),
    ('family_budget_pressure', '가계지출로 납입이 빠듯한 중년층', '자녀·주거비로 추가 납입은 빠듯하지만 노후 준비를 걱정하기 시작한 중년층 고객', '40~54세', 'balanced', 13),
    ('pension_payout_transition', '연금 수령을 시작하는 55세 이상', '55세 이상으로 연금 수령을 시작했거나 수령 직전이라 수령 기간·세금·자산 안정성을 실제로 검토하는 설명용 시나리오', '55세 이상', 'conservative', 1)
on conflict (code) do update set
    name = excluded.name,
    description = excluded.description,
    age_band = excluded.age_band,
    risk_profile = excluded.risk_profile,
    investment_horizon_years = excluded.investment_horizon_years,
    is_active = true,
    updated_at = now();

with contribution_seed (
    auth_user_id, pension_savings_contribution_krw, irp_contribution_krw
) as (
    values
        ('0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid, 0::numeric, 0::numeric),
        ('1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid, 3000000::numeric, 6000000::numeric),
        ('2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid, 1500000::numeric, 2000000::numeric),
        ('306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid, 2000000::numeric, 0::numeric),
        ('417ec083-71a2-4242-95e4-b155e6fb5005'::uuid, 2400000::numeric, 2400000::numeric)
)
update public.demo_user_financial_context as context
set pension_savings_contribution_krw = seed.pension_savings_contribution_krw,
    irp_contribution_krw = seed.irp_contribution_krw,
    updated_at = now()
from contribution_seed as seed
where context.auth_user_id = seed.auth_user_id;

with account_seed (scenario_code, account_type, label, balance_krw) as (
    values
        ('dc_dormant', 'dc', '회사 DC', 60000000::numeric),
        ('tax_contribution_uninvested', 'irp', '개인 IRP', 30000000::numeric),
        ('tax_contribution_uninvested', 'pension_savings', '연금저축펀드', 20000000::numeric),
        ('overlap_risk_concentration', 'dc', '회사 DC', 100000000::numeric),
        ('overlap_risk_concentration', 'irp', '개인 IRP', 50000000::numeric),
        ('overlap_risk_concentration', 'pension_savings', '연금저축펀드', 40000000::numeric),
        ('young_retirement_distance', 'dc', '초기 직장 DC', 18000000::numeric),
        ('young_retirement_distance', 'pension_savings', '소액 연금저축펀드', 3600000::numeric),
        ('family_budget_pressure', 'dc', '회사 DC', 65000000::numeric),
        ('family_budget_pressure', 'irp', '개인 IRP', 12000000::numeric),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 9000000::numeric),
        ('pension_payout_transition', 'irp', '수령기 IRP', 110000000::numeric),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 45000000::numeric)
)
insert into public.mock_accounts (scenario_id, account_type, label, balance_krw)
select ms.id, account_seed.account_type, account_seed.label, account_seed.balance_krw
from account_seed
join public.mock_scenarios as ms on ms.code = account_seed.scenario_code
on conflict (scenario_id, account_type, label) do update set
    balance_krw = excluded.balance_krw;

with holding_seed (
    scenario_code, account_type, account_label, asset_code, instrument_name,
    market_value_krw, risk_treatment, statutory_exception
) as (
    values
        ('dc_dormant', 'dc', '회사 DC', 'deposit', '원리금보장 모형', 60000000::numeric, 'capital_preservation', null),
        ('tax_contribution_uninvested', 'irp', '개인 IRP', 'cash', 'IRP 현금성 모형', 30000000::numeric, 'capital_preservation', null),
        ('tax_contribution_uninvested', 'pension_savings', '연금저축펀드', 'cash', '연금저축 현금성 모형', 20000000::numeric, 'capital_preservation', null),
        ('overlap_risk_concentration', 'dc', '회사 DC', 'global_equity', '글로벌주식형 모형', 60000000::numeric, 'general_risky', null),
        ('overlap_risk_concentration', 'dc', '회사 DC', 'eligible_tdf', '적격 TDF 모형', 20000000::numeric, 'statutory_exception', 'eligible_tdf'),
        ('overlap_risk_concentration', 'dc', '회사 DC', 'deposit', '원리금보장 모형', 20000000::numeric, 'capital_preservation', null),
        ('overlap_risk_concentration', 'irp', '개인 IRP', 'global_equity', '글로벌주식형 모형', 34000000::numeric, 'general_risky', null),
        ('overlap_risk_concentration', 'irp', '개인 IRP', 'bond', '채권형 모형', 16000000::numeric, 'capital_preservation', null),
        ('overlap_risk_concentration', 'pension_savings', '연금저축펀드', 'global_equity', '글로벌주식형 모형', 36000000::numeric, 'general_risky', null),
        ('overlap_risk_concentration', 'pension_savings', '연금저축펀드', 'cash', '현금성 모형', 4000000::numeric, 'capital_preservation', null),
        ('young_retirement_distance', 'dc', '초기 직장 DC', 'deposit', '초기 DC 원리금보장 모형', 15000000::numeric, 'capital_preservation', null),
        ('young_retirement_distance', 'dc', '초기 직장 DC', 'cash', '초기 DC 현금성 모형', 3000000::numeric, 'capital_preservation', null),
        ('young_retirement_distance', 'pension_savings', '소액 연금저축펀드', 'cash', '연금저축 현금성 모형', 3600000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'deposit', '중년층 DC 원리금보장 모형', 35000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'global_equity', '중년층 글로벌주식형 모형', 20000000::numeric, 'general_risky', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'bond', '중년층 채권형 모형', 10000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'irp', '개인 IRP', 'deposit', '중년층 IRP 원리금보장 모형', 8000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'irp', '개인 IRP', 'cash', '중년층 IRP 현금성 모형', 4000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 'global_equity', '중년층 연금저축 글로벌주식형 모형', 5000000::numeric, 'general_risky', null),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 'bond', '중년층 연금저축 채권형 모형', 4000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'deposit', '수령기 IRP 원리금보장 모형', 60000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'bond', '수령기 IRP 채권형 모형', 30000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'cash', '수령기 IRP 현금성 모형', 20000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'bond', '수령기 연금저축 채권형 모형', 25000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'cash', '수령기 연금저축 현금성 모형', 15000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'global_equity', '수령기 연금저축 글로벌주식형 모형', 5000000::numeric, 'general_risky', null)
)
insert into public.mock_holdings (
    account_id, asset_class_id, instrument_name, market_value_krw,
    risk_treatment, statutory_exception
)
select
    ma.id, ac.id, hs.instrument_name, hs.market_value_krw,
    hs.risk_treatment, hs.statutory_exception
from holding_seed as hs
join public.mock_scenarios as ms on ms.code = hs.scenario_code
join public.mock_accounts as ma
    on ma.scenario_id = ms.id
   and ma.account_type = hs.account_type
   and ma.label = hs.account_label
join public.asset_classes as ac on ac.code = hs.asset_code
on conflict (account_id, instrument_name) do update set
    asset_class_id = excluded.asset_class_id,
    market_value_krw = excluded.market_value_krw,
    risk_treatment = excluded.risk_treatment,
    statutory_exception = excluded.statutory_exception;

insert into public.mock_public_profiles (
    code, nickname, age_band, risk_profile, investment_horizon_years
)
values
    ('peer_conservative', '차분한거북이', '50대', 'conservative', 8),
    ('peer_balanced', '균형잡힌나무', '40대', 'balanced', 18),
    ('peer_growth', '긴호흡고래', '30대', 'growth', 28)
on conflict (code) do update set
    nickname = excluded.nickname,
    age_band = excluded.age_band,
    risk_profile = excluded.risk_profile,
    investment_horizon_years = excluded.investment_horizon_years;

with portfolio_seed (profile_code, snapshot_date, title, description, asset_range_label) as (
    values
        ('peer_conservative', date '2026-07-14', '은퇴 근접 안정형 구성', '원리금보장과 채권 비중을 높인 모형 포트폴리오', '5천만~1억원'),
        ('peer_balanced', date '2026-07-14', '중기 균형형 구성', '주식과 방어자산을 비슷하게 나눈 모형 포트폴리오', '1억~2억원'),
        ('peer_growth', date '2026-07-14', '장기 성장형 구성', '장기 투자기간을 전제로 성장자산 비중을 높인 모형 포트폴리오', '1억~2억원')
)
insert into public.mock_public_portfolios (
    profile_id, snapshot_date, title, description, asset_range_label
)
select mpp.id, ps.snapshot_date, ps.title, ps.description, ps.asset_range_label
from portfolio_seed as ps
join public.mock_public_profiles as mpp on mpp.code = ps.profile_code
on conflict (profile_id, snapshot_date) do update set
    title = excluded.title,
    description = excluded.description,
    asset_range_label = excluded.asset_range_label,
    is_published = true;

with allocation_seed (profile_code, snapshot_date, asset_code, allocation_percent) as (
    values
        ('peer_conservative', date '2026-07-14', 'domestic_equity', 25.0::numeric),
        ('peer_conservative', date '2026-07-14', 'bond', 35.0::numeric),
        ('peer_conservative', date '2026-07-14', 'deposit', 40.0::numeric),
        ('peer_balanced', date '2026-07-14', 'global_equity', 50.0::numeric),
        ('peer_balanced', date '2026-07-14', 'bond', 30.0::numeric),
        ('peer_balanced', date '2026-07-14', 'deposit', 20.0::numeric),
        ('peer_growth', date '2026-07-14', 'global_equity', 65.0::numeric),
        ('peer_growth', date '2026-07-14', 'eligible_tdf', 20.0::numeric),
        ('peer_growth', date '2026-07-14', 'cash', 15.0::numeric)
)
insert into public.mock_public_portfolio_holdings (portfolio_id, asset_class_id, allocation_percent)
select mpp.id, ac.id, als.allocation_percent
from allocation_seed as als
join public.mock_public_profiles as profile on profile.code = als.profile_code
join public.mock_public_portfolios as mpp
    on mpp.profile_id = profile.id
   and mpp.snapshot_date = als.snapshot_date
join public.asset_classes as ac on ac.code = als.asset_code
on conflict (portfolio_id, asset_class_id) do update set
    allocation_percent = excluded.allocation_percent;

insert into public.rule_sets (
    code, version, name, status, effective_from, description
)
values (
    'pension_account_core',
    '2026-07-13',
    '연금계좌 핵심 운용 규칙',
    'active',
    date '2026-07-13',
    'DC형·IRP·연금저축계좌의 위험자산 한도와 법정 예외를 계좌별로 분리한 규칙 세트'
)
on conflict (code, version) do update set
    name = excluded.name,
    status = excluded.status,
    effective_from = excluded.effective_from,
    description = excluded.description;

with rule_seed (
    rule_code, account_type, rule_kind, parameters, rationale, source_locator, is_exception
) as (
    values
        (
            'GENERAL_RISK_ASSET_CAP', 'dc', 'risk_cap',
            '{"max_percent":"70","included_treatments":["general_risky"]}'::jsonb,
            'DC형은 일반 위험자산 비중을 적립금의 70% 이내로 판정한다.',
            'docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준', false
        ),
        (
            'GENERAL_RISK_ASSET_CAP', 'irp', 'risk_cap',
            '{"max_percent":"70","included_treatments":["general_risky"]}'::jsonb,
            'IRP는 일반 위험자산 비중을 적립금의 70% 이내로 판정한다.',
            'docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준', false
        ),
        (
            'GENERAL_RISK_ASSET_CAP', 'pension_savings', 'risk_cap',
            '{"max_percent":null,"included_treatments":["general_risky"]}'::jsonb,
            '연금저축펀드에는 DC형·IRP와 같은 위험자산 총량 70% 한도를 적용하지 않는다.',
            'docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준', false
        ),
        (
            'ELIGIBLE_PRODUCT_EXCEPTION', 'dc', 'product_eligibility',
            '{"treatments":["eligible_tdf","default_option"],"requires_explicit_eligibility":true}'::jsonb,
            '적격 TDF·디폴트옵션 등 예외는 일반 상품에 자동 적용하지 않고 적격성이 확인된 경우에만 별도 처리한다.',
            'docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준', true
        ),
        (
            'ELIGIBLE_PRODUCT_EXCEPTION', 'irp', 'product_eligibility',
            '{"treatments":["eligible_tdf","default_option"],"requires_explicit_eligibility":true}'::jsonb,
            '적격 TDF·디폴트옵션 등 예외는 일반 상품에 자동 적용하지 않고 적격성이 확인된 경우에만 별도 처리한다.',
            'docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준', true
        )
)
insert into public.pension_rules (
    rule_set_id, source_id, rule_code, account_type, rule_kind,
    parameters, rationale, source_locator, is_exception
)
select
    rs.id,
    ds.id,
    r.rule_code,
    r.account_type,
    r.rule_kind,
    r.parameters,
    r.rationale,
    r.source_locator,
    r.is_exception
from rule_seed as r
join public.rule_sets as rs
    on rs.code = 'pension_account_core' and rs.version = '2026-07-13'
join public.data_sources as ds on ds.code = 'retirement_pension_official_rules'
on conflict (rule_set_id, rule_code, account_type) do update set
    source_id = excluded.source_id,
    rule_kind = excluded.rule_kind,
    parameters = excluded.parameters,
    rationale = excluded.rationale,
    source_locator = excluded.source_locator,
    is_exception = excluded.is_exception;

insert into public.knowledge_documents (
    source_id, document_type, title, publisher, source_url,
    as_of_date, license_status, content, metadata
)
select
    ds.id,
    'research',
    '세 연금계좌의 위험자산 규칙 검증 요약',
    '연금 코파일럿 팀',
    'project://docs/20_리서치/연금_기초.md',
    date '2026-07-13',
    'permitted',
    'DC형과 IRP는 일반 위험자산을 적립금의 70%까지 운용할 수 있다. 적격 TDF와 디폴트옵션 등 법정 예외는 적격성을 확인해 별도 처리한다. 연금저축펀드에는 같은 위험자산 총량 70% 한도를 적용하지 않는다.',
    '{"contains_personal_data":false,"data_boundary":"verified_knowledge","is_mock":false,"knowledge_kind":"project_verified_document"}'::jsonb
from public.data_sources as ds
where ds.code = 'project_verified_knowledge'
on conflict (source_id, source_url) do update set
    title = excluded.title,
    as_of_date = excluded.as_of_date,
    license_status = excluded.license_status,
    content = excluded.content,
    metadata = excluded.metadata,
    updated_at = now();

insert into public.knowledge_chunks (
    document_id, chunk_index, content, metadata
)
select
    kd.id,
    0,
    kd.content,
    '{"contains_personal_data":false,"data_boundary":"verified_knowledge","is_mock":false,"is_active":true,"knowledge_kind":"project_verified_document"}'::jsonb
from public.knowledge_documents as kd
join public.data_sources as ds on ds.id = kd.source_id
where ds.code = 'project_verified_knowledge'
  and kd.source_url = 'project://docs/20_리서치/연금_기초.md'
on conflict (document_id, chunk_index) do update set
    content = excluded.content,
    metadata = excluded.metadata;
