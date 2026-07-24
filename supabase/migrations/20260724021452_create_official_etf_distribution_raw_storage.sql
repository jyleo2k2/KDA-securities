-- 공식 ETF 분배금 수집 원본은 브라우저에 노출하지 않는 비공개 Storage에만 보관한다.
-- service_role은 RLS를 우회하므로 별도 storage.objects 허용 정책을 만들지 않는다.
-- 정책 부재는 anon/authenticated의 deny-by-default 접근을 유지한다.
-- Storage lifecycle은 지원되지 않으므로 1년 보존 정리는 후속 수집기가 Storage API로 수행한다.
insert into storage.buckets (id, name, public)
values (
    'official-etf-distribution-raw',
    'official-etf-distribution-raw',
    false
)
on conflict (id) do update
set public = false;
