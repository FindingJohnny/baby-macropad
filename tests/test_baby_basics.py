"""Tests for Baby Basics API client using respx to mock HTTP."""

import pytest
import respx
from httpx import Response

from baby_macropad.actions.baby_basics import (
    BabyBasicsAPIError,
    BabyBasicsClient,
    DashboardData,
)

API_URL = "https://example.com/api/v1"
TOKEN = "bb_test_token"
CHILD_ID = "child-uuid-123"
BASE = f"{API_URL}/children/{CHILD_ID}"


@pytest.fixture
def client():
    c = BabyBasicsClient(api_url=API_URL, token=TOKEN, child_id=CHILD_ID)
    yield c
    c.close()


@respx.mock
def test_log_feeding_breast(client: BabyBasicsClient):
    respx.post(f"{BASE}/feedings").mock(
        return_value=Response(201, json={"feeding": {"id": "f1", "type": "breast"}})
    )
    result = client.log_feeding(type="breast", started_side="left")
    assert result["feeding"]["type"] == "breast"


@respx.mock
def test_log_feeding_bottle(client: BabyBasicsClient):
    respx.post(f"{BASE}/feedings").mock(
        return_value=Response(201, json={"feeding": {"id": "f2", "type": "bottle"}})
    )
    result = client.log_feeding(type="bottle", amount_ml=120)
    assert result["feeding"]["type"] == "bottle"


@respx.mock
def test_log_diaper(client: BabyBasicsClient):
    respx.post(f"{BASE}/diapers").mock(
        return_value=Response(201, json={"diaper": {"id": "d1", "type": "pee"}})
    )
    result = client.log_diaper(type="pee")
    assert result["diaper"]["type"] == "pee"


@respx.mock
def test_start_sleep(client: BabyBasicsClient):
    respx.post(f"{BASE}/sleeps").mock(
        return_value=Response(201, json={"sleep": {"id": "s1", "start_time": "2026-01-01T00:00:00Z"}})
    )
    result = client.start_sleep()
    assert result["sleep"]["id"] == "s1"


@respx.mock
def test_end_sleep(client: BabyBasicsClient):
    respx.patch(f"{BASE}/sleeps/s1").mock(
        return_value=Response(200, json={"sleep": {"id": "s1", "end_time": "2026-01-01T02:00:00Z"}})
    )
    result = client.end_sleep("s1")
    assert "end_time" in result["sleep"]


@respx.mock
def test_toggle_sleep_starts_when_none_active(client: BabyBasicsClient):
    respx.post(f"{BASE}/sleeps").mock(
        return_value=Response(201, json={"sleep": {"id": "s2"}})
    )
    result = client.toggle_sleep(dashboard=None)
    assert result["sleep"]["id"] == "s2"


@respx.mock
def test_toggle_sleep_ends_when_active(client: BabyBasicsClient):
    respx.patch(f"{BASE}/sleeps/active-s1").mock(
        return_value=Response(200, json={"sleep": {"id": "active-s1", "end_time": "2026-01-01T03:00:00Z"}})
    )
    dashboard = DashboardData(active_sleep={"id": "active-s1", "start_time": "2026-01-01T01:00:00Z"})
    result = client.toggle_sleep(dashboard=dashboard)
    assert result["sleep"]["end_time"] == "2026-01-01T03:00:00Z"


@respx.mock
def test_toggle_sleep_409_is_noop(client: BabyBasicsClient):
    respx.post(f"{BASE}/sleeps").mock(
        return_value=Response(409, json={"error": {"code": "CONFLICT", "message": "Sleep already active", "details": []}})
    )
    result = client.toggle_sleep(dashboard=None)
    assert result["status"] == "already_active"


@respx.mock
def test_log_note(client: BabyBasicsClient):
    respx.post(f"{BASE}/notes").mock(
        return_value=Response(201, json={"note": {"id": "n1", "content": "Quick note"}})
    )
    result = client.log_note(content="Quick note")
    assert result["note"]["content"] == "Quick note"


@respx.mock
def test_get_dashboard(client: BabyBasicsClient):
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={
            "dashboard": {
                "active_sleep": {"id": "s1", "start_time": "2026-01-01T00:00:00Z"},
                "last_feeding": {"id": "f1", "type": "breast", "started_side": "left"},
                "last_diaper": {"id": "d1", "type": "pee"},
                "last_sleep": {"id": "s0", "end_time": "2025-12-31T23:00:00Z"},
                "suggested_side": "right",
                "today_counts": {"feedings": 6, "diapers": 4, "sleep_hours": 8.5},
            }
        })
    )
    dash = client.get_dashboard()
    assert dash.active_sleep is not None
    assert dash.active_sleep["id"] == "s1"
    assert dash.suggested_side == "right"
    assert dash.last_feeding["started_side"] == "left"
    assert dash.today_counts["feedings"] == 6


@respx.mock
def test_api_error_raises(client: BabyBasicsClient):
    respx.post(f"{BASE}/feedings").mock(
        return_value=Response(400, json={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid type",
                "details": [{"field": "type", "message": "Required", "code": "required"}],
            }
        })
    )
    with pytest.raises(BabyBasicsAPIError) as exc_info:
        client.log_feeding()
    assert exc_info.value.status_code == 400
    assert "Invalid type" in exc_info.value.message
    assert len(exc_info.value.details) == 1


@respx.mock
def test_auth_header_sent(client: BabyBasicsClient):
    route = respx.post(f"{BASE}/feedings").mock(
        return_value=Response(201, json={"feeding": {"id": "f1"}})
    )
    client.log_feeding(type="breast")
    assert route.called
    request = route.calls[0].request
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


@respx.mock
def test_check_connection_success(client: BabyBasicsClient):
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={"dashboard": {}})
    )
    assert client.check_connection() is True


@respx.mock
def test_check_connection_failure(client: BabyBasicsClient):
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(500, json={"error": {"code": "INTERNAL", "message": "fail", "details": []}})
    )
    assert client.check_connection() is False
