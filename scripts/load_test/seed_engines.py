"""
Seeds N throwaway Engine rows for the Locust ingestion load test (each
simulated "edge device" needs a real engine_id — `POST /telemetry/ingest`
404s on an unknown one, by design). Writes their ids to engine_ids.json
for locustfile.py to load.

Run: python scripts/load_test/seed_engines.py [N]
"""
import asyncio
import json
import os
import sys
import uuid

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, _BACKEND_ROOT)

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.engine import Engine  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
OUT_PATH = os.path.join(os.path.dirname(__file__), "engine_ids.json")


async def main():
    ids = []
    async with AsyncSessionLocal() as session:
        for i in range(N):
            engine = Engine(
                id=uuid.uuid4(),
                serial_number=f"LOADTEST-{i:04d}-{uuid.uuid4().hex[:6]}",
                status="operational",
            )
            session.add(engine)
            ids.append(str(engine.id))
        await session.commit()

    with open(OUT_PATH, "w") as f:
        json.dump(ids, f)
    print(f"Seeded {len(ids)} engines -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
