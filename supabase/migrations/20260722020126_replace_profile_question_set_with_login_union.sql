-- The login investor-information form is the only profile questionnaire.
-- Its contextual questions are retained with a zero score; the Shinhan
-- personal-general fields alone determine the 56-point investment profile.

alter table public.profile_question_options
    drop constraint profile_question_options_score_check;
alter table public.profile_question_options
    add constraint profile_question_options_score_check check (score between 0 and 7);

alter table public.investment_profile_answers
    drop constraint investment_profile_answers_selected_score_check;
alter table public.investment_profile_answers
    add constraint investment_profile_answers_selected_score_check
    check (selected_score between 0 and 7);
alter table public.investment_profile_answers
    drop constraint investment_profile_answers_assessment_id_question_id_key;
alter table public.investment_profile_answers
    add constraint investment_profile_answers_assessment_question_option_key
    unique (assessment_id, question_id, option_id);

update public.profile_question_sets
set status = 'retired', effective_to = date '2026-07-21'
where status = 'active';

with inserted_set as (
    insert into public.profile_question_sets (
        version, status, effective_from, engine_name, engine_version,
        rule_version, provisional
    ) values (
        '2026-07-22-login-union-v1', 'active', date '2026-07-22',
        'investor_profile', '2026-07-22.1',
        'shinhan-personal-general-login-union-2026-07-22', false
    ) returning id
), inserted_questions as (
    insert into public.profile_questions (question_set_id, code, topic, display_order)
    select inserted_set.id, item.code, item.topic, item.display_order
    from inserted_set
    cross join jsonb_to_recordset($questions$
      [
        {"code":"age_band","topic":"연령대","display_order":1},
        {"code":"total_net_assets","topic":"총 자산규모(순자산)","display_order":2},
        {"code":"annual_income","topic":"연간 소득 현황","display_order":3},
        {"code":"financial_asset_share","topic":"전체 자산 중 금융자산 비중","display_order":4},
        {"code":"investment_product_share","topic":"총자산 대비 투자성 상품 비중","display_order":5},
        {"code":"loan_product_share","topic":"총자산 대비 대출성 상품 비중","display_order":6},
        {"code":"investment_experience_product","topic":"투자경험이 있는 금융투자상품","display_order":7},
        {"code":"investment_experience_period","topic":"금융투자상품 투자경험 기간","display_order":8},
        {"code":"investment_purpose","topic":"금융투자상품 취득 및 처분 목적","display_order":9},
        {"code":"financial_knowledge","topic":"금융상품 지식 수준","display_order":10},
        {"code":"investment_horizon","topic":"현재 투자자금의 투자예정기간","display_order":11},
        {"code":"risk_attitude","topic":"투자수익 및 위험에 대한 태도","display_order":12},
        {"code":"loss_tolerance","topic":"기대수익률 및 손실감내도","display_order":13},
        {"code":"derivative_experience","topic":"파생상품 투자경험","display_order":14},
        {"code":"vulnerable_investor","topic":"취약 금융소비자 여부","display_order":15},
        {"code":"validity_consent","topic":"투자자정보 유효기간 설정 동의","display_order":16},
        {"code":"retirement_start_age","topic":"연금 수령 개시 나이","display_order":17}
      ]
    $questions$) as item(code text, topic text, display_order smallint)
    returning id, code
), options as (
    select * from jsonb_to_recordset($options$
      [
        {"q":"age_band","v":"under_19","l":"만19세 미만","s":0,"o":1},{"q":"age_band","v":"19_to_40","l":"만19세~만40세","s":0,"o":2},{"q":"age_band","v":"41_to_50","l":"만41세~만50세","s":0,"o":3},{"q":"age_band","v":"51_to_64","l":"만51세~만64세","s":0,"o":4},{"q":"age_band","v":"65_to_79","l":"만65세~만79세","s":0,"o":5},{"q":"age_band","v":"80_plus","l":"만80세 이상","s":0,"o":6},
        {"q":"total_net_assets","v":"under_100m","l":"1억원 미만","s":1,"o":1},{"q":"total_net_assets","v":"100m_to_500m","l":"1억원 이상~5억원 미만","s":2,"o":2},{"q":"total_net_assets","v":"500m_to_1b","l":"5억원 이상~10억원 미만","s":3,"o":3},{"q":"total_net_assets","v":"1b_to_2b","l":"10억원 이상~20억원 미만","s":4,"o":4},{"q":"total_net_assets","v":"over_2b","l":"20억원 이상","s":5,"o":5},
        {"q":"annual_income","v":"under_20m","l":"2천만원 미만","s":1,"o":1},{"q":"annual_income","v":"20m_to_50m","l":"2천만원 이상~5천만원 미만","s":2,"o":2},{"q":"annual_income","v":"50m_to_70m","l":"5천만원 이상~7천만원 미만","s":3,"o":3},{"q":"annual_income","v":"70m_to_100m","l":"7천만원 이상~1억원 미만","s":4,"o":4},{"q":"annual_income","v":"over_100m","l":"1억원 이상","s":5,"o":5},
        {"q":"financial_asset_share","v":"under_10","l":"10% 미만","s":0,"o":1},{"q":"financial_asset_share","v":"10_to_20","l":"10% ~ 20% 미만","s":0,"o":2},{"q":"financial_asset_share","v":"20_to_30","l":"20% ~ 30% 미만","s":0,"o":3},{"q":"financial_asset_share","v":"30_to_50","l":"30% ~ 50% 미만","s":0,"o":4},{"q":"financial_asset_share","v":"over_50","l":"50% 이상","s":0,"o":5},
        {"q":"investment_product_share","v":"under_10","l":"0~9%","s":1,"o":1},{"q":"investment_product_share","v":"10_to_20","l":"10~19%","s":2,"o":2},{"q":"investment_product_share","v":"20_to_30","l":"20~29%","s":3,"o":3},{"q":"investment_product_share","v":"30_to_50","l":"30~49%","s":4,"o":4},{"q":"investment_product_share","v":"over_50","l":"50% 이상","s":5,"o":5},
        {"q":"loan_product_share","v":"under_10","l":"0~9%","s":1,"o":1},{"q":"loan_product_share","v":"10_to_20","l":"10~19%","s":2,"o":2},{"q":"loan_product_share","v":"20_to_30","l":"20~29%","s":3,"o":3},{"q":"loan_product_share","v":"30_to_50","l":"30~49%","s":4,"o":4},{"q":"loan_product_share","v":"over_50","l":"50% 이상","s":5,"o":5},
        {"q":"investment_experience_product","v":"very_low","l":"예금, CMA, MMF, RP, 국공채 등","s":1,"o":1},{"q":"investment_experience_product","v":"low","l":"채권형펀드, 원금보장형 ELB/DLB, 금융채 등","s":3,"o":2},{"q":"investment_experience_product","v":"medium","l":"혼합형펀드, 원금부분보장형 ELS/DLS, 일반회사채","s":4,"o":3},{"q":"investment_experience_product","v":"high","l":"주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채","s":5,"o":4},{"q":"investment_experience_product","v":"very_high","l":"파생상품펀드, ELW, 선물·옵션, 주식신용거래 등","s":6,"o":5},
        {"q":"investment_experience_period","v":"none","l":"투자경험 없음","s":0,"o":1},{"q":"investment_experience_period","v":"under_1y","l":"1년 미만","s":1,"o":2},{"q":"investment_experience_period","v":"1_to_3y","l":"1년 이상~3년 미만","s":3,"o":3},{"q":"investment_experience_period","v":"over_3y","l":"3년 이상","s":5,"o":4},
        {"q":"investment_purpose","v":"education","l":"교육비","s":1,"o":1},{"q":"investment_purpose","v":"living","l":"생활비","s":1,"o":2},{"q":"investment_purpose","v":"marriage","l":"결혼자금","s":1,"o":3},{"q":"investment_purpose","v":"debt","l":"채무상환","s":1,"o":4},{"q":"investment_purpose","v":"housing","l":"주택마련자금","s":2,"o":5},{"q":"investment_purpose","v":"growth","l":"자산증식자금","s":3,"o":6},
        {"q":"financial_knowledge","v":"basic","l":"금융투자상품에 투자해 본 경험이 없음","s":1,"o":1},{"q":"financial_knowledge","v":"partial","l":"주식, 채권, 펀드 등의 구조와 위험을 일정 부분 이해하고 있음","s":3,"o":2},{"q":"financial_knowledge","v":"deep","l":"주식, 채권, 펀드 등의 구조와 위험을 깊이 있게 이해하고 있음","s":4,"o":3},{"q":"financial_knowledge","v":"derivatives","l":"파생상품을 포함한 대부분의 금융상품 구조와 위험을 이해하고 있음","s":5,"o":4},
        {"q":"investment_horizon","v":"under_1y","l":"1년 미만","s":1,"o":1},{"q":"investment_horizon","v":"1_to_2y","l":"1년 이상~2년 미만","s":2,"o":2},{"q":"investment_horizon","v":"2_to_3y","l":"2년 이상~3년 미만","s":3,"o":3},{"q":"investment_horizon","v":"3_to_5y","l":"3년 이상~5년 미만","s":4,"o":4},{"q":"investment_horizon","v":"over_5y","l":"5년 이상","s":5,"o":5},
        {"q":"risk_attitude","v":"principal","l":"투자 수익을 고려하나 원금 보존이 더 중요함","s":1,"o":1},{"q":"risk_attitude","v":"balanced","l":"원금 보존을 고려하나 투자 수익이 더 중요함","s":3,"o":2},{"q":"risk_attitude","v":"return","l":"손실 위험이 있더라도 투자 수익이 더 중요함","s":5,"o":3},
        {"q":"loss_tolerance","v":"limited","l":"제한적인 손실을 감수하여 시중금리 수준의 수익을 기대","s":1,"o":1},{"q":"loss_tolerance","v":"partial","l":"원금의 일부 손실을 감수하여 시중금리보다 다소 높은 수준의 수익을 기대","s":3,"o":2},{"q":"loss_tolerance","v":"principal_loss","l":"원금 손실을 감수하여 시장수익률과 비슷한 수준의 수익을 기대","s":5,"o":3},{"q":"loss_tolerance","v":"beyond_principal","l":"원금 초과 손실까지 감수하여 시장수익률을 초과하는 높은 수익을 추구","s":7,"o":4},
        {"q":"derivative_experience","v":"none","l":"투자경험 없음","s":0,"o":1},{"q":"derivative_experience","v":"under_1y","l":"1년 미만","s":0,"o":2},{"q":"derivative_experience","v":"1_to_3y","l":"1년 ~ 3년 미만","s":0,"o":3},{"q":"derivative_experience","v":"over_3y","l":"3년 이상","s":0,"o":4},
        {"q":"vulnerable_investor","v":"yes","l":"예","s":0,"o":1},{"q":"vulnerable_investor","v":"no","l":"아니오","s":0,"o":2},
        {"q":"validity_consent","v":"agree","l":"동의","s":0,"o":1},{"q":"validity_consent","v":"disagree","l":"미동의","s":0,"o":2},
        {"q":"retirement_start_age","v":"55","l":"만 55세","s":0,"o":1},{"q":"retirement_start_age","v":"56","l":"만 56세","s":0,"o":2},{"q":"retirement_start_age","v":"57","l":"만 57세","s":0,"o":3},{"q":"retirement_start_age","v":"58","l":"만 58세","s":0,"o":4},{"q":"retirement_start_age","v":"59","l":"만 59세","s":0,"o":5},{"q":"retirement_start_age","v":"60","l":"만 60세","s":0,"o":6}
      ]
    $options$) as item(q text, v text, l text, s smallint, o smallint)
)
insert into public.profile_question_options (
    question_id, answer_value, label, score, display_order
)
select question.id, option.v, option.l, option.s, option.o
from options as option
join inserted_questions as question on question.code = option.q;
