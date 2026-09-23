# AeroTwin Decisions Log

This document records the architectural and design decisions made during the project lifecycle.

| # | Decision | Resolution | Rationale |
|---|---|---|---|
| D1 | **Fault model taxonomy** | **Option B**: Keep ALFA's actual 7 classes and reframe the Fault model's scope as UAV-system fault detection. | Relabeling dataset to engine-specific faults requires unavailable domain expertise and data; it's safer and faster for a hackathon to keep the original labels. |
| D2 | **Schema gaps** | Add `aux_predictions (engine_id, model_version_id, ts, aux_score)` and add `model_version_id` FK to `bearing_health_readings`. | Necessary to correctly capture all prediction states and maintain relational integrity across model versions. |
| D3 | **License for public repo** | **MIT License** | Standard permissive open-source license, simplest default for a hackathon. |
