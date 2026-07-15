from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.types.json import Jsonb

from .fss_client import (
    FssResponse,
    PensionSavingsProviderRow,
    RetirementProviderRow,
)

PS_SOURCE_CODE = "fss_ps_corp_list"
RP_SOURCE_CODE = "fss_rp_corp_result_list"
UNIT_BASIS = "project_assumption_api_unit_not_documented_2026-07-14"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    code: str
    name: str
    endpoint: str
    default_source_unit: str


@dataclass(frozen=True, slots=True)
class RunHandle:
    run_id: UUID
    source_id: int


PS_SOURCE = SourceDefinition(
    code=PS_SOURCE_CODE,
    name="통합연금포털 연금저축 회사별 수익률·수수료율",
    endpoint="https://www.fss.or.kr/openapi/api/psCorpList.json",
    default_source_unit="million_krw",
)
RP_SOURCE = SourceDefinition(
    code=RP_SOURCE_CODE,
    name="통합연금포털 퇴직연금 사업자별 수익률",
    endpoint="https://www.fss.or.kr/openapi/api/rpCorpResultList.json",
    default_source_unit="hundred_million_krw",
)


class FssDisclosureRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def start_run(
        self,
        source: SourceDefinition,
        requested_params: dict[str, int],
    ) -> RunHandle:
        if "key" in requested_params:
            raise ValueError(
                "API credentials must not be persisted in requested_params"
            )
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    insert into public.data_sources (
                        code, name, source_type, authority, base_url,
                        default_source_unit, metadata
                    )
                    values (
                        %s, %s, 'regulator_api', '금융감독원', %s, %s,
                        %s
                    )
                    on conflict (code) do update set
                        name = excluded.name,
                        base_url = excluded.base_url,
                        default_source_unit = excluded.default_source_unit,
                        metadata = excluded.metadata,
                        is_active = true,
                        updated_at = now()
                    returning id
                    """,
                (
                    source.code,
                    source.name,
                    source.endpoint,
                    source.default_source_unit,
                    Jsonb(
                        {
                            "data_boundary": "official_disclosure",
                            "is_mock": False,
                            "unit_note": (
                                "API 응답에 단위가 없어 프로젝트 검증 문서의 "
                                "표기를 적용하고 원본 값을 함께 보존한다."
                            )
                        }
                    ),
                ),
            )
            source_row = cursor.fetchone()
            if source_row is None:
                raise RuntimeError("failed to resolve FSS data source")
            source_id = int(source_row[0])
            cursor.execute(
                """
                    insert into public.ingestion_runs (
                        source_id, endpoint, requested_params, status, metadata
                    )
                    values (%s, %s, %s, 'running', %s)
                    returning id
                    """,
                (
                    source_id,
                    source.endpoint,
                    Jsonb(requested_params),
                    Jsonb(
                        {
                            "data_boundary": "official_disclosure",
                            "is_mock": False,
                        }
                    ),
                ),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise RuntimeError("failed to create FSS ingestion run")
            return RunHandle(run_id=run_row[0], source_id=source_id)

    def fail_run(self, run_id: UUID, error: Exception) -> None:
        safe_message = f"{type(error).__name__}: {error}"[:1000]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    update public.ingestion_runs
                    set status = 'failed',
                        completed_at = now(),
                        error_message = %s,
                        metadata = metadata ||
                            '{"outcome":"failed",'
                            '"data_boundary":"official_disclosure",'
                            '"is_mock":false}'::jsonb
                    where id = %s and status = 'running'
                    """,
                (safe_message, run_id),
            )

    def complete_pension_savings(
        self,
        *,
        handle: RunHandle,
        response: FssResponse,
        rows: list[PensionSavingsProviderRow],
        year: int,
        quarter: int,
    ) -> int:
        with psycopg.connect(self._database_url) as connection:
            institutions = self._upsert_institutions(connection, handle.source_id, rows)
            params: list[dict[str, Any]] = []
            for row in rows:
                params.append(
                    {
                        "source_id": handle.source_id,
                        "ingestion_run_id": handle.run_id,
                        "institution_id": institutions[row.company_name_raw],
                        "year": year,
                        "quarter": quarter,
                        "area_name_raw": row.area_name_raw,
                        "company_name_raw": row.company_name_raw,
                        "reserve_source_value": row.reserve_source_value,
                        "reserve_source_value_1y": row.reserve_source_value_1y,
                        "reserve_source_value_2y": row.reserve_source_value_2y,
                        "reserve_source_value_3y": row.reserve_source_value_3y,
                        "reserve_source_unit": PS_SOURCE.default_source_unit,
                        "reserve_unit_basis": UNIT_BASIS,
                        "earn_rate_current": row.earn_rate_current,
                        "earn_rate_1y": row.earn_rate_1y,
                        "earn_rate_2y": row.earn_rate_2y,
                        "earn_rate_3y": row.earn_rate_3y,
                        "fee_rate_1y": row.fee_rate_1y,
                        "fee_rate_2y": row.fee_rate_2y,
                        "fee_rate_3y": row.fee_rate_3y,
                        "avg_earn_rate_3y": row.avg_earn_rate_3y,
                        "avg_earn_rate_5y": row.avg_earn_rate_5y,
                        "avg_earn_rate_7y": row.avg_earn_rate_7y,
                        "avg_earn_rate_10y": row.avg_earn_rate_10y,
                        "avg_fee_rate_3y": row.avg_fee_rate_3y,
                        "avg_fee_rate_5y": row.avg_fee_rate_5y,
                        "avg_fee_rate_7y": row.avg_fee_rate_7y,
                        "avg_fee_rate_10y": row.avg_fee_rate_10y,
                        "quality_flags": Jsonb(
                            [*row.quality_flags, "reserve_unit_not_in_api_response"]
                        ),
                        "raw_payload": Jsonb(row.raw_payload),
                    }
                )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into public.pension_savings_provider_stats (
                        source_id, ingestion_run_id, institution_id, year, quarter,
                        area_name_raw, company_name_raw,
                        reserve_source_value, reserve_source_value_1y,
                        reserve_source_value_2y, reserve_source_value_3y,
                        reserve_source_unit, reserve_unit_basis,
                        earn_rate_current, earn_rate_1y, earn_rate_2y, earn_rate_3y,
                        fee_rate_1y, fee_rate_2y, fee_rate_3y,
                        avg_earn_rate_3y, avg_earn_rate_5y,
                        avg_earn_rate_7y, avg_earn_rate_10y,
                        avg_fee_rate_3y, avg_fee_rate_5y,
                        avg_fee_rate_7y, avg_fee_rate_10y,
                        quality_flags, raw_payload
                    )
                    values (
                        %(source_id)s, %(ingestion_run_id)s, %(institution_id)s,
                        %(year)s, %(quarter)s, %(area_name_raw)s, %(company_name_raw)s,
                        %(reserve_source_value)s, %(reserve_source_value_1y)s,
                        %(reserve_source_value_2y)s, %(reserve_source_value_3y)s,
                        %(reserve_source_unit)s, %(reserve_unit_basis)s,
                        %(earn_rate_current)s, %(earn_rate_1y)s,
                        %(earn_rate_2y)s, %(earn_rate_3y)s,
                        %(fee_rate_1y)s, %(fee_rate_2y)s, %(fee_rate_3y)s,
                        %(avg_earn_rate_3y)s, %(avg_earn_rate_5y)s,
                        %(avg_earn_rate_7y)s, %(avg_earn_rate_10y)s,
                        %(avg_fee_rate_3y)s, %(avg_fee_rate_5y)s,
                        %(avg_fee_rate_7y)s, %(avg_fee_rate_10y)s,
                        %(quality_flags)s, %(raw_payload)s
                    )
                    on conflict (
                        source_id, year, quarter, area_name_raw, company_name_raw
                    )
                    do update set
                        ingestion_run_id = excluded.ingestion_run_id,
                        institution_id = excluded.institution_id,
                        reserve_source_value = excluded.reserve_source_value,
                        reserve_source_value_1y = excluded.reserve_source_value_1y,
                        reserve_source_value_2y = excluded.reserve_source_value_2y,
                        reserve_source_value_3y = excluded.reserve_source_value_3y,
                        reserve_source_unit = excluded.reserve_source_unit,
                        reserve_unit_basis = excluded.reserve_unit_basis,
                        earn_rate_current = excluded.earn_rate_current,
                        earn_rate_1y = excluded.earn_rate_1y,
                        earn_rate_2y = excluded.earn_rate_2y,
                        earn_rate_3y = excluded.earn_rate_3y,
                        fee_rate_1y = excluded.fee_rate_1y,
                        fee_rate_2y = excluded.fee_rate_2y,
                        fee_rate_3y = excluded.fee_rate_3y,
                        avg_earn_rate_3y = excluded.avg_earn_rate_3y,
                        avg_earn_rate_5y = excluded.avg_earn_rate_5y,
                        avg_earn_rate_7y = excluded.avg_earn_rate_7y,
                        avg_earn_rate_10y = excluded.avg_earn_rate_10y,
                        avg_fee_rate_3y = excluded.avg_fee_rate_3y,
                        avg_fee_rate_5y = excluded.avg_fee_rate_5y,
                        avg_fee_rate_7y = excluded.avg_fee_rate_7y,
                        avg_fee_rate_10y = excluded.avg_fee_rate_10y,
                        quality_flags = excluded.quality_flags,
                        raw_payload = excluded.raw_payload,
                        observed_at = now()
                    """,
                    params,
                )
                self._mark_succeeded(
                    cursor,
                    handle.run_id,
                    response,
                    len(rows),
                    {"normalization": "one row per company", "unit_basis": UNIT_BASIS},
                )
        return len(rows)

    def complete_retirement(
        self,
        *,
        handle: RunHandle,
        response: FssResponse,
        rows: list[RetirementProviderRow],
        year: int,
        quarter: int,
        sys_type: int,
    ) -> int:
        with psycopg.connect(self._database_url) as connection:
            institutions = self._upsert_institutions(connection, handle.source_id, rows)
            params: list[dict[str, Any]] = []
            for row in rows:
                params.append(
                    {
                        "source_id": handle.source_id,
                        "ingestion_run_id": handle.run_id,
                        "institution_id": institutions[row.company_name_raw],
                        "year": year,
                        "quarter": quarter,
                        "requested_sys_type": sys_type,
                        "response_division": row.response_division,
                        "area_name_raw": row.area_name_raw,
                        "company_name_raw": row.company_name_raw,
                        "scheme": row.scheme,
                        "reserve_source_value": row.reserve_source_value,
                        "reserve_source_unit": RP_SOURCE.default_source_unit,
                        "reserve_unit_basis": UNIT_BASIS,
                        "earn_rate_current": row.earn_rate_current,
                        "avg_earn_rate_3y": row.avg_earn_rate_3y,
                        "avg_earn_rate_5y": row.avg_earn_rate_5y,
                        "avg_earn_rate_7y": row.avg_earn_rate_7y,
                        "avg_earn_rate_10y": row.avg_earn_rate_10y,
                        "quality_flags": Jsonb(
                            [*row.quality_flags, "reserve_unit_not_in_api_response"]
                        ),
                        "raw_payload": Jsonb(row.raw_payload),
                    }
                )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into public.retirement_provider_stats (
                        source_id, ingestion_run_id, institution_id, year, quarter,
                        requested_sys_type, response_division, area_name_raw,
                        company_name_raw, scheme, reserve_source_value,
                        reserve_source_unit, reserve_unit_basis, earn_rate_current,
                        avg_earn_rate_3y, avg_earn_rate_5y,
                        avg_earn_rate_7y, avg_earn_rate_10y,
                        quality_flags, raw_payload
                    )
                    values (
                        %(source_id)s, %(ingestion_run_id)s, %(institution_id)s,
                        %(year)s, %(quarter)s, %(requested_sys_type)s,
                        %(response_division)s, %(area_name_raw)s,
                        %(company_name_raw)s, %(scheme)s,
                        %(reserve_source_value)s, %(reserve_source_unit)s,
                        %(reserve_unit_basis)s, %(earn_rate_current)s,
                        %(avg_earn_rate_3y)s, %(avg_earn_rate_5y)s,
                        %(avg_earn_rate_7y)s, %(avg_earn_rate_10y)s,
                        %(quality_flags)s, %(raw_payload)s
                    )
                    on conflict (
                        source_id, year, quarter, requested_sys_type,
                        company_name_raw, scheme
                    )
                    do update set
                        ingestion_run_id = excluded.ingestion_run_id,
                        institution_id = excluded.institution_id,
                        response_division = excluded.response_division,
                        area_name_raw = excluded.area_name_raw,
                        reserve_source_value = excluded.reserve_source_value,
                        reserve_source_unit = excluded.reserve_source_unit,
                        reserve_unit_basis = excluded.reserve_unit_basis,
                        earn_rate_current = excluded.earn_rate_current,
                        avg_earn_rate_3y = excluded.avg_earn_rate_3y,
                        avg_earn_rate_5y = excluded.avg_earn_rate_5y,
                        avg_earn_rate_7y = excluded.avg_earn_rate_7y,
                        avg_earn_rate_10y = excluded.avg_earn_rate_10y,
                        quality_flags = excluded.quality_flags,
                        raw_payload = excluded.raw_payload,
                        observed_at = now()
                    """,
                    params,
                )
                self._mark_succeeded(
                    cursor,
                    handle.run_id,
                    response,
                    len(rows),
                    {
                        "normalization": "company response expanded to db/dc/irp rows",
                        "unit_basis": UNIT_BASIS,
                    },
                )
        return len(rows)

    @staticmethod
    def _upsert_institutions(
        connection: Connection[Any],
        source_id: int,
        rows: Iterable[PensionSavingsProviderRow | RetirementProviderRow],
    ) -> dict[str, int]:
        companies = sorted({row.company_name_raw for row in rows})
        if not companies:
            return {}
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                insert into public.financial_institutions (normalized_name)
                values (%s)
                on conflict (normalized_name) do nothing
                """,
                [(company,) for company in companies],
            )
            cursor.execute(
                """
                select id, normalized_name
                from public.financial_institutions
                where normalized_name = any(%s)
                """,
                (companies,),
            )
            institutions = {str(name): int(identifier) for identifier, name in cursor}
            cursor.executemany(
                """
                insert into public.institution_aliases (
                    institution_id, source_id, alias_name
                )
                values (%s, %s, %s)
                on conflict (source_id, alias_name) do update set
                    institution_id = excluded.institution_id
                """,
                [(institutions[company], source_id, company) for company in companies],
            )
        return institutions

    @staticmethod
    def _mark_succeeded(
        cursor: Any,
        run_id: UUID,
        response: FssResponse,
        normalized_count: int,
        metadata: dict[str, str],
    ) -> None:
        cursor.execute(
            """
            update public.ingestion_runs
            set status = 'succeeded',
                completed_at = now(),
                response_code = %s,
                response_message = %s,
                source_record_count = %s,
                normalized_record_count = %s,
                upserted_record_count = %s,
                metadata = metadata || %s
            where id = %s and status = 'running'
            """,
            (
                response.api_code,
                response.message,
                response.source_count,
                normalized_count,
                normalized_count,
                Jsonb(
                    {
                        **metadata,
                        "outcome": "succeeded",
                        "data_boundary": "official_disclosure",
                        "is_mock": False,
                    }
                ),
                run_id,
            ),
        )
