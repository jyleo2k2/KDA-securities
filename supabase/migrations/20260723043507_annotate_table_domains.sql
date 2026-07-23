-- 관리자 식별용 비파괴 도메인 주석.
-- public 한 스키마에 테이블이 누적돼 어느 것이 라이브인지 식별하기 어려운
-- 문제를 해결하기 위해, 코멘트가 없던 41개 테이블에만 도메인·라이프사이클
-- 태그를 단다. 데이터·권한·인덱스·RLS·스키마는 바꾸지 않는다.
-- 이미 코멘트가 있는 15개 테이블은 건드리지 않는다.
--
-- 태그 형식: '[<domain>/<lifecycle>] <설명>'
--   domain    = 아래 11개 논리 도메인 중 하나(추후 스키마 분리 후보 경계).
--   lifecycle = live     : 백엔드 코드가 실제로 읽고 쓴다.
--               retained : 코드 참조는 없으나 감사·이력 보존 목적으로 유지.
--               reserved : 스키마는 설계됐으나 현재 데이터가 없는 예약 테이블.
--               dead     : 다른 테이블로 대체됨. 별도 승인 후 드롭 예정.

-- ── source: 출처·수집 근거 ──────────────────────────────────────────────
comment on table public.data_sources is
    '[source/live] 실데이터 출처 카탈로그(FSS·KRX·KIS·NAVER 등)';
comment on table public.ingestion_runs is
    '[source/live] 수집 실행 단위와 요청 파라미터·기준일·해시 근거';

-- ── institution: 금융기관·공시 통계 ─────────────────────────────────────
comment on table public.financial_institutions is
    '[institution/live] 금융기관 마스터(provider_name 대신 id 참조 기준키)';
comment on table public.institution_aliases is
    '[institution/live] 기관 표기 변형과 정규화 기관 id 매핑';
comment on table public.pension_savings_provider_stats is
    '[institution/live] FSS 연금저축 회사별 수익률·수수료율 기관 단위 집계';
comment on table public.retirement_provider_stats is
    '[institution/live] FSS 퇴직연금 사업자별 수익률 기관 단위 집계';

-- ── asset: 자산 분류 ────────────────────────────────────────────────────
comment on table public.asset_classes is
    '[asset/live] 엔진·상품 공통 자산군 코드 마스터';

-- ── mock_scenario: 목시나리오 계좌(레거시 이관 원본) ────────────────────
comment on table public.mock_scenarios is
    '[mock_scenario/live] 챗봇 데모 시나리오 카탈로그';
comment on table public.mock_accounts is
    '[mock_scenario/retained] 공통 pension_accounts로 이관 완료된 목계좌 원본(감사 보존)';
comment on table public.mock_holdings is
    '[mock_scenario/retained] 공통 구조로 이관 완료된 목보유내역 원본(감사 보존)';

-- ── mock_public: 초기 공개 벤치마크(대체됨) ─────────────────────────────
comment on table public.mock_public_profiles is
    '[mock_public/dead] benchmark_mock_*·demo_public_*로 대체된 초기 공개 프로필';
comment on table public.mock_public_portfolios is
    '[mock_public/dead] 대체된 초기 공개 포트폴리오. 별도 승인 후 드롭 예정';
comment on table public.mock_public_portfolio_holdings is
    '[mock_public/dead] 대체된 초기 공개 포트폴리오 보유내역. 드롭 예정';

-- ── benchmark: 대규모 합성 벤치마크 ─────────────────────────────────────
comment on table public.benchmark_mock_users is
    '[benchmark/live] 1만 명 합성 벤치마크 사용자';
comment on table public.benchmark_mock_accounts is
    '[benchmark/live] 합성 벤치마크 계좌';
comment on table public.benchmark_mock_holdings is
    '[benchmark/live] 합성 벤치마크 보유내역';

-- ── demo_customer: 대표 고객 공개 계약 ──────────────────────────────────
comment on table public.demo_user_financial_context is
    '[demo_customer/live] 대표 고객 Auth 사용자·시나리오 연결과 재무 컨텍스트';

-- ── engine_audit: 규칙 엔진·감사 ────────────────────────────────────────
comment on table public.rule_sets is
    '[engine_audit/live] 규칙 엔진 파라미터 세트 버전';
comment on table public.pension_rules is
    '[engine_audit/live] 계좌 유형별 위험자산 한도·법정예외 규칙';
comment on table public.engine_runs is
    '[engine_audit/live] 엔진 실행 결과(버전형 진단·집계 수치)';
comment on table public.engine_run_evidence is
    '[engine_audit/live] 엔진 실행 결과의 입력·근거 스냅샷';

-- ── rag_news: RAG 지식·뉴스 ─────────────────────────────────────────────
comment on table public.knowledge_documents is
    '[rag_news/live] 승인된 공식 지식 문서 원본';
comment on table public.knowledge_chunks is
    '[rag_news/live] BGE-M3 1024차원 임베딩 청크(HNSW 검색)';
comment on table public.news_items is
    '[rag_news/live] NAVER 뉴스 검색 메타데이터와 3줄 요약';
comment on table public.curated_contents is
    '[rag_news/dead] 초기 큐레이션 콘텐츠. 미사용. 별도 승인 후 드롭 예정';

-- ── chat: 챗봇 대화 ─────────────────────────────────────────────────────
comment on table public.chat_sessions is
    '[chat/live] 사용자 소유 대화 세션';
comment on table public.chat_messages is
    '[chat/live] 대화 메시지 이력';
comment on table public.chat_message_evidence is
    '[chat/live] 메시지별 출처 칩·근거 연결';
comment on table public.chat_request_idempotency is
    '[chat/live] 챗 요청 idempotency 키 장부';

-- ── user_pension: 사용자·투자성향·연금계좌 ──────────────────────────────
comment on table public.user_profiles is
    '[user_pension/live] auth.users 참조 앱 사용자 프로필 확장';
comment on table public.profile_question_sets is
    '[user_pension/live] 투자성향 설문 세트 버전';
comment on table public.profile_questions is
    '[user_pension/live] 설문 문항';
comment on table public.profile_question_options is
    '[user_pension/live] 설문 선택지·배점';
comment on table public.investment_profile_assessments is
    '[user_pension/live] 성향 진단 이력(총점·5단계 성향·엔진 버전)';
comment on table public.investment_profile_answers is
    '[user_pension/live] 진단 당시 답변·점수 스냅샷';
comment on table public.investment_profile_confirmations is
    '[user_pension/live] 저장 투자성향 확인 이력(24개월 유효·append-only)';
comment on table public.pension_accounts is
    '[user_pension/live] 실계좌·목계좌 공통 연금계좌';
comment on table public.account_snapshots is
    '[user_pension/live] 기준일 계좌 상태(누적 납입·평가액)';
comment on table public.account_holding_snapshots is
    '[user_pension/live] 기준일 보유내역 스냅샷';
comment on table public.account_cash_flows is
    '[user_pension/reserved] 과거 수익률 계산용 외부 현금흐름. 현재 미적재';
comment on table public.financial_products is
    '[user_pension/reserved] 상품 마스터. holding FK 참조 대상이나 현재 미적재';

-- ── 관리자 식별용 카탈로그 뷰 ───────────────────────────────────────────
-- 각 public 테이블의 도메인·라이프사이클 태그와 코멘트를 한 화면에 모은다.
-- 태그 규칙을 따르지 않는(코멘트가 없거나 '[domain/lifecycle]' 접두어가 없는)
-- 테이블은 domain·lifecycle이 null로 나와 누락을 바로 식별할 수 있다.
-- security_invoker=true라 호출자(RLS·GRANT) 권한을 그대로 따른다.
create view public.table_domain_catalog
with (security_invoker = true) as
select
    c.relname as table_name,
    substring(
        obj_description(c.oid, 'pg_class') from '^\[([^/]+)/'
    ) as domain,
    substring(
        obj_description(c.oid, 'pg_class') from '^\[[^/]+/([^]]+)\]'
    ) as lifecycle,
    obj_description(c.oid, 'pg_class') as table_comment
from pg_catalog.pg_class as c
join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind in ('r', 'p')
order by domain nulls last, lifecycle, table_name;

comment on view public.table_domain_catalog is
    '[admin/live] public 테이블의 도메인·라이프사이클 태그 식별용 조회 뷰';

-- 내부 관리용 뷰: 브라우저 직접 접근을 차단하고 FastAPI·관리자 경유만 허용한다.
revoke all privileges on public.table_domain_catalog
from public, anon, authenticated;
grant select on public.table_domain_catalog to service_role;
