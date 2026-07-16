import json
from pathlib import Path

import httpx
import pytest

from backend.app.ingestion.kis import load_krx_etf_universe
from backend.app.ingestion.kis_client import (
    KisApiError,
    fetch_etf_components,
    fetch_etf_price,
    issue_access_token,
)


def test_issue_token_and_fetch_etf_data_without_echoing_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            assert b"never-print-secret" in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "token-value",
                    "token_type": "Bearer",
                    "expires_in": 86400,
                },
            )
        assert request.headers["appkey"] == "app-key"
        assert request.headers["appsecret"] == "never-print-secret"
        assert request.headers["authorization"] == "Bearer token-value"
        if request.url.path.endswith("inquire-component-stock-price"):
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "msg_cd": "MCA00000",
                    "output1": {"nav": "40000"},
                    "output2": [{"stck_shrn_iscd": "005930"}],
                },
            )
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "msg_cd": "MCA00000",
                "output": {"stck_prpr": "41000"},
            },
        )

    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        token = issue_access_token(
            client, app_key="app-key", app_secret="never-print-secret"
        )
        components = fetch_etf_components(
            client,
            app_key="app-key",
            app_secret="never-print-secret",
            access_token=token.value,
            isu_code="069500",
        )
        price = fetch_etf_price(
            client,
            app_key="app-key",
            app_secret="never-print-secret",
            access_token=token.value,
            isu_code="069500",
        )

    assert components.payload["output2"][0]["stck_shrn_iscd"] == "005930"
    assert price.payload["output"]["stck_prpr"] == "41000"


def test_kis_rejection_never_echoes_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"rt_cd": "1", "msg_cd": "ERR001", "msg1": "rejected"},
        )

    with (
        httpx.Client(
            base_url="https://example.test", transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(KisApiError) as error,
    ):
        fetch_etf_price(
            client,
            app_key="never-print-key",
            app_secret="never-print-secret",
            access_token="never-print-token",
            isu_code="069500",
        )

    message = str(error.value)
    assert error.value.message_code == "ERR001"
    assert "never-print-key" not in message
    assert "never-print-secret" not in message
    assert "never-print-token" not in message


def test_load_krx_universe_validates_count_and_codes(tmp_path: Path) -> None:
    path = tmp_path / "krx.json"
    path.write_text(
        json.dumps(
            {
                "as_of": "2026-07-14",
                "product_count": 1,
                "products": [{"isu_code": "069500", "isu_name": "KODEX 200"}],
            }
        ),
        encoding="utf-8",
    )

    as_of, products = load_krx_etf_universe(path)

    assert as_of == "2026-07-14"
    assert products == [{"isu_code": "069500", "isu_name": "KODEX 200"}]
