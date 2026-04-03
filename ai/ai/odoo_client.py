"""
Thin XML-RPC client for the AI worker.

Reads scalar metrics from uav.parse.result and writes the AI conclusion
back to uav.mission.
"""

import logging
import xmlrpc.client
from typing import Any

_logger = logging.getLogger(__name__)

SCALAR_FIELDS = [
    "total_distance",
    "max_h_speed",
    "max_v_speed",
    "max_acceleration",
    "max_altitude_gain",
    "flight_duration",
    "gps_count",
    "imu_count",
    "gps_sample_rate",
    "imu_sample_rate",
]


class AiOdooClient:
    """XML-RPC client for the AI worker."""

    def __init__(self, url: str, db: str, user: str, password: str) -> None:
        self.db = db
        self.password = password

        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise ConnectionError(
                f"Odoo auth failed for '{user}' on db '{db}' at {url}"
            )
        _logger.info("AI worker authenticated with Odoo uid=%s", self.uid)

    def execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        return self._models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            method,
            list(args),
            kwargs,
        )

    def read_parse_result(self, result_id: int) -> dict:
        """Return scalar metric fields from a uav.parse.result record."""
        rows = self.execute(
            "uav.parse.result", "read", [result_id], fields=SCALAR_FIELDS
        )
        if not rows:
            raise ValueError(f"uav.parse.result {result_id} not found")
        return rows[0]

    def save_conclusion(self, mission_id: int, conclusion: str) -> None:
        """Write ai_conclusion + status=done on a uav.mission record."""
        self.execute(
            "uav.mission",
            "write",
            [mission_id],
            {
                "ai_conclusion": conclusion,
                "status": "done",
            },
        )
        _logger.info("Saved AI conclusion to mission %s", mission_id)

    def set_mission_status(
        self, mission_id: int, status: str, error_message: str | None = None
    ) -> None:
        vals = {"status": status}
        if error_message:
            vals["error_message"] = error_message
        self.execute("uav.mission", "write", [mission_id], vals)
