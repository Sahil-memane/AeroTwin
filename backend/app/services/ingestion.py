"""
MQTT-based telemetry ingestion service.

Subscribes to  aerotwin/telemetry/+  on the configured MQTT broker,
validates each payload against physical sensor bounds, persists valid
readings to TimescaleDB, and pushes them to connected WebSocket clients.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.telemetry_reading import TelemetryReading
from app.models.rul_prediction import RulPrediction
from app.ws.connection_manager import manager as ws_manager
from app.services.rul_adapter import piston_to_cmapss
from app.services.rul_service import rul_service

import uuid
DUMMY_MODEL_VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

logger = logging.getLogger(__name__)

# ── Physical sensor bounds for validation ────────────────────────────
# Values outside these hard limits are rejected as implausible.
SENSOR_BOUNDS = {
    "rpm":          (0, 6500),
    "cht":          (0, 400),       # °C  (raised to accommodate fault injection)
    "egt":          (0, 1000),      # °C
    "oil_pressure": (0, 150),       # psi
    "oil_temp":     (0, 200),       # °C
    "fuel_flow":    (0, 30),        # GPH
    "vibration_x":  (-50, 50),
    "vibration_y":  (-50, 50),
    "vibration_z":  (-50, 50),
    # Extended fields from the physics-aware simulator
    "throttle":             (0, 1.0),
    "altitude_m":           (-500, 15000),
    "deviation_score":      (0, 100),
    "vibration_magnitude":  (0, 100),
}


def _validate_payload(data: dict) -> Optional[str]:
    """Return an error string if any field is out of plausible range, else None."""
    for field, (lo, hi) in SENSOR_BOUNDS.items():
        value = data.get(field)
        if value is None:
            continue  # vibration fields are optional
        if not (lo <= value <= hi):
            return f"{field}={value} outside plausible range [{lo}, {hi}]"
    # Required fields
    for required in ("engine_id", "ts", "rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"):
        if required not in data or data[required] is None:
            return f"missing required field: {required}"
    return None


class MQTTIngestionService:
    """Runs paho-mqtt in a background thread; bridges messages into asyncio."""

    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._topic = "aerotwin/telemetry/+"

    # ── MQTT callbacks (run on paho's network thread) ────────────────
    def _on_connect(self, client, userdata, flags, rc, *args, **kwargs):
        if rc == 0 or (hasattr(rc, "is_failure") and not rc.is_failure):
            logger.info("MQTT connected — subscribing to %s", self._topic)
            client.subscribe(self._topic, qos=1)
        else:
            logger.error("MQTT connection failed (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, *args, **kwargs):
        rc = args[0] if args else kwargs.get("rc")
        logger.warning("MQTT disconnected (%s) — paho will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):
        """Schedule the async handler on the main event loop."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._handle_message(msg.topic, msg.payload), self._loop
            )

    # ── Async processing (runs on the FastAPI event loop) ────────────
    async def _handle_message(self, topic: str, raw: bytes):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON payload on %s — skipped", topic)
            return

        # Validate
        error = _validate_payload(data)
        if error:
            logger.warning("Rejected telemetry: %s  (payload=%s)", error, data)
            return

        # Parse timestamp
        ts_raw = data["ts"]
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        else:
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            
        # Strip timezone info because the DB column is TIMESTAMP WITHOUT TIME ZONE
        ts = ts.replace(tzinfo=None)

        # Persist to DB
        try:
            async with AsyncSessionLocal() as session:
                reading = TelemetryReading(
                    ts=ts,
                    engine_id=data["engine_id"],
                    mission_id=data.get("mission_id"),
                    rpm=data["rpm"],
                    cht=data["cht"],
                    egt=data["egt"],
                    oil_pressure=data["oil_pressure"],
                    oil_temp=data["oil_temp"],
                    fuel_flow=data["fuel_flow"],
                    vibration_x=data.get("vibration_x"),
                    vibration_y=data.get("vibration_y"),
                    vibration_z=data.get("vibration_z"),
                )
                session.add(reading)
                await session.commit()
        except Exception:
            logger.exception("Failed to persist telemetry reading")
            return

        # ── Build the enriched data dict for downstream consumers ────
        enriched = {
            **data,
            "ts": ts.isoformat(),
        }

        # Broadcast to WebSocket clients
        engine_id = str(data["engine_id"])
        ws_payload = {
            "type": "telemetry",
            "payload": {
                "engine_id": engine_id,
                "ts": ts.isoformat(),
                "rpm": data["rpm"],
                "throttle": data.get("throttle"),
                "altitude_m": data.get("altitude_m"),
                "cht": data["cht"],
                "egt": data["egt"],
                "oil_pressure": data["oil_pressure"],
                "oil_temp": data["oil_temp"],
                "fuel_flow": data["fuel_flow"],
                "vibration_x": data.get("vibration_x"),
                "vibration_y": data.get("vibration_y"),
                "vibration_z": data.get("vibration_z"),
                "vibration_magnitude": data.get("vibration_magnitude"),
                "deviation_score": data.get("deviation_score"),
            },
        }
        try:
            await ws_manager.broadcast_to_engine(engine_id, ws_payload)
        except Exception:
            logger.exception("WebSocket broadcast error for engine %s", engine_id)

        # ── RUL Inference ────────────────────────────────────────────
        try:
            # Map piston telemetry to CMAPSS format
            cmapss_row = piston_to_cmapss(data)
            
            # Fire inference synchronously for now (XGBoost is fast)
            # In a real heavy-load scenario, this could be pushed to a worker queue
            rul_result = rul_service.push_reading(engine_id, cmapss_row)
            
            if rul_result:
                # We got a prediction because the 30-cycle window is full
                rul_payload = {
                    "rul_cycles": rul_result["rul_cycles"],
                    "degradation_index": rul_result["degradation_index"],
                    "rul_lower": rul_result["rul_lower"],
                    "rul_upper": rul_result["rul_upper"]
                }
                
                # Save prediction to database
                async with AsyncSessionLocal() as session:
                    pred = RulPrediction(
                        ts=ts,
                        engine_id=data["engine_id"],
                        model_version_id=DUMMY_MODEL_VERSION_ID,
                        rul_cycles=rul_result["rul_cycles"],
                        degradation_index=rul_result["degradation_index"]
                    )
                    session.add(pred)
                    await session.commit()
                
                # Broadcast prediction via WebSocket
                await ws_manager.broadcast_to_engine(engine_id, {
                    "type": "rul_prediction",
                    "payload": rul_payload
                })
        except Exception:
            logger.exception("Failed to process RUL prediction")

    # ── Lifecycle ────────────────────────────────────────────────────
    def _parse_broker_url(self) -> tuple[str, int]:
        """Extract host and port from MQTT_BROKER_URL (e.g. mqtt://mqtt:1883)."""
        url = settings.MQTT_BROKER_URL or "mqtt://localhost:1883"
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 1883
        return host, port

    async def start(self):
        """Start the MQTT client (called from FastAPI lifespan)."""
        self._loop = asyncio.get_running_loop()
        host, port = self._parse_broker_url()

        if hasattr(mqtt, "CallbackAPIVersion"):
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "aerotwin-ingest")
        else:
            self._client = mqtt.Client("aerotwin-ingest")

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        logger.info("Connecting MQTT ingestion to %s:%s …", host, port)
        self._client.connect_async(host, port, keepalive=60)
        self._client.loop_start()  # Starts paho's background network thread

    async def stop(self):
        """Gracefully disconnect (called from FastAPI lifespan)."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT ingestion stopped")


# Module-level singleton
ingestion_service = MQTTIngestionService()
