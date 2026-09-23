import os
import sys
import json
import time
import random
import uuid
import argparse
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Default parameters
DEFAULT_MQTT_HOST = "localhost"
DEFAULT_MQTT_PORT = 1883
DEFAULT_ENGINE_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_MISSION_ID = "00000000-0000-0000-0000-000000000002"

class EngineSimulator:
    def __init__(self, engine_id, mission_id):
        self.engine_id = engine_id
        self.mission_id = mission_id
        
        # Baselines
        self.rpm = 2400.0
        self.cht = 150.0
        self.egt = 650.0
        self.oil_pressure = 60.0
        self.oil_temp = 90.0
        self.fuel_flow = 8.0
        self.vib_x = 0.5
        self.vib_y = 0.5
        self.vib_z = 0.5
        
        self.synthetic_fault = False

    def trigger_fault(self):
        self.synthetic_fault = True
        print("\n>>> SYNTHETIC FAULT INJECTED! CHT will rapidly ramp up. <<<\n")

    def step(self):
        # Random walks around baseline
        self.rpm = max(0, self.rpm + random.uniform(-50, 50))
        if self.synthetic_fault:
            self.cht = min(350, self.cht + random.uniform(5, 10)) # Fault: CHT ramping up rapidly out of bounds
        else:
            self.cht = max(50, min(250, self.cht + random.uniform(-2, 2)))
            
        self.egt = max(200, min(900, self.egt + random.uniform(-10, 10)))
        self.oil_pressure = max(10, min(120, self.oil_pressure + random.uniform(-1, 1)))
        self.oil_temp = max(40, min(150, self.oil_temp + random.uniform(-1, 1)))
        self.fuel_flow = max(0, min(20, self.fuel_flow + random.uniform(-0.5, 0.5)))
        self.vib_x = max(0, min(10, self.vib_x + random.uniform(-0.1, 0.1)))
        self.vib_y = max(0, min(10, self.vib_y + random.uniform(-0.1, 0.1)))
        self.vib_z = max(0, min(10, self.vib_z + random.uniform(-0.1, 0.1)))

        return {
            "engine_id": self.engine_id,
            "mission_id": self.mission_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "rpm": round(self.rpm, 2),
            "cht": round(self.cht, 2),
            "egt": round(self.egt, 2),
            "oil_pressure": round(self.oil_pressure, 2),
            "oil_temp": round(self.oil_temp, 2),
            "fuel_flow": round(self.fuel_flow, 2),
            "vibration_x": round(self.vib_x, 2),
            "vibration_y": round(self.vib_y, 2),
            "vibration_z": round(self.vib_z, 2)
        }

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to MQTT broker!")
    else:
        print(f"Failed to connect, return code {rc}")

def listen_for_fault(sim):
    while True:
        try:
            cmd = input()
            if cmd.strip().lower() == 'f':
                sim.trigger_fault()
        except EOFError:
            break

def main():
    parser = argparse.ArgumentParser(description="AeroTwin Engine Telemetry Simulator")
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", DEFAULT_MQTT_HOST), help="MQTT broker host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", DEFAULT_MQTT_PORT)), help="MQTT broker port")
    parser.add_argument("--engine-id", default=os.getenv("ENGINE_ID", DEFAULT_ENGINE_ID), help="Engine UUID")
    parser.add_argument("--mission-id", default=os.getenv("MISSION_ID", DEFAULT_MISSION_ID), help="Mission UUID")
    parser.add_argument("--rate", type=float, default=1.0, help="Publish rate in seconds")
    parser.add_argument("--fault", action="store_true", help="Start with synthetic fault injected")
    
    args = parser.parse_args()

    sim = EngineSimulator(args.engine_id, args.mission_id)
    if args.fault:
        sim.trigger_fault()

    # Setup MQTT
    client_id = f"aerotwin-sim-{uuid.uuid4().hex[:8]}"
    if hasattr(mqtt, 'CallbackAPIVersion'):
        # For paho-mqtt 2.0.0+
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
    else:
        client = mqtt.Client(client_id)
        
    client.on_connect = on_connect
    
    print(f"Connecting to MQTT broker at {args.host}:{args.port}...")
    try:
        client.connect(args.host, args.port, 60)
    except Exception as e:
        print(f"Failed to connect to {args.host}:{args.port}: {e}")
        return

    client.loop_start()
    
    topic = f"aerotwin/telemetry/{args.engine_id}"
    print(f"Publishing to topic: {topic} at {args.rate}s intervals.")
    print("Press 'f' and ENTER at any time to inject a synthetic fault.")
    print("Press Ctrl+C to stop.")

    # Start interactive thread
    t = threading.Thread(target=listen_for_fault, args=(sim,), daemon=True)
    t.start()

    try:
        while True:
            payload = sim.step()
            client.publish(topic, json.dumps(payload), qos=1)
            print(f"Published: CHT={payload['cht']} RPM={payload['rpm']} EGT={payload['egt']}")
            time.sleep(args.rate)
    except KeyboardInterrupt:
        print("\nStopping simulator...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
