import json
import logging
import re

from odoo.http import request

from odoo import http

_logger = logging.getLogger(__name__)


class UavController(http.Controller):
    """HTTP endpoints used by parser/AI workers and the React frontend."""

    # ── Worker webhook (POST, JSON-RPC) ──────────────────────────────────────
    @http.route(
        "/uav/webhook",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def webhook(self):
        """Called by Parser and AI workers to push status updates to Odoo.

        Expected JSON body:
            {
                "jsonrpc": "2.0", "method": "call",
                "params": {
                    "mission_id": <int>,
                    "status": <str>,           optional
                    "error_message": <str>,    optional
                    "parse_result_id": <int>,  optional
                    "ai_conclusion": <str>     optional
                }
            }
        """
        params = request.jsonrequest.get("params", {})
        mission_id = params.get("mission_id")

        if not mission_id:
            return {"error": "mission_id is required"}

        mission = request.env["uav.mission"].sudo().browse(int(mission_id))
        if not mission.exists():
            return {"error": f"Mission {mission_id} not found"}

        vals = {}
        for field in ("status", "error_message", "parse_result_id", "ai_conclusion"):
            if field in params:
                vals[field] = params[field]

        # Convert markdown AI conclusion to HTML for Odoo rendering
        if "ai_conclusion" in vals and vals["ai_conclusion"]:
            vals["ai_conclusion"] = self._markdown_to_html(vals["ai_conclusion"])

        if vals:
            mission.write(vals)
            _logger.info(
                "Webhook updated mission %s: %s", mission_id, list(vals.keys())
            )

        return {"success": True, "mission_id": mission_id}

    @staticmethod
    def _markdown_to_html(text):
        """Lightweight markdown → HTML for AI conclusion rendering."""
        lines = text.split("\n")
        html_lines = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            # Headers
            if stripped.startswith("#### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h5>{stripped[5:]}</h5>")
            elif stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h4>{stripped[4:]}</h4>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{stripped[3:]}</h3>")
            # Bullet points
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                content = stripped[2:]
                # Bold markers
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                html_lines.append(f"<li>{content}</li>")
            # Blank line
            elif stripped == "":
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br/>")
            # Regular paragraph
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
                html_lines.append(f"<p>{content}</p>")
        if in_list:
            html_lines.append("</ul>")
        return "\n".join(html_lines)

    # ── Frontend: status poll (GET) ───────────────────────────────────────────
    @http.route(
        "/uav/api/mission/<int:mission_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def mission_status(self, mission_id, **kwargs):
        """Lightweight status endpoint — polled by the frontend every 3 s."""
        mission = request.env["uav.mission"].sudo().browse(mission_id)
        if not mission.exists():
            return request.make_json_response(
                {"error": "Mission not found"}, status=404
            )

        return request.make_json_response(
            {
                "id": mission.id,
                "name": mission.name,
                "status": mission.status,
                "error_message": mission.error_message or "",
            }
        )

    # ── Frontend: full trajectory data (GET) ──────────────────────────────────
    @http.route(
        "/uav/api/mission/<int:mission_id>/trajectory",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def mission_trajectory(self, mission_id, **kwargs):
        """Returns all metrics + trajectory JSON for the 3D viewer frontend.

        Called once the React frontend detects status in
        {parsed, ai_processing, done}.
        """
        mission = request.env["uav.mission"].sudo().browse(mission_id)
        if not mission.exists():
            return request.make_json_response(
                {"error": "Mission not found"}, status=404
            )

        result = mission.parse_result_id

        payload = {
            "id": mission.id,
            "name": mission.name,
            "status": mission.status,
            "ai_conclusion": mission.ai_conclusion or "",
            "ai_status": mission.status,  # frontend uses this for AiConclusion
        }

        if not result:
            return request.make_json_response(payload)

        # Deserialise JSON trajectory and IMU arrays
        def safe_json(raw, fallback):
            try:
                return json.loads(raw or "[]")
            except (json.JSONDecodeError, TypeError):
                return fallback

        gps_points = safe_json(result.gps_points, [])
        enu_points = safe_json(result.enu_points, [])
        imu_data = safe_json(result.imu_data, {})
        analytics = safe_json(result.analytics, {})

        payload.update(
            {
                # Scalar metrics
                "total_distance": result.total_distance,
                "max_h_speed": result.max_h_speed,
                "max_v_speed": result.max_v_speed,
                "max_acceleration": result.max_acceleration,
                "max_altitude_gain": result.max_altitude_gain,
                "flight_duration": result.flight_duration,
                "gps_count": result.gps_count,
                "imu_count": result.imu_count,
                "gps_sample_rate": result.gps_sample_rate,
                "imu_sample_rate": result.imu_sample_rate,
                # Trajectory + IMU arrays
                "gps_points": gps_points,
                "enu_points": enu_points,
                "imu_data": imu_data,
                "analytics": analytics,
            }
        )

        return request.make_json_response(payload)
