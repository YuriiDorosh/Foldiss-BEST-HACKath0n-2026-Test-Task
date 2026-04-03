"""
Thin XML-RPC wrapper around the Odoo 18 external API.

Odoo exposes two XML-RPC endpoints:
  /xmlrpc/2/common  — authentication (no auth required)
  /xmlrpc/2/object  — model operations (requires uid + password)

References:
  https://www.odoo.com/documentation/18.0/developer/reference/external_api.html
"""

import base64
import logging
import xmlrpc.client
from typing import Any

_logger = logging.getLogger(__name__)


class OdooClient:
    """Authenticated XML-RPC client for Odoo."""

    def __init__(self, url: str, db: str, user: str, password: str) -> None:
        self.db = db
        self.password = password

        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise ConnectionError(
                f"Odoo authentication failed for user '{user}' on db '{db}' at {url}"
            )
        _logger.info("Authenticated with Odoo as uid=%s", self.uid)

    # ── Generic execute ──────────────────────────────────────────────────────
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

    # ── ir.attachment ────────────────────────────────────────────────────────
    def read_attachment(self, attachment_id: int) -> bytes:
        """Fetch the raw bytes of an ir.attachment record."""
        result = self.execute(
            "ir.attachment", "read", [attachment_id], fields=["datas", "name"]
        )
        if not result:
            raise ValueError(f"Attachment {attachment_id} not found in Odoo")
        name = result[0].get("name", "unknown")
        data = result[0].get("datas") or ""
        _logger.info("Fetched attachment '%s' (%d base64 chars)", name, len(data))
        return base64.b64decode(data)

    # ── uav.mission ──────────────────────────────────────────────────────────
    def update_mission(self, mission_id: int, vals: dict) -> None:
        """Write arbitrary fields on a uav.mission record."""
        self.execute("uav.mission", "write", [mission_id], vals)
        _logger.info("Updated mission %s: %s", mission_id, list(vals.keys()))

    # ── uav.parse.result ─────────────────────────────────────────────────────
    def create_parse_result(self, vals: dict) -> int:
        """Create a uav.parse.result record and return its ID."""
        result_id = self.execute("uav.parse.result", "create", vals)
        _logger.info(
            "Created parse result id=%s for mission %s",
            result_id,
            vals.get("mission_id"),
        )
        return result_id
