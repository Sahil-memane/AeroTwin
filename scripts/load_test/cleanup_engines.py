"""Deletes the throwaway engines seed_engines.py created (and their
telemetry readings) so the load test doesn't leave clutter in the
fleet dashboard. Run after the Locust run is done.

Run: python scripts/load_test/cleanup_engines.py
"""
import asyncio
import json
import os
import sys

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import delete  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.engine import Engine  # noqa: E402
from app.models.telemetry_reading import TelemetryReading  # noqa: E402

IDS_PATH = os.path.join(os.path.dirname(__file__), "engine_ids.json")


async def main():
    if not os.path.exists(IDS_PATH):
        print("No engine_ids.json found — nothing to clean up.")
        return
    with open(IDS_PATH) as f:
        ids = json.load(f)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(TelemetryReading).where(TelemetryReading.engine_id.in_(ids)))
        result = await session.execute(delete(Engine).where(Engine.id.in_(ids)))
        await session.commit()
        print(f"Deleted {result.rowcount} load-test engine(s) and their telemetry readings.")

    os.remove(IDS_PATH)


if __name__ == "__main__":
    asyncio.run(main())
