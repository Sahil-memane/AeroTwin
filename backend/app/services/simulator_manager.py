import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Environment variable to explicitly select mode
_USE_DOCKER = os.getenv("SIMULATOR_USE_DOCKER", "auto").lower()

# Safety-net heartbeat: if the frontend hasn't pinged in this long, auto-stop.
# Set very high (1 h) — the real stop comes from the frontend on logout/window-close.
# Override via SIMULATOR_HEARTBEAT_TIMEOUT env var.
HEARTBEAT_TIMEOUT_SECONDS = int(os.getenv("SIMULATOR_HEARTBEAT_TIMEOUT", "3600"))


def _docker_available() -> bool:
    """Return True if the Docker SDK is importable and the socket exists."""
    if _USE_DOCKER == "false":
        return False
    if _USE_DOCKER == "true":
        return True
    try:
        import docker  # noqa: F401
        sock = os.getenv("DOCKER_HOST", "/var/run/docker.sock")
        return os.path.exists(sock) or os.getenv("DOCKER_HOST") is not None
    except ImportError:
        return False


class SimulatorManager:
    """
    Singleton that controls the live-telemetry simulator.

    Uses explicit on/off semantics — NOT ref-counted sessions.
    start() is idempotent; stop() only stops when explicitly called
    (user clicks Stop, logs out, or closes the browser window).

    A heartbeat watchdog acts only as a safety net for abandoned sessions
    (e.g. browser crash); the timeout is intentionally very long (24 h).
    """

    def __init__(self) -> None:
        # engine_id → True if the simulator is intentionally running
        self._running: dict[str, bool] = {}
        # engine_id → asyncio.Lock
        self._locks: dict[str, asyncio.Lock] = {}
        # engine_id → subprocess.Popen (subprocess mode only)
        self._procs: dict[str, subprocess.Popen] = {}
        # engine_id → last heartbeat timestamp (monotonic)
        self._last_heartbeat: dict[str, float] = {}
        # Watchdog task
        self._watchdog_task: Optional[asyncio.Task] = None
        # Whether we're using Docker or subprocess mode
        self._docker_mode: Optional[bool] = None

    def _get_lock(self, engine_id: str) -> asyncio.Lock:
        if engine_id not in self._locks:
            self._locks[engine_id] = asyncio.Lock()
        return self._locks[engine_id]

    @property
    def docker_mode(self) -> bool:
        if self._docker_mode is None:
            self._docker_mode = _docker_available()
            logger.info(
                "SimulatorManager: using %s mode",
                "Docker" if self._docker_mode else "subprocess",
            )
        return self._docker_mode


    # ── Docker helpers ────────────────────────────────────────────────

    def _docker_client(self):
        import docker
        return docker.from_env()

    def _container_name(self, engine_id: str) -> str:
        # One container per engine.  For the demo single-engine case the
        # default container name is reused; for multi-engine we'd need one
        # container per engine or a single container with an ENGINE_ID env var.
        # We keep it simple: one shared container, started/stopped per engine.
        return os.getenv("SIMULATOR_CONTAINER_NAME", "aerotwin-simulator")

    async def _docker_start(self, engine_id: str) -> None:
        try:
            import docker.errors  # noqa: PLC0415
            client = await asyncio.to_thread(self._docker_client)
            name = self._container_name(engine_id)
            mqtt_host = os.getenv("MQTT_HOST", "mqtt")
            image = os.getenv("SIMULATOR_IMAGE", "aerotwin-simulator:latest")
            # dev network = aerotwin_default, prod network = aerotwin-prod_default
            network = os.getenv("DOCKER_NETWORK", "aerotwin_default")

            try:
                container = await asyncio.to_thread(client.containers.get, name)
            except docker.errors.NotFound:
                container = None

            if container:
                state = container.status
                try:
                    if state in ("exited", "created"):
                        logger.info("SimulatorManager: starting container %s (was %s)", name, state)
                        await asyncio.to_thread(container.start)
                    elif state == "paused":
                        logger.info("SimulatorManager: unpausing container %s", name)
                        await asyncio.to_thread(container.unpause)
                    else:
                        logger.info("SimulatorManager: container %s already running (%s)", name, state)
                except docker.errors.APIError as e:
                    logger.warning("SimulatorManager: failed to start existing container (maybe network changed?). Removing it. Error: %s", e)
                    try:
                        await asyncio.to_thread(container.remove, force=True)
                    except Exception:
                        pass
                    container = None

            if not container:
                # Container doesn't exist (or was just removed) — create and start it.
                logger.info(
                    "SimulatorManager: creating container %s — docker run image=%s network=%s",
                    name, image, network,
                )
                try:
                    await asyncio.to_thread(
                        client.containers.run,
                        image,
                        name=name,
                        environment={"ENGINE_ID": engine_id, "MQTT_HOST": mqtt_host},
                        network=network,
                        detach=True,
                        remove=False,
                    )
                except docker.errors.APIError as e:
                    if e.response.status_code == 409:
                        # Conflict - another thread/process might have created it, or it was dangling
                        logger.warning("SimulatorManager: conflict creating container %s. Removing old and retrying.", name)
                        try:
                            old_container = await asyncio.to_thread(client.containers.get, name)
                            await asyncio.to_thread(old_container.remove, force=True)
                        except Exception:
                            pass
                        await asyncio.to_thread(
                            client.containers.run,
                            image,
                            name=name,
                            environment={"ENGINE_ID": engine_id, "MQTT_HOST": mqtt_host},
                            network=network,
                            detach=True,
                            remove=False,
                        )
                    else:
                        raise

            # Brief settle — give the process inside the container ~1 s to connect to MQTT
            await asyncio.sleep(1.5)
        except Exception:
            logger.exception("SimulatorManager: failed to start Docker container for engine %s", engine_id)
            raise

    async def _docker_stop(self, engine_id: str) -> None:
        """Stop (pause) the simulator Docker container."""
        try:
            client = await asyncio.to_thread(self._docker_client)
            name = self._container_name(engine_id)
            try:
                container = await asyncio.to_thread(client.containers.get, name)
                if container.status == "running":
                    logger.info("SimulatorManager: stopping container %s", name)
                    await asyncio.to_thread(container.stop, timeout=5)
            except Exception:
                logger.warning("SimulatorManager: container %s not found or already stopped", name)
        except Exception:
            logger.exception("SimulatorManager: failed to stop Docker container for engine %s", engine_id)

    # ── Subprocess helpers (dev) ──────────────────────────────────────

    def _subprocess_start(self, engine_id: str) -> None:
        """Start simulate.py as a child subprocess."""
        if engine_id in self._procs:
            proc = self._procs[engine_id]
            if proc.poll() is None:
                logger.info("SimulatorManager: subprocess already running for engine %s", engine_id)
                return
        # Find simulate.py relative to this file
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        script = os.path.join(repo_root, "edge", "telemetry_publisher", "simulate.py")
        mqtt_host = os.getenv("MQTT_HOST", "localhost")
        logger.info("SimulatorManager: spawning subprocess for engine %s", engine_id)
        proc = subprocess.Popen(
            [sys.executable, script, "--host", mqtt_host, "--engine-id", engine_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._procs[engine_id] = proc

    def _subprocess_stop(self, engine_id: str) -> None:
        """Terminate the simulator subprocess."""
        proc = self._procs.pop(engine_id, None)
        if proc and proc.poll() is None:
            logger.info("SimulatorManager: terminating subprocess for engine %s", engine_id)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # ── Public API ───────────────────────────────────────────────────

    async def start(self, engine_id: str) -> dict:
        """
        Start the simulator for `engine_id`.  Idempotent — calling again when
        already running simply refreshes the heartbeat and returns.
        """
        async with self._get_lock(engine_id):
            if not self._running.get(engine_id):
                # Not running — actually start it
                if self.docker_mode:
                    await self._docker_start(engine_id)
                else:
                    await asyncio.to_thread(self._subprocess_start, engine_id)
                self._running[engine_id] = True
                logger.info("SimulatorManager: started simulator for engine %s", engine_id)
            else:
                logger.info("SimulatorManager: simulator already running for engine %s — refreshing heartbeat", engine_id)
            # Always refresh heartbeat and ensure watchdog is alive
            self._last_heartbeat[engine_id] = time.monotonic()
            self._ensure_watchdog()
            return {"engine_id": engine_id, "status": "running"}

    async def stop(self, engine_id: str, force: bool = False) -> dict:
        """
        Explicitly stop the simulator for `engine_id`.
        This is the ONLY way the simulator stops (besides the safety-net watchdog).
        Navigating away from the Dashboard does NOT call this.
        """
        async with self._get_lock(engine_id):
            if not self._running.get(engine_id) and not force:
                return {"engine_id": engine_id, "status": "already_stopped"}

            self._running[engine_id] = False
            self._last_heartbeat.pop(engine_id, None)

            if self.docker_mode:
                await self._docker_stop(engine_id)
            else:
                await asyncio.to_thread(self._subprocess_stop, engine_id)

            logger.info("SimulatorManager: stopped simulator for engine %s (force=%s)", engine_id, force)
            return {"engine_id": engine_id, "status": "stopped"}

    def status(self, engine_id: str) -> dict:
        """Return running state.  Also refreshes the heartbeat to keep the watchdog satisfied."""
        if self.docker_mode:
            try:
                client = self._docker_client()
                name = self._container_name(engine_id)
                container = client.containers.get(name)
                running = container.status == "running"
            except Exception:
                running = False
        else:
            proc = self._procs.get(engine_id)
            running = proc is not None and proc.poll() is None

        # Sync internal flag with actual container state
        if running != self._running.get(engine_id, False):
            self._running[engine_id] = running

        # Refresh heartbeat while running (safety-net watchdog won't fire)
        if running:
            self._last_heartbeat[engine_id] = time.monotonic()

        return {"engine_id": engine_id, "status": "running" if running else "stopped"}

    def heartbeat(self, engine_id: str) -> None:
        """Lightweight ping — just refreshes the watchdog timestamp. No side effects."""
        if self._running.get(engine_id):
            self._last_heartbeat[engine_id] = time.monotonic()

    def _ensure_watchdog(self) -> None:
        """Start the heartbeat watchdog task if not already running."""
        if self._watchdog_task is None or self._watchdog_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._watchdog_task = loop.create_task(self._watchdog())
                self._watchdog_task.add_done_callback(
                    lambda _: logger.debug("SimulatorManager: watchdog stopped")
                )
            except RuntimeError:
                pass  # No event loop yet (startup)

    async def _watchdog(self) -> None:
        """
        Safety-net: stops simulators whose heartbeat has expired (e.g. browser crash).
        With HEARTBEAT_TIMEOUT_SECONDS=86400 this only fires after 24 h of silence.
        Exits when no simulators are running.
        """
        logger.info(
            "SimulatorManager: heartbeat watchdog started (timeout=%ds)",
            HEARTBEAT_TIMEOUT_SECONDS,
        )
        while True:
            await asyncio.sleep(60)  # Check every minute
            now = time.monotonic()
            timed_out = [
                eid
                for eid, ts in list(self._last_heartbeat.items())
                if self._running.get(eid) and (now - ts) > HEARTBEAT_TIMEOUT_SECONDS
            ]
            for engine_id in timed_out:
                logger.warning(
                    "SimulatorManager: heartbeat timeout for engine %s — auto-stopping",
                    engine_id,
                )
                try:
                    await self.stop(engine_id, force=True)
                except Exception:
                    logger.exception("SimulatorManager: watchdog failed to stop engine %s", engine_id)
            # Exit watchdog when no simulators are running
            if not any(v for v in self._running.values()):
                logger.info("SimulatorManager: watchdog exiting — no active simulators")
                return


# Module-level singleton
simulator_manager = SimulatorManager()
