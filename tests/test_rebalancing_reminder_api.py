from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.deps import get_rebalancing_reminder_repository
from backend.app.auth import require_supabase_user_id
from backend.app.engine.educational_portfolio import rebalancing_cadence
from backend.app.engine.models import RiskProfile
from backend.app.main import app
from backend.app.rebalancing_reminder_repository import RebalancingReminderState

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _state(*, enabled: bool = True) -> RebalancingReminderState:
    cadence = rebalancing_cadence(RiskProfile.RISK_NEUTRAL)
    return RebalancingReminderState(
        profile_required=False,
        enabled=enabled,
        risk_profile=RiskProfile.RISK_NEUTRAL,
        cadence=cadence,
        last_reviewed_at=datetime(2026, 4, 1, tzinfo=UTC),
        next_review_at=datetime(2026, 7, 1, tzinfo=UTC),
        is_due=True,
    )


def test_reminder_endpoints_are_authenticated_and_owner_scoped() -> None:
    calls: list[tuple[str, UUID, bool | None]] = []

    class Repository:
        def get_state(self, owner_id: UUID):
            calls.append(("get", owner_id, None))
            return _state()

        def update_enabled(self, owner_id: UUID, *, enabled: bool):
            calls.append(("update", owner_id, enabled))
            return _state(enabled=enabled)

        def record_review_completion(self, owner_id: UUID):
            calls.append(("complete", owner_id, None))
            return _state()

    app.dependency_overrides[require_supabase_user_id] = lambda: OWNER_ID
    app.dependency_overrides[get_rebalancing_reminder_repository] = Repository
    try:
        with TestClient(app) as client:
            assert client.get("/me/rebalancing-reminder").status_code == 200
            assert client.put(
                "/me/rebalancing-reminder", json={"enabled": False}
            ).status_code == 200
            assert client.post("/me/rebalancing-reminder/complete").status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert calls == [
        ("get", OWNER_ID, None),
        ("update", OWNER_ID, False),
        ("complete", OWNER_ID, None),
    ]


def test_reminder_endpoint_requires_authentication() -> None:
    assert TestClient(app).get("/me/rebalancing-reminder").status_code == 401


def test_cors_allows_reminder_preference_put() -> None:
    response = TestClient(app).options(
        "/me/rebalancing-reminder",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
