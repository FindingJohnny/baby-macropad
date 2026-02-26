"""Baby Basics API client for logging baby events."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Timeout: 10s connect, 30s total (Pi on WiFi can be slow)
DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0)


@dataclass
class DashboardData:
    """Parsed dashboard response from the API."""

    active_sleep: dict[str, Any] | None = None
    last_feeding: dict[str, Any] | None = None
    last_diaper: dict[str, Any] | None = None
    last_sleep: dict[str, Any] | None = None
    suggested_side: str | None = None
    today_counts: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class BabyBasicsAPIError(Exception):
    """Raised when the Baby Basics API returns an error."""

    def __init__(self, status_code: int, message: str, details: list[dict] | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or []
        super().__init__(f"API error {status_code}: {message}")


class BabyBasicsClient:
    """HTTP client for the Baby Basics REST API."""

    def __init__(self, api_url: str, token: str, child_id: str):
        self.api_url = api_url.rstrip("/")
        self.child_id = child_id
        self._client = httpx.Client(
            base_url=f"{self.api_url}/children/{child_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )

    def close(self) -> None:
        self._client.close()

    def _handle_response(self, resp: httpx.Response) -> dict[str, Any]:
        """Check response status and return parsed JSON, or raise."""
        if resp.status_code >= 400:
            try:
                body = resp.json()
                error = body.get("error", {})
                raise BabyBasicsAPIError(
                    status_code=resp.status_code,
                    message=error.get("message", resp.text),
                    details=error.get("details", []),
                )
            except (ValueError, KeyError):
                raise BabyBasicsAPIError(resp.status_code, resp.text)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def log_feeding(self, **params: Any) -> dict[str, Any]:
        """POST /children/:childId/feedings"""
        logger.info("Logging feeding: %s", params)
        resp = self._client.post("/feedings", json=params)
        return self._handle_response(resp)

    def log_diaper(self, **params: Any) -> dict[str, Any]:
        """POST /children/:childId/diapers"""
        logger.info("Logging diaper: %s", params)
        resp = self._client.post("/diapers", json=params)
        return self._handle_response(resp)

    def start_sleep(self) -> dict[str, Any]:
        """POST /children/:childId/sleeps"""
        logger.info("Starting sleep")
        resp = self._client.post("/sleeps", json={})
        return self._handle_response(resp)

    def end_sleep(self, sleep_id: str) -> dict[str, Any]:
        """PATCH /children/:childId/sleeps/:id"""
        logger.info("Ending sleep: %s", sleep_id)
        end_time = datetime.now(timezone.utc).isoformat()
        resp = self._client.patch(f"/sleeps/{sleep_id}", json={"end_time": end_time})
        return self._handle_response(resp)

    def toggle_sleep(self, dashboard: DashboardData | None = None) -> dict[str, Any]:
        """Toggle sleep state: start if none active, end if one is active."""
        if dashboard and dashboard.active_sleep:
            sleep_id = dashboard.active_sleep.get("id")
            if sleep_id:
                return self.end_sleep(sleep_id)
        # Try to start sleep; if there's already an active one, the API returns 409
        try:
            return self.start_sleep()
        except BabyBasicsAPIError as e:
            if e.status_code == 409:
                logger.warning("Sleep already active (409), treating as no-op")
                return {"status": "already_active"}
            raise

    def log_note(self, **params: Any) -> dict[str, Any]:
        """POST /children/:childId/notes"""
        logger.info("Logging note: %s", params)
        resp = self._client.post("/notes", json=params)
        return self._handle_response(resp)

    def get_dashboard(self) -> DashboardData:
        """GET /children/:childId/dashboard"""
        resp = self._client.get("/dashboard")
        data = self._handle_response(resp)
        dashboard = data.get("dashboard", data)
        return DashboardData(
            active_sleep=dashboard.get("active_sleep"),
            last_feeding=dashboard.get("last_feeding"),
            last_diaper=dashboard.get("last_diaper"),
            last_sleep=dashboard.get("last_sleep"),
            suggested_side=dashboard.get("suggested_side"),
            today_counts=dashboard.get("today_counts", {}),
            raw=dashboard,
        )

    def check_connection(self) -> bool:
        """Quick health check — try to fetch dashboard."""
        try:
            self.get_dashboard()
            return True
        except Exception:
            return False
