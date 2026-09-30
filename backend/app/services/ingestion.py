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

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.telemetry_reading import TelemetryReading
from app.models.rul_prediction import RulPrediction
from app.models.fault_prediction import FaultPrediction
from app.models.aux_prediction import AuxPrediction
from app.models.bearing_health_reading import BearingHealthReading
from app.models.physics_deviation_reading import PhysicsDeviationReading
from app.ws.connection_manager import manager as ws_manager
from app.services.rul_adapter import piston_to_cmapss
from app.services.rul_service import rul_service
from app.services.fault_service import fault_service
from app.services.aux_service import aux_service
from app.services.bearing_service import bearing_service
from app.services.physics_ingestion import compute_consistency
from app.services.validation import validate_payload, ValidationStatus
from app.models.health_score import HealthScore
from app.services.health_fusion import compute_health_score, fetch_latest_predictions, missing_sources, excluded_sources
from app.services.alert_engine import evaluate_and_alert

import uuid
DUMMY_MODEL_VERSION_ID   = uuid.UUID("00000000-0000-0000-0000-000000000003")
FAULT_MODEL_VERSION_ID   = uuid.UUID("00000000-0000-0000-0000-000000000004")
AUX_MODEL_VERSION_ID     = uuid.UUID("00000000-0000-0000-0000-000000000005")
BEARING_MODEL_VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000006")

logger = logging.getLogger(__name__)

class MQTTIngestionService:
    """Runs paho-mqtt in a background thread; bridges messages into asyncio."""

    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._topic = "aerotwin/telemetry/+"
        # One lock per engine_id — see _handle_message_serialized.
        self._engine_locks: dict[str, asyncio.Lock] = {}
        # Accuracy-First Phase 1: the last ACCEPTED (non-INVALID) reading
        # per engine, so validate_payload can detect duplicate/out-of-
        # order/implausible-jump readings relative to it. In-memory,
        # process-local — same lifecycle/limitation as _engine_locks and
        # rul_service's own sliding windows; lost on restart, not shared
        # across workers. [NEEDS VERIFICATION] if this ever runs multi-worker.
        self._last_reading: dict[str, dict] = {}

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
                self._handle_message_serialized(msg.topic, msg.payload), self._loop
            )

    async def _handle_message_serialized(self, topic: str, raw: bytes):
        """
        Every incoming message is scheduled independently via
        run_coroutine_threadsafe with no concurrency limit — paho
        delivers messages faster than one message's full chain of model
        inference + up to 6 sequential DB round-trips can complete, so
        without this, in-flight _handle_message calls pile up faster
        than they drain. Proven live: this exhausted the DB connection
        pool (default 5 + 10 overflow = 15) permanently within minutes
        of a single demo engine publishing at 0.5s intervals, well below
        Phase 8's ~50-engine load target — every request after that
        failed with a 30s pool-checkout timeout until the process was
        restarted. A per-engine lock caps concurrent in-flight messages
        at one per engine (different engines still process in
        parallel), which bounds total open sessions and — as a bonus —
        guarantees each engine's RUL/Fault sliding-window state updates
        in true arrival order rather than however asyncio happens to
        interleave them.
        """
        try:
            engine_id = str(json.loads(raw).get("engine_id"))
        except (json.JSONDecodeError, AttributeError):
            engine_id = None

        if not engine_id:
            await self._handle_message(topic, raw)
            return

        lock = self._engine_locks.setdefault(engine_id, asyncio.Lock())
        async with lock:
            await self._handle_message(topic, raw)

    # ── Async processing (runs on the FastAPI event loop) ────────────
    async def _handle_message(self, topic: str, raw: bytes):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON payload on %s — skipped", topic)
            return

        # Validate — INVALID is dropped (as before); STALE/SUSPICIOUS are
        # accepted but flagged (`quality_status`, below), since they're
        # heuristic/relative checks that can have legitimate explanations
        # (a network gap, clock skew) rather than unambiguous corruption.
        engine_id_raw = str(data.get("engine_id")) if data.get("engine_id") else None
        previous = self._last_reading.get(engine_id_raw) if engine_id_raw else None
        result = validate_payload(data, previous=previous)
        if result.rejected:
            logger.warning("Rejected telemetry [%s]: %s  (payload=%s)", result.status.value, result.reason, data)
            return
        if result.status != ValidationStatus.VALID:
            logger.info("Accepted telemetry flagged %s for engine %s: %s", result.status.value, engine_id_raw, result.reason)
        if engine_id_raw:
            self._last_reading[engine_id_raw] = data

        # Parse timestamp
        ts_raw = data["ts"]
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        else:
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            
        # Strip timezone info because the DB column is TIMESTAMP WITHOUT TIME ZONE
        ts = ts.replace(tzinfo=None)

        # ── Physics Consistency (Accuracy-First Phase 4) ───────────────
        # Replaces whatever `deviation_score` the client happened to
        # supply (previously defaulted to 0.0/"nominal" for any source
        # other than the demo simulator — rul_adapter.piston_to_cmapss's
        # own fallback) with a real, server-computed value from the
        # already-built Otto-cycle physics model, for every reading
        # regardless of source. Deliberately NOT asyncio.to_thread'd like
        # the 4 ML inference blocks below — this is plain arithmetic on
        # an already-loaded closed-form solver, not model inference, so
        # it doesn't block the event loop meaningfully.
        try:
            deviation_score, consistency_results = compute_consistency(data)
            data["deviation_score"] = deviation_score

            async with AsyncSessionLocal() as session:
                for r in consistency_results:
                    session.add(PhysicsDeviationReading(
                        ts=ts,
                        engine_id=data["engine_id"],
                        parameter=r.parameter,
                        expected=r.expected,
                        measured=r.measured,
                        residual=r.residual,
                        status=r.status,
                        method=r.method,
                    ))
                await session.commit()

            await ws_manager.broadcast_to_engine(str(data["engine_id"]), {
                "type": "physics_consistency",
                "payload": {
                    "ts": ts.isoformat(),
                    "deviation_score": deviation_score,
                    "parameters": [vars(r) for r in consistency_results],
                },
            })
        except Exception:
            logger.exception("Failed to process physics consistency")

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
                    throttle=data.get("throttle"),
                    altitude_m=data.get("altitude_m"),
                    quality_status=result.status.value,
                )
                session.add(reading)
                await session.commit()
        except Exception:
            logger.exception("Failed to persist telemetry reading")
            return

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

            # asyncio.to_thread: push_reading is synchronous/CPU-bound
            # (XGBoost inference). Calling it directly blocks the whole
            # event loop for its duration — harmless at low message
            # rates, but every other in-flight request (including other
            # engines' _handle_message calls and their own DB commits)
            # stalls behind it too. Proven live: a long-blocked request
            # elsewhere on the loop let enough concurrent
            # _handle_message calls pile up to exhaust the DB connection
            # pool (15 max) — see Phase 8 notes. Same fix already applied
            # to the Phase 6 replay path for the identical reason.
            rul_result = await asyncio.to_thread(rul_service.push_reading, engine_id, cmapss_row)
            
            if rul_result:
                # We got a prediction because the 30-cycle window is full
                rul_payload = {
                    "rul_cycles": rul_result["rul_cycles"],
                    "degradation_index": rul_result["degradation_index"],
                    "rul_lower": rul_result["rul_lower"],
                    "rul_upper": rul_result["rul_upper"],
                    "status": rul_result["status"],
                }
                
                # Save prediction to database — rul_lower/rul_upper (a
                # real split-conformal interval, not invented — see the
                # migration docstring) and status are now persisted
                # (Accuracy-First Phase 2), not just broadcast and dropped.
                async with AsyncSessionLocal() as session:
                    pred = RulPrediction(
                        ts=ts,
                        engine_id=data["engine_id"],
                        model_version_id=DUMMY_MODEL_VERSION_ID,
                        rul_cycles=rul_result["rul_cycles"],
                        degradation_index=rul_result["degradation_index"],
                        rul_lower=rul_result["rul_lower"],
                        rul_upper=rul_result["rul_upper"],
                        status=rul_result["status"],
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

        # ── Fault Inference ──────────────────────────────────────────
        try:
            fault_result = await asyncio.to_thread(fault_service.push_reading, engine_id, data)
            if fault_result:
                fault_payload = {
                    "class_id": fault_result["class_id"],
                    "fault_class": fault_result["fault_class"],
                    "confidence": fault_result["confidence"],
                    "probabilities": fault_result["probabilities"],
                    "state": fault_result["state"],
                    # Advisory (reliable=False) results are shown but excluded from Health Fusion.
                    "input_coverage": fault_result["input_coverage"],
                    "reliable": fault_result["reliable"],
                }

                async with AsyncSessionLocal() as session:
                    fault_pred = FaultPrediction(
                        ts=ts,
                        engine_id=data["engine_id"],
                        model_version_id=FAULT_MODEL_VERSION_ID,
                        class_id=fault_result["class_id"],
                        fault_class=fault_result["fault_class"],
                        confidence=fault_result["confidence"],
                        probabilities=fault_result["probabilities"],
                        state=fault_result["state"],
                        input_coverage=fault_result["input_coverage"],
                    )
                    session.add(fault_pred)
                    await session.commit()
                
                await ws_manager.broadcast_to_engine(engine_id, {
                    "type": "fault_prediction",
                    "payload": fault_payload
                })
        except Exception:
            logger.exception("Failed to process Fault prediction")

        # ── Aux Inference ────────────────────────────────────────────
        try:
            aux_result = await asyncio.to_thread(aux_service.push_reading, engine_id, data)
            if aux_result:
                aux_payload = {
                    "failure_status": aux_result["failure_status"],
                    "risk_level": aux_result["risk_level"],
                    "failure_probability_pct": aux_result["failure_probability_pct"],
                    "detected_failure_types": aux_result["detected_failure_types"],
                    "primary_failure_cause": aux_result["primary_failure_cause"],
                    "recommended_action": aux_result["recommended_action"]
                }
                
                async with AsyncSessionLocal() as session:
                    aux_pred = AuxPrediction(
                        ts=ts,
                        engine_id=data["engine_id"],
                        model_version_id=AUX_MODEL_VERSION_ID,
                        failure_status=aux_result["failure_status"],
                        risk_level=aux_result["risk_level"],
                        failure_probability_pct=aux_result["failure_probability_pct"],
                        detected_failure_types=aux_result["detected_failure_types"],
                        primary_failure_cause=aux_result["primary_failure_cause"],
                        recommended_action=aux_result["recommended_action"]
                    )
                    session.add(aux_pred)
                    await session.commit()
                
                await ws_manager.broadcast_to_engine(engine_id, {
                    "type": "aux_prediction",
                    "payload": aux_payload
                })
        except Exception:
            logger.exception("Failed to process Aux prediction")

        # ── Bearing Inference ─────────────────────────────────────────
        try:
            bearing_result = await asyncio.to_thread(bearing_service.push_reading, engine_id, data)
            if bearing_result:
                bearing_payload = {
                    "class_id":        bearing_result["class_id"],
                    "class_label":     bearing_result["class_label"],
                    "fault_location":  bearing_result["fault_location"],
                    "severity_inches": bearing_result["severity_inches"],
                    "confidence":      bearing_result["confidence"],
                }

                async with AsyncSessionLocal() as session:
                    bearing_pred = BearingHealthReading(
                        ts=ts,
                        engine_id=data["engine_id"],
                        model_version_id=BEARING_MODEL_VERSION_ID,
                        class_id=bearing_result["class_id"],
                        class_label=bearing_result["class_label"],
                        fault_location=bearing_result["fault_location"],
                        severity_inches=bearing_result["severity_inches"],
                        confidence=bearing_result["confidence"],
                    )
                    session.add(bearing_pred)
                    await session.commit()

                await ws_manager.broadcast_to_engine(engine_id, {
                    "type": "bearing_prediction",
                    "payload": bearing_payload
                })
        except Exception:
            logger.exception("Failed to process Bearing prediction")

        # ── Health Fusion & Alerting ───────────────────────────────────
        # Runs after every message regardless of which windowed models
        # (RUL/Fault) actually fired this cycle — it always fuses
        # whatever the latest known prediction of each type is.
        try:
            async with AsyncSessionLocal() as session:
                latest_rul, latest_fault, latest_bearing, latest_aux = await fetch_latest_predictions(
                    session, data["engine_id"], as_of=ts
                )
                health_result = compute_health_score(latest_rul, latest_fault, latest_bearing, latest_aux)
                unavailable = missing_sources(latest_rul, latest_fault, latest_bearing, latest_aux)
                excluded = excluded_sources(latest_fault)

                session.add(HealthScore(
                    ts=ts,
                    engine_id=data["engine_id"],
                    combined_score=health_result.combined_score,
                    contributing_factors=health_result.contributing_factors,
                    primary_concern=health_result.primary_concern,
                ))
                await session.commit()

                await ws_manager.broadcast_to_engine(engine_id, {
                    "type": "health_score",
                    "payload": {
                        "combined_score": health_result.combined_score,
                        "contributing_factors": health_result.contributing_factors,
                        "primary_concern": health_result.primary_concern,
                        # Sources with no fresh prediction (e.g. windows still
                        # warming up): the score excludes them, so it is a
                        # partial assessment, not a clean bill of health.
                        "missing_sources": unavailable,
                        # Present but deliberately not scored (fault model input coverage too low).
                        "excluded_sources": excluded,
                        "ts": ts.isoformat(),
                    },
                })

                await evaluate_and_alert(session, data["engine_id"], ts, health_result)
        except Exception:
            logger.exception("Failed to process health fusion / alerting")

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
