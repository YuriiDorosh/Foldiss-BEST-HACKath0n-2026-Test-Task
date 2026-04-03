"""
Parser Worker — RabbitMQ consumer.

Listens on queue 'uav.parse', fetches the .BIN file from Odoo,
runs the full parsing + metric pipeline, saves results back to Odoo,
then publishes a job to 'uav.ai' for AI analysis.

Startup retries both RabbitMQ and Odoo connections, because in a fresh
docker compose up the dependencies may not be ready immediately.
"""

import json
import logging
import os
import time

import pika
import pika.exceptions
from parser.bin_parser import write_temp_bin

from parser import OdooClient, compute_all_metrics, parse_bin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [parser] %(levelname)s %(message)s",
)
_logger = logging.getLogger(__name__)

# ── Configuration from environment ──────────────────────────────────────────
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
ODOO_URL = os.environ.get("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.environ.get("ODOO_DB", "postgres")
ODOO_USER = os.environ.get("ODOO_USER", "admin")
ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")

QUEUE_PARSE = "uav.parse"
QUEUE_AI = "uav.ai"
MAX_RETRIES = 60  # 60 × 10 s = 10 minutes (covers Odoo --init=base cold start)
RETRY_DELAY = 10  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────
def connect_odoo() -> OdooClient:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = OdooClient(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
            _logger.info("Connected to Odoo (attempt %d)", attempt)
            return client
        except Exception as exc:
            _logger.warning("Odoo not ready (%d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f"Could not connect to Odoo after {MAX_RETRIES} attempts")


def connect_rabbitmq() -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,  # keep-alive during long parse jobs
        blocked_connection_timeout=300,
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn = pika.BlockingConnection(params)
            _logger.info("Connected to RabbitMQ (attempt %d)", attempt)
            return conn
        except pika.exceptions.AMQPConnectionError as exc:
            _logger.warning("RabbitMQ not ready (%d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f"Could not connect to RabbitMQ after {MAX_RETRIES} attempts")


# ── Message callback ─────────────────────────────────────────────────────────
def make_callback(odoo: OdooClient, channel):
    def callback(ch, method, properties, body):
        data = {}
        mission_id = None
        try:
            data = json.loads(body)
            mission_id = data["mission_id"]
            att_id = data["attachment_id"]

            _logger.info("Processing mission %s (attachment %s)", mission_id, att_id)

            # 1. Update status → parsing
            odoo.update_mission(mission_id, {"status": "parsing"})

            # 2. Fetch .BIN file bytes from Odoo
            raw_bytes = odoo.read_attachment(att_id)
            tmp_path = write_temp_bin(raw_bytes, mission_id)

            # 3. Parse binary log
            gps, imu = parse_bin(tmp_path)
            _logger.info(
                "Mission %s: %d GPS records, %d IMU records",
                mission_id,
                len(gps),
                len(imu),
            )

            # 4. Compute all metrics (haversine + trapz + WGS-84→ENU)
            metrics = compute_all_metrics(gps, imu)
            _logger.info(
                "Mission %s metrics: distance=%.0fm  max_speed=%.2fm/s  duration=%.1fs",
                mission_id,
                metrics["total_distance"],
                metrics["max_h_speed"],
                metrics["flight_duration"],
            )

            # 5. Create parse result in Odoo
            scalar_keys = [
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
            result_vals = {k: metrics[k] for k in scalar_keys}
            result_vals["mission_id"] = mission_id
            result_vals["gps_points"] = json.dumps(metrics["gps_points"])
            result_vals["enu_points"] = json.dumps(metrics["enu_points"])
            result_vals["imu_data"] = json.dumps(metrics["imu_data"])

            result_id = odoo.create_parse_result(result_vals)

            # 6. Update mission: status → parsed, link result
            odoo.update_mission(
                mission_id,
                {
                    "status": "parsed",
                    "parse_result_id": result_id,
                },
            )

            # 7. Publish AI analysis job
            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_AI,
                body=json.dumps(
                    {
                        "mission_id": mission_id,
                        "parse_result_id": result_id,
                    }
                ),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            _logger.info("Mission %s: published to %s", mission_id, QUEUE_AI)

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as exc:
            _logger.exception("Mission %s failed: %s", mission_id, exc)
            if mission_id:
                try:
                    odoo.update_mission(
                        mission_id,
                        {
                            "status": "error",
                            "error_message": str(exc),
                        },
                    )
                except Exception:
                    pass
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    return callback


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    _logger.info("Parser Worker starting...")

    odoo = connect_odoo()
    conn = connect_rabbitmq()

    channel = conn.channel()
    channel.queue_declare(queue=QUEUE_PARSE, durable=True)
    channel.queue_declare(queue=QUEUE_AI, durable=True)
    channel.basic_qos(prefetch_count=1)  # process one job at a time

    channel.basic_consume(
        queue=QUEUE_PARSE,
        on_message_callback=make_callback(odoo, channel),
    )

    _logger.info("Waiting for messages on '%s'. Press CTRL+C to stop.", QUEUE_PARSE)
    channel.start_consuming()


if __name__ == "__main__":
    main()
