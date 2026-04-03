import json
import logging
import os

import pika
import pika.exceptions
from odoo.exceptions import UserError

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

QUEUE_PARSE = "uav.parse"


class UavMission(models.Model):
    _name = "uav.mission"
    _description = "UAV Flight Mission"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    # ── Core fields ─────────────────────────────────────────────────────────
    name = fields.Char(
        string="Mission Name",
        required=True,
        tracking=True,
    )
    log_file = fields.Binary(
        string="BIN Log File",
        attachment=True,  # stored via ir.attachment, not inline in DB
    )
    log_filename = fields.Char(string="Log Filename")
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True,
    )

    # ── Status ───────────────────────────────────────────────────────────────
    status = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("parsing", "Parsing"),
            ("parsed", "Parsed"),
            ("ai_processing", "AI Processing"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        tracking=True,
        string="Status",
    )
    error_message = fields.Text(string="Error Message", readonly=True)

    # ── Results ──────────────────────────────────────────────────────────────
    parse_result_id = fields.Many2one(
        comodel_name="uav.parse.result",
        string="Parse Result",
        readonly=True,
        ondelete="set null",
    )
    ai_conclusion = fields.Text(string="AI Conclusion", readonly=True)

    # ── Related metrics (pulled from parse result for easy display) ──────────
    result_total_distance = fields.Float(
        related="parse_result_id.total_distance",
        string="Total Distance (m)",
        readonly=True,
    )
    result_max_h_speed = fields.Float(
        related="parse_result_id.max_h_speed",
        string="Max Horizontal Speed (m/s)",
        readonly=True,
    )
    result_max_v_speed = fields.Float(
        related="parse_result_id.max_v_speed",
        string="Max Vertical Speed (m/s)",
        readonly=True,
    )
    result_max_acceleration = fields.Float(
        related="parse_result_id.max_acceleration",
        string="Max Acceleration (m/s²)",
        readonly=True,
    )
    result_max_altitude_gain = fields.Float(
        related="parse_result_id.max_altitude_gain",
        string="Max Altitude Gain (m)",
        readonly=True,
    )
    result_flight_duration = fields.Float(
        related="parse_result_id.flight_duration",
        string="Flight Duration (s)",
        readonly=True,
    )
    result_gps_count = fields.Integer(
        related="parse_result_id.gps_count",
        string="GPS Points",
        readonly=True,
    )
    result_imu_count = fields.Integer(
        related="parse_result_id.imu_count",
        string="IMU Samples",
        readonly=True,
    )
    result_gps_sample_rate = fields.Float(
        related="parse_result_id.gps_sample_rate",
        string="GPS Sample Rate (Hz)",
        readonly=True,
    )
    result_imu_sample_rate = fields.Float(
        related="parse_result_id.imu_sample_rate",
        string="IMU Sample Rate (Hz)",
        readonly=True,
    )

    # ── Actions ──────────────────────────────────────────────────────────────
    def action_start_parsing(self):
        self.ensure_one()

        # Validate file
        if not self.log_file:
            raise UserError(_("Please upload a .BIN flight log file first."))
        filename = self.log_filename or ""
        if not filename.lower().endswith(".bin"):
            raise UserError(_("Only ArduPilot .BIN log files are supported."))

        # Find the ir.attachment record for this binary field
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "uav.mission"),
                ("res_field", "=", "log_file"),
                ("res_id", "=", self.id),
            ],
            limit=1,
        )
        if not attachment:
            raise UserError(
                _("Attachment record not found. Try re-uploading the file.")
            )

        # Reset any previous results
        self.write(
            {
                "status": "queued",
                "error_message": False,
                "ai_conclusion": False,
            }
        )
        if self.parse_result_id:
            self.parse_result_id.unlink()
            self.parse_result_id = False

        # Publish job to RabbitMQ
        try:
            self._publish_to_queue(
                QUEUE_PARSE,
                {"mission_id": self.id, "attachment_id": attachment.id},
            )
        except Exception as exc:
            self.write(
                {
                    "status": "error",
                    "error_message": f"Failed to publish parse job: {exc}",
                }
            )
            raise UserError(
                _(
                    "Could not connect to the message queue. "
                    "Make sure RabbitMQ is running.\n\nDetails: %s"
                )
                % exc
            ) from exc

        _logger.info(
            "Mission %s queued for parsing (attachment %s)", self.id, attachment.id
        )
        return True

    def action_rerun(self):
        """Reset this mission to draft and resubmit the full parse → AI flow."""
        self.ensure_one()
        self.write(
            {
                "status": "draft",
                "error_message": False,
                "ai_conclusion": False,
            }
        )
        if self.parse_result_id:
            self.parse_result_id.unlink()
            self.parse_result_id = False
        return self.action_start_parsing()

    def action_open_viewer(self):
        """Open the 3D trajectory viewer in a new browser tab."""
        self.ensure_one()
        viewer_base = os.environ.get("VIEWER_URL", "http://localhost:3000")
        return {
            "type": "ir.actions.act_url",
            "url": f"{viewer_base}/mission/{self.id}",
            "target": "new",
        }

    # ── Private helpers ──────────────────────────────────────────────────────
    def _publish_to_queue(self, queue: str, payload: dict) -> None:
        """Publish a JSON message to a RabbitMQ durable queue.

        Uses a short-lived BlockingConnection — never hold pika connections
        across Odoo ORM transactions (it would block the web worker).
        """
        host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
        user = os.environ.get("RABBITMQ_USER", "guest")
        password = os.environ.get("RABBITMQ_PASSWORD", "guest")

        credentials = pika.PlainCredentials(user, password)
        params = pika.ConnectionParameters(
            host=host,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=1,
            socket_timeout=5,
            heartbeat=60,
        )
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2),  # persistent
            )
            _logger.info("Published to queue '%s': %s", queue, payload)
        finally:
            connection.close()
