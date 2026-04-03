"""
AI Worker — RabbitMQ consumer.

Listens on queue 'uav.ai', reads parse result metrics from Odoo,
generates an AI flight analysis conclusion using Qwen2.5-1.5B-Instruct
(+ LoRA fine-tune if available), and writes the conclusion back to Odoo.

The model is loaded on first message to avoid blocking startup.
Startup retries both RabbitMQ and Odoo with exponential back-off.
"""

import json
import logging
import os
import time

import pika
import pika.exceptions

from ai import AiOdooClient, generate_conclusion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ai_worker] %(levelname)s %(message)s",
)
_logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
ODOO_URL = os.environ.get("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.environ.get("ODOO_DB", "postgres")
ODOO_USER = os.environ.get("ODOO_USER", "admin")
ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")

QUEUE_AI = "uav.ai"
MAX_RETRIES = 60  # 60 × 10 s = 10 minutes (covers Odoo --init=base cold start)
RETRY_DELAY = 10  # seconds


# ── Connection helpers ────────────────────────────────────────────────────────
def connect_odoo() -> AiOdooClient:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = AiOdooClient(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
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
        heartbeat=600,
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


# ── Message callback ──────────────────────────────────────────────────────────
def make_callback(odoo: AiOdooClient):
    def callback(ch, method, properties, body):
        mission_id = None
        try:
            data = json.loads(body)
            mission_id = data["mission_id"]
            parse_result_id = data["parse_result_id"]

            _logger.info(
                "AI job: mission=%s  parse_result=%s", mission_id, parse_result_id
            )

            # 1. Mark mission as ai_processing
            odoo.set_mission_status(mission_id, "ai_processing")

            # 2. Read metrics from Odoo
            metrics = odoo.read_parse_result(parse_result_id)
            _logger.info("Metrics loaded for mission %s: %s", mission_id, metrics)

            # 3. Generate AI conclusion (loads model on first call)
            conclusion = generate_conclusion(metrics)
            _logger.info(
                "Conclusion generated for mission %s (%d chars)",
                mission_id,
                len(conclusion),
            )

            # 4. Save conclusion + mark done
            odoo.save_conclusion(mission_id, conclusion)

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as exc:
            _logger.exception("AI job failed for mission %s: %s", mission_id, exc)
            if mission_id:
                try:
                    odoo.set_mission_status(
                        mission_id,
                        "error",
                        error_message=f"AI worker error: {exc}",
                    )
                except Exception:
                    pass
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    return callback


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    _logger.info("AI Worker starting …")

    odoo = connect_odoo()
    conn = connect_rabbitmq()

    channel = conn.channel()
    channel.queue_declare(queue=QUEUE_AI, durable=True)
    channel.basic_qos(prefetch_count=1)  # one heavy inference job at a time

    channel.basic_consume(
        queue=QUEUE_AI,
        on_message_callback=make_callback(odoo),
    )

    _logger.info("Waiting for AI jobs on '%s'. CTRL+C to stop.", QUEUE_AI)
    channel.start_consuming()


if __name__ == "__main__":
    main()
