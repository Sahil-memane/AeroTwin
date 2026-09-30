"""
What-If parameter-perturbation scenario engine.

Takes an engine's most recent REAL telemetry window (plain dicts — this
module never touches the database), applies the operator's parameter
change to the last K readings on an in-memory copy, and runs the existing
RUL / Fault / Bearing / Aux services plus Health Fusion over both the
untouched (baseline) window and the perturbed (scenario) window, so the
two are compared like-for-like through identical code paths.

Isolation guarantees:
  * inputs are deep-copied; the caller's rows are never mutated;
  * every model service is driven with a unique, namespaced pseudo
    engine_id and that state is freed in `finally` — live sliding windows,
    the fault state machine and aux wear state of the real engine are
    never written;
  * no alert is created or broadcast (only `describe_alert`, a pure
    function sharing production severity/message rules, is used).

Scenario type is PARAMETER PERTURBATION, not a full physical engine
simulation: parameters are shifted independently; no cross-parameter
physical coupling is invented.
"""
from __future__ import annotations

import copy
import hashlib
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.services.alert_engine import describe_alert
from app.services.aux_adapter import aux_adapter
from app.services.aux_service import aux_service
from app.services.bearing_service import bearing_service
from app.services.fault_service import fault_service
from app.services.fault_state import fault_state_machine
from app.services.health_fusion import HealthScoreResult, compute_health_score, excluded_sources
from app.services.physics_ingestion import compute_consistency
from app.services.rul_adapter import piston_to_cmapss
from app.services.rul_service import rul_service
from app.services.validation import SENSOR_BOUNDS

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "telemetry_limits.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _WI_CONFIG = yaml.safe_load(_f)["what_if"]

# API parameter name -> telemetry field name (oil_temperature is the
# operator-facing name; the stored/model field is oil_temp).
PARAMETER_FIELDS: Dict[str, str] = {k: v["telemetry_field"] for k, v in _WI_CONFIG["parameters"].items()}
PERTURBATION_WINDOW: int = int(_WI_CONFIG["perturbation_window"])

# Numerical tolerance under which two model outputs count as "unchanged".
CHANGE_TOLERANCE = 1e-9

# Which scenario parameters feed which model, verified against the model
# adapters by tests/test_what_if_scenario.py (not merely asserted here).
FEATURE_MAPPING: Dict[str, Dict[str, Any]] = {
    "rul": {
        "direct": ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"],
        "note": "Via piston_to_cmapss; all six also shift the server-computed physics deviation_score (RUL's top feature).",
    },
    "fault": {
        "direct": ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"],
        "note": "Via piston_to_uav_telemetry proxy channels over an 80-reading window.",
    },
    "bearing": {
        "direct": ["rpm"],
        "note": "Model input is vibration magnitude + RPM; RPM only sets the synthetic defect frequency. Vibration amplitude is not a scenario input.",
    },
    "auxiliary": {
        "direct": ["rpm", "cht"],
        "note": "AI4I features derive from RPM and CHT (plus vibration_x); RPM also drives accumulated wear state.",
    },
}

_SOURCES = ("rul", "fault", "bearing", "aux")


# ── Validation ───────────────────────────────────────────────────────

def parameter_config() -> Dict[str, Dict[str, Any]]:
    """Slider metadata for the frontend: bounds come from `sensor_bounds`."""
    out = {}
    for name, cfg in _WI_CONFIG["parameters"].items():
        lo, hi = SENSOR_BOUNDS[cfg["telemetry_field"]]
        out[name] = {"min": lo, "max": hi, "step": cfg["step"], "unit": cfg["unit"]}
    return out


def validate_parameters(params: Any) -> Tuple[Dict[str, float], List[str]]:
    """Returns (clean {param: float}, errors). Omitted parameters mean
    "unchanged"; an explicit null/NaN/Infinity/non-number/out-of-range
    value is an error, as is an empty or unknown-key request."""
    errors: List[str] = []
    clean: Dict[str, float] = {}
    if not isinstance(params, dict) or not params:
        return clean, ["`parameters` must be a non-empty object"]
    cfg = parameter_config()
    for key, value in params.items():
        if key not in cfg:
            errors.append(f"unknown parameter '{key}' (allowed: {', '.join(cfg)})")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"'{key}' must be a number (got {value!r})")
            continue
        if not math.isfinite(value):
            errors.append(f"'{key}' must be finite (got {value!r})")
            continue
        lo, hi = cfg[key]["min"], cfg[key]["max"]
        if not (lo <= value <= hi):
            errors.append(f"'{key}'={value} outside configured range [{lo}, {hi}] {cfg[key]['unit']}")
            continue
        clean[key] = float(value)
    return clean, errors


# ── Window construction ──────────────────────────────────────────────

def required_window_size() -> int:
    """Readings to load: enough that each of the K perturbed readings has
    its own full fault window (fault window - 1 + K)."""
    return fault_service.window_len - 1 + PERTURBATION_WINDOW


def apply_perturbation(
    rows: List[Dict[str, Any]], scenario: Dict[str, float], k: int
) -> Tuple[List[Dict[str, Any]], int]:
    """
    In-memory scenario copy of `rows` (oldest -> newest). For each
    parameter, delta = scenario value - the LAST reading's value; that
    delta is added to each of the last K readings (so the final reading
    equals the scenario value exactly, while the window's real variance is
    preserved, and delta == 0 is an exact no-op). A shifted value that
    would leave the configured sensor bounds is clamped; the count of
    clamped values is returned.
    """
    out = copy.deepcopy(rows)
    if not out:
        return out, 0
    last = out[-1]
    clamped = 0
    for param, target in scenario.items():
        field = PARAMETER_FIELDS[param]
        delta = target - last[field]
        if delta == 0:
            continue
        lo, hi = SENSOR_BOUNDS[field]
        for row in out[-k:]:
            shifted = row[field] + delta
            bounded = min(hi, max(lo, shifted))
            if bounded != shifted:
                clamped += 1
            row[field] = bounded
    return out, clamped


def _prepare(row: Dict[str, Any]) -> Dict[str, Any]:
    """Row -> model input dict, mirroring live ingestion: None vibration
    fields are dropped (so service defaults apply rather than crashing on
    None), vibration magnitude is derived, and deviation_score is computed
    server-side from the physics model exactly as ingestion.py does."""
    data = {k: v for k, v in row.items() if v is not None}
    vx, vy, vz = row.get("vibration_x"), row.get("vibration_y"), row.get("vibration_z")
    if vx is not None and vy is not None and vz is not None:
        data["vibration_magnitude"] = round(math.sqrt(vx**2 + vy**2 + vz**2), 3)
    data["deviation_score"] = compute_consistency(data)[0]
    return data


def _bearing_seed(engine_id: str, baseline_ts: str) -> int:
    """Seed from window identity (engine + newest reading), NOT from
    scenario values — baseline and scenario share identical synthetic
    noise, so any bearing difference comes from the input change alone."""
    digest = hashlib.sha256(f"{engine_id}|{baseline_ts}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


# ── Pipeline ─────────────────────────────────────────────────────────

class _Fusion:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _run_pipeline(
    readings: List[Dict[str, Any]], tag: str, wear_seed: float, bearing_seed: int
) -> Dict[str, Any]:
    """Drive the four real model services + Health Fusion over `readings`
    (oldest -> newest, already prepared) under isolated namespaced state."""
    key = f"whatif::{uuid.uuid4().hex}::{tag}"
    n = len(readings)
    result: Dict[str, Any] = {}
    try:
        rul_res = fault_res = None
        fault_inferences = 0
        rul_error = fault_error = None
        for data in readings:
            try:
                r = rul_service.push_reading(key, piston_to_cmapss(data))
                rul_res = r if r is not None else rul_res
            except Exception as e:  # model-level failure must not sink the whole scenario
                rul_error = str(e)
            try:
                f = fault_service.push_reading(key, data)
                if f is not None:
                    fault_res = f
                    fault_inferences += 1
            except Exception as e:
                fault_error = str(e)
        # RUL only counts if the LAST push produced a prediction.
        rul_ready = n >= rul_service.window_len

        # Aux: stateless inference on the last reading, but wear state is
        # cumulative — replay the earlier readings' wear accumulation from
        # the same seed for baseline and scenario.
        aux_adapter.set_wear(key, wear_seed)
        aux_res = aux_error = None
        try:
            for data in readings[:-1]:
                aux_adapter.telemetry_to_raw_features(key, data)
            aux_res = aux_service.push_reading(key, readings[-1]) if readings else None
        except Exception as e:
            aux_error = str(e)

        bearing_res = bearing_error = None
        try:
            bearing_res = bearing_service.push_reading(key, readings[-1], seed=bearing_seed) if readings else None
        except Exception as e:
            bearing_error = str(e)

        # ── per-model status ──
        if rul_error:
            rul_block = {"status": "ERROR", "message": rul_error}
        elif not rul_ready or rul_res is None:
            rul_block = {"status": "INSUFFICIENT_DATA", "message": f"{n}/{rul_service.window_len} readings available"}
        elif rul_res.get("status") == "MODEL_ERROR":
            rul_block = {"status": "MODEL_UNAVAILABLE", "message": "RUL model unavailable (mock placeholder suppressed)"}
        else:
            rul_block = {**rul_res, "status": "COMPLETED", "model_status": rul_res.get("status")}

        if fault_error:
            fault_block = {"status": "ERROR", "message": fault_error}
        elif n < fault_service.window_len or fault_res is None:
            fault_block = {"status": "INSUFFICIENT_DATA", "message": f"{n}/{fault_service.window_len} readings available"}
        elif getattr(fault_service, "_stage1_model", None) is None:
            fault_block = {"status": "MODEL_UNAVAILABLE", "message": "Fault model failed to load"}
        else:
            fault_block = {**fault_res, "status": "COMPLETED", "inferences": fault_inferences}

        if aux_error:
            aux_block = {"status": "ERROR", "message": aux_error}
        elif aux_res is None:
            aux_block = {"status": "INSUFFICIENT_DATA", "message": "no readings"}
        elif getattr(aux_service, "_binary_model", None) is None:
            aux_block = {"status": "MODEL_UNAVAILABLE", "message": "Auxiliary model failed to load"}
        else:
            aux_block = {**aux_res, "status": "COMPLETED"}

        if bearing_error:
            bearing_block = {"status": "ERROR", "message": bearing_error}
        elif bearing_res is None:
            bearing_block = {"status": "INSUFFICIENT_DATA", "message": "no readings"}
        elif getattr(bearing_service, "_model", None) is None:
            bearing_block = {"status": "MODEL_UNAVAILABLE", "message": "Bearing CNN failed to load"}
        else:
            bearing_block = {**bearing_res, "status": "COMPLETED"}
            bearing_block["inputs"] = {
                "vibration_magnitude": readings[-1].get("vibration_magnitude"),
                "rpm": readings[-1].get("rpm"),
            }

        # ── Health Fusion over whatever real, usable outputs exist ──
        fusion_rul = _Fusion(**rul_res) if rul_block["status"] == "COMPLETED" else None
        fusion_fault = (
            _Fusion(
                fault_class=fault_res["fault_class"], confidence=fault_res["confidence"], state=fault_res.get("state"),
                input_coverage=fault_res.get("input_coverage"),
            )
            if fault_block["status"] == "COMPLETED" else None
        )
        fusion_bearing = (
            _Fusion(
                class_label=bearing_res["class_label"],
                fault_location=bearing_res["fault_location"],
                severity_inches=bearing_res["severity_inches"],
            )
            if bearing_block["status"] == "COMPLETED" else None
        )
        fusion_aux = (
            _Fusion(
                failure_probability_pct=aux_res["failure_probability_pct"],
                primary_failure_cause=aux_res.get("primary_failure_cause"),
                detected_failure_types=aux_res.get("detected_failure_types") or [],
            )
            if aux_block["status"] == "COMPLETED" else None
        )
        health = compute_health_score(fusion_rul, fusion_fault, fusion_bearing, fusion_aux)
        used = {
            "rul": fusion_rul is not None, "fault": fusion_fault is not None,
            "bearing": fusion_bearing is not None, "aux": fusion_aux is not None,
        }
        result = {
            "models": {"rul": rul_block, "fault": fault_block, "bearing": bearing_block, "auxiliary": aux_block},
            "health": health,
            "sources_used": used,
            # Produced output but set aside by Health Fusion (fault input coverage too low):
            # not "missing" — the score is still a real assessment of the other sources.
            "excluded": excluded_sources(fusion_fault),
        }
        return result
    finally:
        rul_service.reset_engine(key)
        fault_service.reset_engine(key)
        fault_state_machine.reset_engine(key)
        aux_adapter.reset_engine(key)


def _fusion_view(health: HealthScoreResult, sources_used: Dict[str, bool], excluded: List[str]) -> Dict[str, Any]:
    """Health Fusion output with ALL four sources present (0 penalty when
    inactive) so consumers can render a consistent table."""
    by_source = {f["source"]: f for f in health.contributing_factors}
    sources = {}
    for s in _SOURCES:
        f = by_source.get(s)
        forced = bool(f and f.get("forced_zero"))
        sources[s] = {
            "penalty": None if forced else (f["penalty"] if f else 0.0),
            "active": f is not None,
            "forced_zero": forced,
            "available": sources_used[s],
            "excluded": s in excluded,
        }
    return {
        "score": health.combined_score,
        "contributing_factors": health.contributing_factors,
        "sources": sources,
        "primary_concern": health.primary_concern,
        "forced_zero": health.forced_zero,
        # A source that produced no usable output contributes no penalty,
        # which is NOT the same as "healthy" — surfaced so it isn't misread.
        "missing_sources": [s for s in _SOURCES if not sources_used[s]],
        # Sources that reported but are advisory-only (see fault_reliability).
        "excluded_sources": list(excluded),
    }


def _num_changed(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return a != b
    return abs(a - b) > CHANGE_TOLERANCE


def _compare_models(base: Dict[str, Any], scen: Dict[str, Any], deltas: Dict[str, float]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    b, s = base["rul"], scen["rul"]
    out["rul"] = {
        "baseline": b, "scenario": s,
        "changed": b["status"] != s["status"] or _num_changed(b.get("rul_cycles"), s.get("rul_cycles")),
        "delta_cycles": (s["rul_cycles"] - b["rul_cycles"]) if "rul_cycles" in b and "rul_cycles" in s else None,
    }

    b, s = base["fault"], scen["fault"]
    out["fault"] = {
        "baseline": b, "scenario": s,
        "changed": (b["status"], b.get("fault_class"), b.get("state")) != (s["status"], s.get("fault_class"), s.get("state"))
        or _num_changed(b.get("confidence"), s.get("confidence")),
        "delta_confidence": (s["confidence"] - b["confidence"]) if "confidence" in b and "confidence" in s else None,
    }

    b, s = base["bearing"], scen["bearing"]
    input_changed = "rpm" in deltas and deltas["rpm"] != 0
    output_changed = (b["status"], b.get("class_label"), b.get("severity_inches")) != (
        s["status"], s.get("class_label"), s.get("severity_inches"))
    conf_changed = _num_changed(b.get("confidence"), s.get("confidence"))
    if not input_changed:
        note = "Bearing prediction unchanged: the scenario did not modify the bearing model's inputs (vibration magnitude, RPM)."
    elif not (output_changed or conf_changed):
        note = "RPM changed the synthetic defect frequency, but the bearing model output is unchanged."
    else:
        note = "Bearing output changed; the only scenario input reaching the bearing model is RPM (synthetic defect frequency). Vibration amplitude was not modified."
    out["bearing"] = {"baseline": b, "scenario": s, "input_changed": input_changed,
                      "changed": output_changed or conf_changed, "note": note}

    b, s = base["auxiliary"], scen["auxiliary"]
    input_changed = any(deltas.get(p, 0) != 0 for p in ("rpm", "cht"))
    out["auxiliary"] = {
        "baseline": b, "scenario": s, "input_changed": input_changed,
        "changed": b["status"] != s["status"] or _num_changed(b.get("failure_probability_pct"), s.get("failure_probability_pct")),
        "delta_failure_probability_pct": (
            s["failure_probability_pct"] - b["failure_probability_pct"]
            if "failure_probability_pct" in b and "failure_probability_pct" in s else None),
        "note": None if input_changed else
        "Auxiliary prediction unchanged: the scenario did not modify the auxiliary model's inputs (RPM, CHT).",
    }
    return out


def _alerts_view(base: HealthScoreResult, scen: HealthScoreResult) -> Dict[str, Any]:
    rank = {"warning": 1, "critical": 2}
    b, s = describe_alert(base), describe_alert(scen)
    if b is None and s is None:
        change = "NONE"
    elif b is None:
        change = "NEW"
    elif s is None:
        change = "CLEARED"
    elif rank[s["severity"]] > rank[b["severity"]]:
        change = "ESCALATED"
    elif rank[s["severity"]] < rank[b["severity"]]:
        change = "DEESCALATED"
    else:
        change = "UNCHANGED"
    tag = lambda a: None if a is None else {**a, "simulation": True}  # noqa: E731
    return {"simulation": True, "baseline": tag(b), "scenario": tag(s), "change": change}


def _physics_view(base_last: Dict[str, Any], scen_last: Dict[str, Any]) -> Dict[str, Any]:
    b_dev, b_res = compute_consistency(base_last)
    s_dev, s_res = compute_consistency(scen_last)
    api_name = {v["telemetry_field"]: k for k, v in _WI_CONFIG["parameters"].items()}
    b_by = {r.parameter: r for r in b_res}
    params = {}
    for r in s_res:  # RPM is a physics INPUT, not a checked channel -> not listed
        base = b_by[r.parameter]
        params[api_name[r.parameter]] = {
            "expected": r.expected, "measured": r.measured, "residual": r.residual,
            "status": r.status, "method": r.method,
            "baseline_residual": base.residual, "baseline_status": base.status,
        }
    return {"deviation_score": {"baseline": b_dev, "scenario": s_dev}, "parameters": params}


def run_scenario(
    engine_id: str,
    rows: List[Dict[str, Any]],
    scenario_params: Dict[str, float],
) -> Dict[str, Any]:
    """
    `rows`: oldest -> newest telemetry dicts (ts as datetime + the six
    channels + optional vibration_x/y/z). `scenario_params`: already
    validated {api_name: value}. Synchronous and CPU-bound — call via
    asyncio.to_thread.
    """
    k = PERTURBATION_WINDOW
    n = len(rows)
    fault_req, rul_req = fault_service.window_len, rul_service.window_len
    window = {
        "total_readings": n,
        "perturbed_readings": min(k, n),
        "required_readings": {"fault": fault_req, "rul": rul_req},
        "loaded_target": required_window_size(),
        "data_sufficiency": (
            "INSUFFICIENT_DATA" if n < rul_req else
            "PARTIAL" if n < fault_req else
            "SUFFICIENT"
        ),
    }
    meta = {
        "mode": "WHAT_IF",
        "scenario_type": "PARAMETER_PERTURBATION",
        "perturbation_count": min(k, n),
        "perturbation_window_config": k,
        "perturbation_method": "delta_applied_to_last_k_readings",
    }
    if n == 0:
        return {**meta, "engine_id": engine_id, "simulation_status": "INSUFFICIENT_DATA",
                "baseline": None, "scenario": None, "delta": None, "window": window,
                "model_results": None, "health_fusion": None, "physics_consistency": None,
                "alerts": None, "baseline_timestamp": None,
                "message": "No telemetry recorded for this engine — current engine data unavailable."}

    last = rows[-1]
    baseline_ts = last["ts"].isoformat() if isinstance(last["ts"], datetime) else str(last["ts"])
    full_scenario = {p: (scenario_params[p] if p in scenario_params else last[f]) for p, f in PARAMETER_FIELDS.items()}
    baseline_vals = {p: last[f] for p, f in PARAMETER_FIELDS.items()}
    deltas = {p: full_scenario[p] - baseline_vals[p] for p in PARAMETER_FIELDS}

    scen_rows, clamped = apply_perturbation(rows, {p: full_scenario[p] for p in scenario_params}, k)
    base_prepared = [_prepare(r) for r in rows]
    scen_prepared = [_prepare(r) for r in scen_rows]

    # Aux wear seed: live wear already includes this window's own
    # increments, so seed = live - window increments; replaying the
    # unperturbed window then reproduces live wear at the last reading.
    live_wear = aux_adapter.get_wear(engine_id)
    if live_wear is None:
        wear_seed, wear_source = 0.0, "unavailable_seeded_zero"
    else:
        used = sum(aux_adapter.wear_increment(r["rpm"]) for r in base_prepared)
        wear_seed, wear_source = max(0.0, live_wear - used), "live_state"
    seed = _bearing_seed(engine_id, baseline_ts)

    base = _run_pipeline(base_prepared, "baseline", wear_seed, seed)
    scen = _run_pipeline(scen_prepared, "scenario", wear_seed, seed)

    models = _compare_models(base["models"], scen["models"], deltas)
    statuses = [scen["models"][m]["status"] for m in scen["models"]]
    if "ERROR" in statuses:
        overall = "ERROR"
    elif "MODEL_UNAVAILABLE" in statuses:
        overall = "MODEL_UNAVAILABLE"
    elif "INSUFFICIENT_DATA" in statuses:
        overall = "INSUFFICIENT_DATA"
    else:
        overall = "COMPLETED"

    base_fusion = _fusion_view(base["health"], base["sources_used"], base["excluded"])
    scen_fusion = _fusion_view(scen["health"], scen["sources_used"], scen["excluded"])
    scen_last = {**scen_prepared[-1]}
    base_last = {**base_prepared[-1]}

    return {
        **meta,
        "engine_id": engine_id,
        "simulation_status": overall,
        "baseline_timestamp": baseline_ts,
        "baseline": baseline_vals,
        "scenario": full_scenario,
        "delta": deltas,
        "window": {**window, "clamped_values": clamped,
                   "aux_wear_seed": round(wear_seed, 6), "aux_wear_source": wear_source},
        "feature_mapping": FEATURE_MAPPING,
        "model_results": models,
        "health_fusion": {
            "baseline": base_fusion, "scenario": scen_fusion,
            "score_delta": round(scen_fusion["score"] - base_fusion["score"], 2),
            **scen_fusion,
        },
        "physics_consistency": _physics_view(base_last, scen_last),
        "alerts": _alerts_view(base["health"], scen["health"]),
        "assumptions": [
            "telemetry_readings does not persist throttle/altitude_m; RUL uses adapter defaults and physics estimates throttle from RPM (identical for baseline and scenario).",
            "Vibration magnitude is derived from stored vibration_x/y/z.",
        ],
    }
