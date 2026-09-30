"""
Phase 7 — the on-aircraft edge agent.

Reads telemetry from `edge/can_interface` (simulated today, real CAN
hardware later — see that module), runs Fault + RUL inference locally
via ONNX Runtime (`fault_runner.py`/`rul_runner.py` — no cloud call
needed for these two), and publishes each reading (telemetry + the
local predictions, tagged under `edge_fault`/`edge_rul` so they never
collide with the cloud pipeline's own authoritative predictions) to the
same MQTT topic `ingestion.py` already subscribes to.

Definition of Done this phase is built around: if the broker is
unreachable, readings go to a durable on-disk buffer instead of being
dropped; once reconnected, the buffer is flushed in original order,
oldest first, before any new live reading is published, so nothing is
lost and nothing arrives out of order.

Bearing/Aux stay cloud-side (per the phase plan) — this agent does not
run them locally.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from edge.can_interface.reader import SimulatedReader  # noqa: E402
from edge.inference.buffer import DurableBuffer  # noqa: E402
from edge.inference.fault_runner import EdgeFaultRunner  # noqa: E402
from edge.inference.rul_runner import EdgeRULRunner  # noqa: E402

DEFAULT_MQTT_HOST = "localhost"
DEFAULT_MQTT_PORT = 1883
DEFAULT_ENGINE_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_MISSION_ID = "00000000-0000-0000-0000-000000000002"
PUBLISH_TIMEOUT_S = 3.0


class EdgeAgent:
    def __init__(self, host: str, port: int, engine_id: str, buffer_db: str):
        self.engine_id = engine_id
        self.topic = f"aerotwin/telemetry/{engine_id}"
        self.connected = False
        self.flushing = False  # while True, new readings queue behind the buffer, not around it
        self.buffer = DurableBuffer(buffer_db)

        client_id = f"aerotwin-edge-{uuid.uuid4().hex[:8]}"
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
        else:
            self.client = mqtt.Client(client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self._host, self._port = host, port

    # ── Connection lifecycle ─────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            was_disconnected = not self.connected
            self.connected = True
            print(f"[edge] Connected to MQTT broker at {self._host}:{self._port}")
            if was_disconnected:
                # paho-mqtt's on_connect runs ON its single network I/O
                # thread. _flush_buffer() blocks on wait_for_publish() per
                # item, waiting for a PUBACK — a packet that same network
                # thread is responsible for reading. Calling it directly
                # here would deadlock (blocked waiting for a packet it
                # can't process until it stops blocking). Running the
                # flush on its own thread keeps the network thread free.
                threading.Thread(target=self._flush_buffer, daemon=True).start()
        else:
            print(f"[edge] MQTT connect failed, rc={rc}")

    def _on_disconnect(self, client, userdata, *args):
        if self.connected:
            print("[edge] Lost connection to MQTT broker — buffering readings locally.")
        self.connected = False

    def connect(self):
        # connect_async() + loop_start() (rather than a blocking connect())
        # retries in the background even if the broker is unreachable at
        # startup, not just on a later mid-run disconnect — readings from
        # the very first tick go straight to the buffer until it succeeds.
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.connect_async(self._host, self._port, keepalive=10)
        self.client.loop_start()

    # ── Buffering ─────────────────────────────────────────────────────
    def _publish_confirmed(self, topic: str, payload: dict) -> bool:
        """Publish and wait for QoS1 delivery confirmation. False = not delivered."""
        try:
            info = self.client.publish(topic, json.dumps(payload), qos=1)
            info.wait_for_publish(timeout=PUBLISH_TIMEOUT_S)
            return info.is_published()
        except (RuntimeError, ValueError):
            return False

    def _flush_buffer(self):
        pending = self.buffer.pending()
        if not pending:
            return
        # Block new live readings from cutting ahead of the backlog while
        # it drains — otherwise a reading produced *after* reconnect could
        # reach the broker before older buffered ones still in flight,
        # breaking the "no loss, right order" guarantee this phase is for.
        self.flushing = True
        print(f"[edge] Reconnected — flushing {len(pending)} buffered reading(s) in order...")
        flushed = 0
        for row_id, topic, payload in pending:
            if not self.connected:
                break  # dropped again mid-flush — stop, resume next reconnect
            if self._publish_confirmed(topic, payload):
                self.buffer.ack(row_id)
                flushed += 1
            else:
                break  # preserve order: don't skip ahead past an unconfirmed item
        self.flushing = False
        print(f"[edge] Flushed {flushed}/{len(pending)} buffered reading(s); "
              f"{self.buffer.count()} remain.")

    def publish_or_buffer(self, payload: dict):
        if self.connected and not self.flushing and self._publish_confirmed(self.topic, payload):
            return
        self.buffer.push(self.topic, payload)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
        self.buffer.close()


def listen_for_fault(reader: SimulatedReader):
    print("Commands: 'f' = CHT overheat, 'o' = oil pressure loss, 'v' = high vibration, 'c' = clear fault")
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == "f":
                reader.trigger_fault("cht_overheat")
            elif cmd == "o":
                reader.trigger_fault("oil_pressure_loss")
            elif cmd == "v":
                reader.trigger_fault("high_vibration")
            elif cmd == "c":
                reader.clear_fault()
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="AeroTwin Edge Agent (Phase 7)")
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", DEFAULT_MQTT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", DEFAULT_MQTT_PORT)))
    parser.add_argument("--engine-id", default=os.getenv("ENGINE_ID", DEFAULT_ENGINE_ID))
    parser.add_argument("--mission-id", default=os.getenv("MISSION_ID", DEFAULT_MISSION_ID))
    parser.add_argument("--rate", type=float, default=1.0, help="Reading interval in seconds")
    parser.add_argument("--fault", choices=["cht_overheat", "oil_pressure_loss", "high_vibration"], default=None)
    parser.add_argument("--buffer-db", default=os.path.join(os.path.dirname(__file__), "edge_outbox.sqlite3"))
    args = parser.parse_args()

    reader = SimulatedReader(args.engine_id, args.mission_id, dt=args.rate)
    if args.fault:
        reader.trigger_fault(args.fault)

    fault_runner = EdgeFaultRunner()
    rul_runner = EdgeRULRunner()

    agent = EdgeAgent(args.host, args.port, args.engine_id, args.buffer_db)
    agent.connect()

    threading.Thread(target=listen_for_fault, args=(reader,), daemon=True).start()

    print(f"[edge] Local ONNX Fault + RUL inference active. Publishing to "
          f"aerotwin/telemetry/{args.engine_id} at {args.rate}s intervals. Ctrl+C to stop.")

    try:
        while True:
            reading = reader.read()

            edge_fault = None
            edge_rul = None
            try:
                edge_fault = fault_runner.push_reading(args.engine_id, reading)
            except Exception as e:
                print(f"[edge] Local fault inference error: {e}")
            try:
                edge_rul = rul_runner.push_reading(args.engine_id, reading)
            except Exception as e:
                print(f"[edge] Local RUL inference error: {e}")

            payload = dict(reading)
            if edge_fault is not None:
                payload["edge_fault"] = edge_fault
            if edge_rul is not None:
                payload["edge_rul"] = edge_rul

            agent.publish_or_buffer(payload)

            status = "LIVE" if agent.connected else f"BUFFERED ({agent.buffer.count()} pending)"
            fault_str = edge_fault["fault_class"] if edge_fault else "warming up"
            rul_str = f"{edge_rul['rul_cycles']:.1f}cyc" if edge_rul else "warming up"
            print(f"[{status:>22}] phase={reading['phase']:>10} "
                  f"edge_fault={fault_str:<22} edge_rul={rul_str}")

            time.sleep(args.rate)
    except KeyboardInterrupt:
        print("\n[edge] Stopping...")
    finally:
        agent.close()


if __name__ == "__main__":
    main()
