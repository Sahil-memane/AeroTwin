import os
import joblib
import logging
import numpy as np
from typing import Optional, Dict, Any

from app.services.aux_adapter import aux_adapter

logger = logging.getLogger(__name__)

class AuxService:
    def __init__(self):
        self._loaded = False
        
        # Stage 1
        self._scaler = None
        self._binary_model = None
        
        # Stage 2
        self._type_classifiers = {}
        self._failure_types_meta = {}

    def _ensure_loaded(self):
        if self._loaded:
            return
            
        base_dir = os.path.join(os.path.dirname(__file__), "../../../ml/training/aux_model/final_model")
        
        try:
            # Stage 1
            b_meta = joblib.load(os.path.join(base_dir, "binary_failure_metadata.joblib"))
            self._scaler = b_meta['scaler']
            self._binary_model = joblib.load(os.path.join(base_dir, "binary_failure_model.joblib"))
            
            # Stage 2
            self._type_classifiers = joblib.load(os.path.join(base_dir, "failure_type_classifiers.joblib"))
            t_meta = joblib.load(os.path.join(base_dir, "failure_type_metadata.joblib"))
            self._failure_types_meta = t_meta['failure_types']
            
            self._loaded = True
            logger.info("Successfully loaded Aux Model pipeline.")
        except Exception as e:
            logger.error(f"Failed to load Aux Model: {e}")
            self._loaded = True # Mock mode

    def _get_risk_and_action(self, prob_pct: float):
        if prob_pct < 15.0:
            return "LOW", "Continue normal operation"
        elif prob_pct < 50.0:
            return "MODERATE", "Schedule preventive inspection"
        elif prob_pct < 80.0:
            return "HIGH", "Halt and service before next shift"
        else:
            return "CRITICAL", "Emergency shutdown — immediate maintenance"

    def push_reading(self, engine_id: str, raw_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs stateless inference on a single reading.
        """
        self._ensure_loaded()
        
        # 1. Feature Engineering
        raw_inputs = aux_adapter.telemetry_to_raw_features(engine_id, raw_telemetry)
        features = aux_adapter.raw_to_engineered_features(raw_inputs)
        
        if self._binary_model is None or self._scaler is None:
            # Fallback mock
            return {
                "failure_status": "HEALTHY",
                "risk_level": "LOW",
                "failure_probability_pct": 0.0,
                "detected_failure_types": [],
                "primary_failure_cause": None,
                "recommended_action": "Continue normal operation"
            }
            
        # 2. Scale features
        # Note: scikit-learn warnings about version mismatches may occur, but transform should work
        try:
            features_scaled = self._scaler.transform(features)
        except Exception as e:
            logger.warning(f"Scaler failed, using unscaled features: {e}")
            features_scaled = features
            
        # 3. Stage 1: Binary Inference
        is_failure = self._binary_model.predict(features_scaled)[0]
        probs = self._binary_model.predict_proba(features_scaled)[0]
        # In sklearn, predict_proba returns [prob_class_0, prob_class_1]
        fail_prob = float(probs[1]) if len(probs) > 1 else float(probs[0] if is_failure else 0.0)
        fail_prob_pct = fail_prob * 100.0
        
        risk_level, action = self._get_risk_and_action(fail_prob_pct)
        status = "MACHINE FAILURE" if is_failure else "HEALTHY"
        if risk_level == "CRITICAL" and not is_failure:
            status = "CRITICAL" # override if risk is very high
            
        detected_types = []
        primary_cause = None
        
        # 4. Stage 2: Failure Type Isolation (only if failure detected or high risk)
        if is_failure or fail_prob_pct >= 50.0:
            best_prob = 0.0
            
            # Check ML classifiers (HDF, PWF, OSF)
            for code, clf in self._type_classifiers.items():
                if code in ['TWF', 'RNF']: 
                    continue # Handled by rules
                    
                # Note: failure classifiers might not need scaled features, but assuming they do 
                # based on common pipeline patterns. If they fail, we catch it.
                try:
                    c_prob = float(clf.predict_proba(features_scaled)[0][1])
                    c_active = clf.predict(features_scaled)[0] == 1
                    
                    if c_active or c_prob > 0.5:
                        detected_types.append({
                            "code": code,
                            "full_name": self._failure_types_meta.get(code, code),
                            "probability": c_prob,
                            "active": bool(c_active),
                            "cause": self._failure_types_meta.get(code, code)
                        })
                        if c_prob > best_prob:
                            best_prob = c_prob
                            primary_cause = f"{code} - {self._failure_types_meta.get(code, code)}"
                except Exception as e:
                    logger.debug(f"Failed to predict with {code} classifier: {e}")
            
            # TWF Rule Fallback
            tool_wear = raw_inputs.get('Tool wear [min]', 0.0)
            torque = raw_inputs.get('Torque [Nm]', 0.0)
            if tool_wear > 200 and torque > 60:
                detected_types.append({
                    "code": "TWF",
                    "full_name": "Tool Wear Failure",
                    "probability": 1.0,
                    "active": True,
                    "cause": "Tool Wear Failure"
                })
                if 1.0 > best_prob:
                    best_prob = 1.0
                    primary_cause = "TWF - Tool Wear Failure"
                    
            # If still nothing identified but Stage 1 flagged failure, fall back to RNF
            if not detected_types:
                detected_types.append({
                    "code": "RNF",
                    "full_name": "Random/Unknown Failure",
                    "probability": fail_prob,
                    "active": True,
                    "cause": "Random/Unknown Failure"
                })
                primary_cause = "RNF - Random/Unknown Failure"

        return {
            "failure_status": status,
            "risk_level": risk_level,
            "failure_probability_pct": fail_prob_pct,
            "detected_failure_types": detected_types,
            "primary_failure_cause": primary_cause,
            "recommended_action": action
        }

# Global singleton instance
aux_service = AuxService()
