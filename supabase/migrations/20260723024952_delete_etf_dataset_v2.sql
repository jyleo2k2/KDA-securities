-- Remove only the superseded ETF universe v2 after confirming v4 is the
-- production-ready replacement. Child rows use the existing cascade keys.
delete from public.etf_dataset_versions
where id = 2
  and as_of = date '2026-07-20';
