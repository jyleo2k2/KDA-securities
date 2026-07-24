-- 공식 ETF 분배금 수집 원본은 브라우저에 노출하지 않는 비공개 Storage에만 보관한다.
-- Storage lifecycle은 지원되지 않으므로 1년 보존 정리는 후속 수집기가 Storage API로 수행한다.
insert into storage.buckets (id, name, public)
values (
    'official-etf-distribution-raw',
    'official-etf-distribution-raw',
    false
)
on conflict (id) do update
set public = false;

do $$
begin
    if not exists (
        select 1
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'official_etf_distribution_raw_service_role'
    ) then
        create policy official_etf_distribution_raw_service_role
        on storage.objects
        for all
        to service_role
        using (bucket_id = 'official-etf-distribution-raw')
        with check (bucket_id = 'official-etf-distribution-raw');
    end if;
end $$;

comment on policy official_etf_distribution_raw_service_role on storage.objects is
    '공식 ETF 분배금 원본은 서버 수집기 service_role만 읽고 쓴다.';
