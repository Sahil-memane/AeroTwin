# Demo telemetry source: runs edge/telemetry_publisher/simulate.py (the physics-based EngineSimulator).
# Started ON-DEMAND by the backend API (POST /api/v1/simulator/{engine_id}/start) — it is NOT
# auto-started by docker compose; the `profiles: [demo]` flag in docker-compose.prod.yml prevents that.
#
# In production the source tree is COPIED into the image (not bind-mounted) so the image is self-contained.
FROM python:3.12-slim
WORKDIR /app

# Copy only what the simulator needs
COPY edge/telemetry_publisher/ edge/telemetry_publisher/
COPY ml/ ml/

RUN pip install --no-cache-dir paho-mqtt numpy scipy

ENV PYTHONUNBUFFERED=1 \
    MQTT_HOST=mqtt \
    MQTT_PORT=1883 \
    ENGINE_ID=00000000-0000-0000-0000-000000000001 \
    MISSION_ID=00000000-0000-0000-0000-000000000002

# Use shell form so $ENGINE_ID / $MQTT_HOST are expanded from the container environment at runtime.
CMD python edge/telemetry_publisher/simulate.py \
      --host "$MQTT_HOST" \
      --port "$MQTT_PORT" \
      --engine-id "$ENGINE_ID" \
      --mission-id "$MISSION_ID" \
      --rate 1.0
