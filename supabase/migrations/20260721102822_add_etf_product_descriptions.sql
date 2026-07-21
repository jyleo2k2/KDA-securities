-- Approved ETF descriptions are joined by product name because some source
-- documents do not contain an issue code. normalized_product_name is produced
-- by the application and is unique within each version; collisions are rejected.
create table public.etf_product_descriptions (
    id bigint generated always as identity primary key,
    catalog_version text not null
        constraint etf_product_descriptions_catalog_version_check
            check (coalesce(length(btrim(catalog_version)), 0) > 0),
    product_name text not null
        constraint etf_product_descriptions_product_name_check
            check (coalesce(length(btrim(product_name)), 0) > 0),
    normalized_product_name text not null
        constraint etf_product_descriptions_normalized_name_check
            check (
                coalesce(length(btrim(normalized_product_name)), 0) > 0
                and normalized_product_name = lower(normalized_product_name)
                and normalized_product_name !~ '[[:space:]]'
            ),
    full_description text not null
        constraint etf_product_descriptions_full_description_check
            check (coalesce(length(btrim(full_description)), 0) > 0),
    one_line_description text not null
        constraint etf_product_descriptions_one_line_description_check
            check (coalesce(length(btrim(one_line_description)), 0) > 0),
    source_document_ids text[] not null
        constraint etf_product_descriptions_source_documents_check
            check (cardinality(source_document_ids) > 0),
    content_sha256 text not null
        constraint etf_product_descriptions_sha256_check
            check (content_sha256 ~ '^[0-9a-f]{64}$'),
    as_of_date date not null,
    approval_status text not null default 'draft'
        constraint etf_product_descriptions_approval_status_check
            check (approval_status in ('draft', 'verified', 'rejected')),
    verified_at timestamptz,
    reviewer text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint etf_product_descriptions_name_version_unique
        unique (catalog_version, normalized_product_name),
    constraint etf_product_descriptions_verified_contract_check
        check (
            approval_status <> 'verified'
            or (
                verified_at is not null
                and coalesce(length(btrim(reviewer)), 0) > 0
            )
        )
);

create index etf_product_descriptions_lookup_idx
    on public.etf_product_descriptions (
        normalized_product_name,
        catalog_version desc
    )
    where approval_status = 'verified';

alter table public.etf_product_descriptions enable row level security;

-- Server-only content: browsers receive descriptions through the FastAPI
-- response contract and never query or mutate this table directly.
revoke all privileges on table public.etf_product_descriptions
from public, anon, authenticated;

grant select, insert, update, delete on table public.etf_product_descriptions
to service_role;

revoke all privileges on sequence public.etf_product_descriptions_id_seq
from public, anon, authenticated;

grant usage, select on sequence public.etf_product_descriptions_id_seq
to service_role;

comment on table public.etf_product_descriptions is
    'Versioned approved ETF descriptions keyed by normalized product name; service-role only.';
