-- Remove only the superseded ETF universe v1.  Its child product and return
-- history rows are removed by the existing ON DELETE CASCADE foreign keys.
delete from public.etf_dataset_versions
where id = 1
  and as_of = date '2026-07-16';
