-- 대체·미사용으로 확정된 죽은 테이블 4종을 제거한다.
--
-- 근거: 20260723043507_annotate_table_domains.sql 에서 아래와 같이 표기됐다.
--   public.mock_public_profiles           '[mock_public/dead] benchmark_mock_*·demo_public_*로 대체된 초기 공개 프로필'
--   public.mock_public_portfolios         '[mock_public/dead] 대체된 초기 공개 포트폴리오. 별도 승인 후 드롭 예정'
--   public.mock_public_portfolio_holdings '[mock_public/dead] 대체된 초기 공개 포트폴리오 보유내역. 드롭 예정'
--   public.curated_contents               '[rag_news/dead] 초기 큐레이션 콘텐츠. 미사용. 별도 승인 후 드롭 예정'
--
-- 사전 확인(2026-07-23): backend/app·scripts·tests 참조 0건.
-- 삭제 직전 행 수: mock_public_profiles 3, mock_public_portfolios 3,
--                  mock_public_portfolio_holdings 9, curated_contents 0.
-- 복구: 테이블 정의는 20260715005435_initial_data_foundation.sql, seed 데이터는
--       supabase/seed.sql 의 이 커밋 이전 이력에서 되살릴 수 있다.
--
-- FK 의존성을 지키기 위해 자식 → 부모 순으로 제거한다. cascade는 쓰지 않는다.
-- 예상치 못한 의존 객체가 있으면 조용히 지우지 말고 실패시켜야 하기 때문이다.

drop table if exists public.mock_public_portfolio_holdings;
drop table if exists public.mock_public_portfolios;
drop table if exists public.mock_public_profiles;
drop table if exists public.curated_contents;
