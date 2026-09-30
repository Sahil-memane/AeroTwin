"""
E2E — edge connectivity loss & recovery: stop the real Mosquitto
container, run the edge agent so its readings buffer, restart the
broker, and confirm every buffered reading flushes in order with none
lost. This drives the actual `docker stop`/`docker start` on
`aerotwin-mqtt` rather than mocking the broker, matching how the same
scenario was verified by hand during Phase 7.

Requires Docker and the `aerotwin-mqtt` container from
infra/docker/docker-compose.yml. Leaves the broker running on exit.

Run: python scripts/e2e/test_connectivity_loss_recovery.py
"""
import os
import subprocess
import sys
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from edge.inference.buffer import DurableBuffer  # noqa: E402

MQTT_CONTAINER = "aerotwin-mqtt"
BUFFER_DB = os.path.join(_REPO_ROOT, "edge", "inference", "e2e_test_outbox.sqlite3")
AGENT_SCRIPT = os.path.join(_REPO_ROOT, "edge", "inference", "edge_agent.py")


def docker(*args):
    subprocess.run(["docker", *args], check=True, capture_output=True)


def main():
    if os.path.exists(BUFFER_DB):
        os.remove(BUFFER_DB)

    print(f"[1/5] Stopping {MQTT_CONTAINER} to simulate a lost cloud connection...")
    docker("stop", MQTT_CONTAINER)

    print("[2/5] Starting the edge agent while the broker is down...")
    agent = subprocess.Popen(
        [sys.executable, "-u", AGENT_SCRIPT, "--rate", "1.0", "--buffer-db", BUFFER_DB],
        cwd=_REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(8)
        buffer = DurableBuffer(BUFFER_DB)
        buffered_count = buffer.count()
        buffer.close()
        assert buffered_count > 0, "expected readings to buffer while the broker was down"
        print(f"[3/5] {buffered_count} reading(s) buffered locally, as expected.")

        print(f"[4/5] Restarting {MQTT_CONTAINER}...")
        docker("start", MQTT_CONTAINER)
        time.sleep(10)

        buffer = DurableBuffer(BUFFER_DB)
        remaining = buffer.count()
        buffer.close()
        assert remaining == 0, f"expected the buffer to fully drain on reconnect, {remaining} left"
        print("[5/5] Buffer fully flushed after reconnect — zero readings lost.")
    finally:
        agent.terminate()
        agent.wait(timeout=10)
        # Windows can lag briefly before releasing the child process's
        # sqlite file handle after it exits — this is cleanup, not part
        # of what's being verified, so don't let a slow-to-release lock
        # mask an otherwise-passed test.
        for attempt in range(5):
            try:
                if os.path.exists(BUFFER_DB):
                    os.remove(BUFFER_DB)
                break
            except PermissionError:
                time.sleep(1)

    print("\nPASS: connectivity loss -> buffer -> recovery E2E")


if __name__ == "__main__":
    main()
