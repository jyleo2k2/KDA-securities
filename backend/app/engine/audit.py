from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .models import RiskCapEvaluation, RiskCapEvidence


def validate_rule_parameters(
    parameters: object,
    evidence: RiskCapEvidence,
) -> None:
    if not isinstance(parameters, dict):
        raise RuntimeError("rule parameters must be a JSON object")
    raw_limit = parameters.get("max_percent")
    try:
        database_limit = None if raw_limit is None else Decimal(str(raw_limit))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError("rule max_percent must be numeric or null") from exc
    if database_limit != evidence.limit_percent:
        raise RuntimeError(
            "engine result limit does not match the versioned database rule"
        )
    treatments = parameters.get("included_treatments")
    if treatments != ["general_risky"]:
        raise RuntimeError("engine rule treatment does not match the database rule")


class EngineAuditRepository:
    """Persist an already-computed deterministic result and its source chips."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def record(
        self,
        evaluation: RiskCapEvaluation,
        *,
        owner_id: UUID | None = None,
    ) -> UUID:
        rule_versions = {evidence.rule_version for evidence in evaluation.evidence}
        if len(rule_versions) != 1:
            raise RuntimeError("one engine run must use exactly one rule version")
        rule_version = rule_versions.pop()
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    select id
                    from public.rule_sets
                    where code = 'pension_account_core'
                      and version = %s
                      and status = 'active'
                    """,
                (rule_version,),
            )
            rule_set_row = cursor.fetchone()
            if rule_set_row is None:
                raise RuntimeError("active pension_account_core rule set is missing")
            rule_set_id = int(rule_set_row[0])

            cursor.execute(
                """
                    insert into public.engine_runs (
                        owner_id, rule_set_id, engine_name, engine_version,
                        status, request_payload, result_payload, completed_at
                    )
                    values (%s, %s, %s, %s, 'succeeded', %s, %s, now())
                    returning id
                    """,
                (
                    owner_id,
                    rule_set_id,
                    evaluation.engine_name,
                    evaluation.engine_version,
                    Jsonb(evaluation.evaluated_input.model_dump(mode="json")),
                    Jsonb(evaluation.model_dump(mode="json")),
                ),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise RuntimeError("failed to create engine audit run")
            run_id: UUID = run_row[0]

            evidence_params: list[dict[str, Any]] = []
            for evidence in evaluation.evidence:
                cursor.execute(
                    """
                        select
                            pr.id, pr.source_id, pr.source_locator, pr.parameters
                        from public.pension_rules as pr
                        where pr.rule_set_id = %s
                          and pr.rule_code = %s
                          and pr.account_type = %s
                        """,
                    (
                        rule_set_id,
                        evidence.rule_code,
                        evaluation.evaluated_input.account_type.value,
                    ),
                )
                rule_row = cursor.fetchone()
                if rule_row is None:
                    raise RuntimeError(
                        f"rule evidence is missing for {evidence.rule_code}"
                    )
                validate_rule_parameters(rule_row[3], evidence)
                evidence_params.append(
                    {
                        "engine_run_id": run_id,
                        "source_id": rule_row[1],
                        "rule_id": rule_row[0],
                        "source_locator": rule_row[2],
                        "as_of_date": evidence.source.as_of,
                        "payload": Jsonb(evidence.model_dump(mode="json")),
                    }
                )

            cursor.executemany(
                """
                    insert into public.engine_run_evidence (
                        engine_run_id, evidence_type, source_id, rule_id,
                        source_locator, as_of_date, payload
                    )
                    values (
                        %(engine_run_id)s, 'rule', %(source_id)s, %(rule_id)s,
                        %(source_locator)s, %(as_of_date)s, %(payload)s
                    )
                    """,
                evidence_params,
            )
            return run_id
