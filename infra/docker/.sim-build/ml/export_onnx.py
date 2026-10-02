"""
Phase 7 — Edge Packaging: ONNX export.

Converts the trained Fault (2-stage LightGBM) and RUL (XGBoost) models to
ONNX so `edge/inference/` can run them with just `onnxruntime` — no
scikit-learn, lightgbm, or xgboost wheels needed on the edge device.

Bearing and Aux models stay cloud-side (per the phase plan) and are NOT
exported here.

The RUL pipeline's *preprocessing* (StandardScaler condition scaling,
KMeans regime assignment, per-regime StandardScaler sensor scaling) is
NOT converted to an ONNX subgraph — sklearn-onnx cannot express "look up
one of N scalers by a runtime-computed cluster id" as a static graph
without contortions, and it's cheap, well-understood linear algebra
either way. Instead its learned parameters (means/scales/centroids) are
dumped to plain JSON and re-applied with a few lines of numpy in
`edge/inference/rul_runner.py` — smaller, more portable, and just as
exact as calling the original scikit-learn objects, since a
StandardScaler transform and a nearest-centroid lookup are both just
arithmetic on the fitted parameters, not learned black boxes.

Run from the repo root: `python ml/export_onnx.py`
"""
import json
import os

import joblib
import onnx
import onnxmltools
import xgboost as xgb
from onnxmltools.convert.common.data_types import FloatTensorType

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__) + "/..")
_FAULT_DIR = os.path.join(_REPO_ROOT, "ml", "training", "fault_model")
_RUL_DIR = os.path.join(_REPO_ROOT, "ml", "training", "rul_model", "CMaps", "saved_models")
_OUT_DIR = os.path.join(_REPO_ROOT, "ml", "models")


def export_fault_models():
    os.makedirs(_OUT_DIR, exist_ok=True)

    with open(os.path.join(_FAULT_DIR, "feature_names.json")) as f:
        feature_names = json.load(f)
    n_features = len(feature_names)

    for stage, filename, out_name in [
        (1, "stage1_binary_lgb.pkl", "fault_stage1.onnx"),
        (2, "stage2_multiclass_lgb.pkl", "fault_stage2.onnx"),
    ]:
        model = joblib.load(os.path.join(_FAULT_DIR, filename))
        assert model.n_features_in_ == n_features, (
            f"stage{stage}: model expects {model.n_features_in_} features, "
            f"feature_names.json has {n_features}"
        )
        onnx_model = onnxmltools.convert_lightgbm(
            model,
            initial_types=[("input", FloatTensorType([None, n_features]))],
            target_opset=15,
        )
        out_path = os.path.join(_OUT_DIR, out_name)
        onnx.save_model(onnx_model, out_path)
        print(f"Wrote {out_path} ({n_features} input features, "
              f"{len(getattr(model, 'classes_', []))} classes)")

    # feature_names.json travels with the ONNX files so the edge runner
    # can rebuild the same 465-wide feature vector in the same order.
    with open(os.path.join(_OUT_DIR, "fault_feature_names.json"), "w") as f:
        json.dump(feature_names, f)


def export_rul_model():
    os.makedirs(_OUT_DIR, exist_ok=True)

    with open(os.path.join(_RUL_DIR, "inference_config.json")) as f:
        config = json.load(f)

    booster = xgb.Booster()
    booster.load_model(os.path.join(_RUL_DIR, "xgb_rul_model.json"))
    n_features = booster.num_features()
    trained_feature_names = booster.feature_names  # save before stripping, for the JSON sidecar

    # onnxmltools' XGBoost converter only understands positional "f<N>"
    # feature names, not our trained booster's named columns (e.g.
    # "s_11_last5_mean") — rename to the generic form for conversion only;
    # order (not name) is what the ONNX graph actually keys on, and that
    # order is preserved and written out separately below.
    booster.feature_names = [f"f{i}" for i in range(n_features)]

    onnx_model = onnxmltools.convert_xgboost(
        booster,
        initial_types=[("input", FloatTensorType([None, n_features]))],
        target_opset=15,
    )
    out_path = os.path.join(_OUT_DIR, "rul_xgb.onnx")
    onnx.save_model(onnx_model, out_path)
    print(f"Wrote {out_path} ({n_features} input features)")

    # ── Preprocessing parameters, as plain JSON (see module docstring) ──
    condition_scaler = joblib.load(os.path.join(_RUL_DIR, "condition_scaler.joblib"))
    regime_kmeans = joblib.load(os.path.join(_RUL_DIR, "regime_kmeans.joblib"))
    regime_scalers = joblib.load(os.path.join(_RUL_DIR, "regime_scalers.joblib"))

    preprocessing = {
        "window_len": config["window_len"],
        "rul_cap": config["rul_cap"],
        "conformal_q": config["conformal_q"],
        "setting_cols": config["setting_cols"],
        "keep_sensors": config["keep_sensors"],
        "condition_scaler": {
            "mean": condition_scaler.mean_.tolist(),
            "scale": condition_scaler.scale_.tolist(),
        },
        "regime_kmeans": {
            "cluster_centers": regime_kmeans.cluster_centers_.tolist(),
        },
        "regime_scalers": {
            str(regime_id): {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
            for regime_id, scaler in regime_scalers.items()
        },
        "trained_feature_names": trained_feature_names,  # the ORIGINAL names (booster.feature_names is now the generic f0..fN)
    }
    out_path = os.path.join(_OUT_DIR, "rul_preprocessing.json")
    with open(out_path, "w") as f:
        json.dump(preprocessing, f)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    export_fault_models()
    export_rul_model()
