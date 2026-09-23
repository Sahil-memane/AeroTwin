import json
import logging
from typing import Dict, List, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages per-engine WebSocket connections for live telemetry broadcast."""

    def __init__(self):
        # Maps engine_id (str) -> list of active WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, engine_id: str):
        """Accept a WebSocket and register it under the given engine_id."""
        await websocket.accept()
        if engine_id not in self._connections:
            self._connections[engine_id] = []
        self._connections[engine_id].append(websocket)
        logger.info(
            "WebSocket connected for engine %s (total: %d)",
            engine_id,
            len(self._connections[engine_id]),
        )

    def disconnect(self, websocket: WebSocket, engine_id: str):
        """Remove a WebSocket from the engine's connection list."""
        if engine_id in self._connections:
            try:
                self._connections[engine_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[engine_id]:
                del self._connections[engine_id]
        logger.info("WebSocket disconnected for engine %s", engine_id)

    async def broadcast_to_engine(self, engine_id: str, message: Any):
        """Send a JSON message to every client watching the given engine."""
        if engine_id not in self._connections:
            return

        payload = json.dumps(message)
        stale: List[WebSocket] = []

        for ws in self._connections[engine_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)

        # Clean up dead sockets
        for ws in stale:
            self.disconnect(ws, engine_id)


# Module-level singleton so ingestion + API share the same instance
manager = ConnectionManager()
