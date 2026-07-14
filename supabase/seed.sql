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
    ('dc_dormant', 'DC형 방치', 'DC 적립금이 원리금보장 상품에만 머문 설명용 시나리오', '40대', 'balanced', 20),
    ('tax_contribution_uninvested', '세액공제 후 미운용', '세액공제를 위해 납입했지만 IRP·연금저축 자금이 현금성 자산에 머문 설명용 시나리오', '30대', 'balanced', 25),
    ('overlap_risk_concentration', '계좌별 중복·위험 편중', '세 계좌에 같은 글로벌 주식 노출이 반복되고 위험자산 비중이 높은 설명용 시나리오', '30대', 'growth', 28)
on conflict (code) do update set
    name = excluded.name,
    description = excluded.description,
    age_band = excluded.age_band,
    risk_profile = excluded.risk_profile,
    investment_horizon_years = excluded.investment_horizon_years,
    is_active = true,
    updated_at = now();

with account_seed (scenario_code, account_type, label, balance_krw) as (
    values
        ('dc_dormant', 'dc', '회사 DC', 60000000::numeric),
        ('tax_contribution_uninvested', 'irp', '개인 IRP', 30000000::numeric),
        ('tax_contribution_uninvested', 'pension_savings', '연금저축펀드', 20000000::numeric),
        ('overlap_risk_concentration', 'dc', '회사 DC', 100000000::numeric),
        ('overlap_risk_concentration', 'irp', '개인 IRP', 50000000::numeric),
        ('overlap_risk_concentration', 'pension_savings', '연금저축펀드', 40000000::numeric)
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
        ('overlap_risk_concentration', 'pension_savings', '연금저축펀드', 'cash', '현금성 모형', 4000000::numeric, 'capital_preservation', null)
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
    'project://docs/20_리서치/연금_기초.md#4-2',
    date '2026-07-13',
    'permitted',
    'DC형과 IRP는 일반 위험자산을 적립금의 70%까지 운용할 수 있다. 적격 TDF와 디폴트옵션 등 법정 예외는 적격성을 확인해 별도 처리한다. 연금저축펀드에는 같은 위험자산 총량 70% 한도를 적용하지 않는다.',
    '{"contains_personal_data":false,"knowledge_kind":"project_verified_summary"}'::jsonb
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
    '{"contains_personal_data":false,"knowledge_kind":"project_verified_summary"}'::jsonb
from public.knowledge_documents as kd
join public.data_sources as ds on ds.id = kd.source_id
where ds.code = 'project_verified_knowledge'
  and kd.source_url = 'project://docs/20_리서치/연금_기초.md#4-2'
on conflict (document_id, chunk_index) do update set
    content = excluded.content,
    metadata = excluded.metadata;
