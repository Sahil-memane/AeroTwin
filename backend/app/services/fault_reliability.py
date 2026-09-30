"""
Is a fault prediction trustworthy enough to drive Health Fusion and alerts?

The fault model's input is 32 channels, but for a piston engine only some are
driven by measured data (fault_adapter.PLACEHOLDER_CHANNELS are constants).
A result computed mostly from placeholders is out-of-distribution for the
model — it can look confident ("Compass Failure, 99.9%") while reflecting
missing sensors, not engine state. Such results are kept and shown as
ADVISORY but excluded from Health Fusion.

`input_coverage` is NULL on rows written before this existed; those are
treated as reliable (the legacy behavior) — they age out of Health Fusion via
the freshness window anyway.
"""
from typing import Optional

from app.core.config import settings


def is_reliable(input_coverage: Optional[float]) -> bool:
    return input_coverage is None or input_coverage >= settings.FAULT_MIN_INPUT_COVERAGE
