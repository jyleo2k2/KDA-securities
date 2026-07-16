from datetime import date

import httpx
import pytest

from backend.app.ingestion.law_open import build_pension_regulatory_master
from backend.app.ingestion.law_open_client import (
    LawOpenApiError,
    fetch_law_open_document,
    parse_law_open_payload,
)


def _law_payload(name: str, article: dict[str, object]) -> dict[str, object]:
    return {
        "법령": {
            "기본정보": {"법령명_한글": name, "시행일자": "20260324"},
            "조문": {"조문단위": [article]},
        }
    }


def _admrul_payload(
    name: str,
    article: str,
    *,
    effective_date: str,
) -> dict[str, object]:
    return {
        "AdmRulService": {
            "행정규칙기본정보": {
                "행정규칙명": name,
                "시행일자": effective_date,
                "현행여부": "Y",
            },
            "조문내용": [article],
        }
    }


def _documents():
    decree_article = {
        "조문번호": "26",
        "항": {
            "항번호": "①",
            "호": {
                "호번호": "2.",
                "목": {
                    "목번호": "가.",
                    "목내용": (
                        "가. 원리금보장 운용방법과 투자위험을 낮춘 운용방법을 "
                        "제외한 운용방법은 총투자한도 내에서 운용할 것"
                    ),
                },
            },
        },
    }
    rule_article = {
        "조문번호": "10",
        "항": {
            "항번호": "①",
            "호": {
                "호번호": "2.",
                "호내용": (
                    "2. 확정기여형퇴직연금제도 및 개인형퇴직연금제도: "
                    "가입자별 전체 적립금의 100분의 70"
                ),
            },
        },
    }
    regulation_article = (
        "제11조(적립금 운용방법 등) ① 투자위험을 낮춘 운용방법 "
        "9. 투자목표시점이 명시된 집합투자증권 "
        "10. 법 제21조의2제1항에 따라 승인받은 사전지정운용방법 "
        "② 확정기여형퇴직연금 및 개인형퇴직연금의 경우"
    )
    detailed_article = (
        "제5조의2(적격 집합투자증권 인정기준) "
        "1. 은퇴예상시기가 다가올수록 위험자산 비중을 줄일 것 "
        "2. 투자목표시점을 설정일부터 5년 이후로 할 것 "
        "3. 현금성자산 및 채무증권 비중 기준을 지킬 것 "
        "4. 투자적격등급 이외 채무증권 한도를 지킬 것 "
        "5. 해외 특정 국가 주식 및 채권 한도를 지킬 것"
    )
    payloads = {
        "retirement_benefit_act_enforcement_decree": (
            "law",
            "근로자퇴직급여 보장법 시행령",
            _law_payload("근로자퇴직급여 보장법 시행령", decree_article),
        ),
        "retirement_benefit_act_enforcement_rule": (
            "law",
            "근로자퇴직급여 보장법 시행규칙",
            _law_payload("근로자퇴직급여 보장법 시행규칙", rule_article),
        ),
        "retirement_pension_supervision_regulation": (
            "admrul",
            "퇴직연금감독규정",
            _admrul_payload(
                "퇴직연금감독규정",
                regulation_article,
                effective_date="20231116",
            ),
        ),
        "retirement_pension_supervision_detailed_rule": (
            "admrul",
            "퇴직연금감독규정시행세칙",
            _admrul_payload(
                "퇴직연금감독규정시행세칙",
                detailed_article,
                effective_date="20260401",
            ),
        ),
    }
    return {
        slug: parse_law_open_payload(payload, target=target, requested_name=name)
        for slug, (target, name, payload) in payloads.items()
    }


def test_law_open_client_sends_key_without_echoing_it() -> None:
    payload = _law_payload(
        "근로자퇴직급여 보장법 시행규칙",
        {"조문번호": "10"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["OC"] == "never-print-key"
        assert request.url.params["target"] == "law"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        document = fetch_law_open_document(
            client,
            api_key="never-print-key",
            target="law",
            name="근로자퇴직급여 보장법 시행규칙",
        )
    assert document.effective_date == "20260324"

    def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with (
        httpx.Client(transport=httpx.MockTransport(rejected)) as client,
        pytest.raises(LawOpenApiError) as error,
    ):
        fetch_law_open_document(
            client,
            api_key="never-print-key",
            target="law",
            name="근로자퇴직급여 보장법 시행규칙",
        )
    assert "never-print-key" not in str(error.value)


def test_regulatory_master_separates_cap_and_tdf_qualification() -> None:
    master = build_pension_regulatory_master(
        _documents(), snapshot_date=date(2026, 7, 16)
    )

    rules = {rule["rule_id"]: rule for rule in master["rules"]}
    assert rules["DC_IRP_GENERAL_RISK_ASSET_CAP"]["aggregate_limit_percent"] == 70
    tdf = rules["DC_IRP_QUALIFIED_TDF_CRITERIA"]
    assert tdf["product_level_verification_required"] is True
    assert len(tdf["criteria"]) == 5
    assert master["account_scope"] == ["dc", "irp"]
