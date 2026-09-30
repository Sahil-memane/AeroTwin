import math
import numpy as np
from typing import Dict, Any, Optional

class AuxAdapter:
    def __init__(self):
        # engine_id -> accumulated wear
        self._wear_state: Dict[str, float] = {}

    @staticmethod
    def wear_increment(rpm: float) -> float:
        """Wear (minutes) added by one reading at `rpm` — the single
        definition used by telemetry_to_raw_features and by the What-If
        scenario engine, so the two can never drift."""
        return (rpm / 3000.0) * (0.5 / 60.0) if rpm > 0 else 0

    def get_wear(self, engine_id: str) -> Optional[float]:
        """Accumulated wear for `engine_id`, or None if no state exists."""
        return self._wear_state.get(engine_id)

    def set_wear(self, engine_id: str, value: float) -> None:
        self._wear_state[engine_id] = value

    def reset_engine(self, engine_id: str) -> None:
        self._wear_state.pop(engine_id, None)

    def telemetry_to_raw_features(self, engine_id: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps piston telemetry to the 6 raw features expected by the AI4I model.
        """
        rpm = telemetry.get("rpm", 0.0)
        cht = telemetry.get("cht", 30.0)
        
        # Accumulate wear simply as time elapsed (assuming 0.5s intervals, so +0.5/60 min per call)
        # In a real scenario, this would come from the database or RUL state
        current_wear = self._wear_state.get(engine_id, 0.0)
        # Increase wear proportionally to RPM to simulate load
        wear_increment = self.wear_increment(rpm)
        current_wear += wear_increment
        self._wear_state[engine_id] = current_wear
        
        # Ensure wear is non-negative and somewhat realistic
        if current_wear > 300: # Reset mock after 300 minutes to avoid permanent failure state in demo
            current_wear = 0.0
            self._wear_state[engine_id] = 0.0

        return {
            'Type': 'M',
            'Air temperature [K]': 298.15,
            'Process temperature [K]': 298.15 + (cht / 10.0), # Mock process temp based on CHT
            'Rotational speed [rpm]': rpm,
            'Torque [Nm]': (rpm / 100.0) + telemetry.get("vibration_x", 0.0), # Mock torque based on RPM and vibration
            'Tool wear [min]': current_wear
        }

    def raw_to_engineered_features(self, raw: Dict[str, Any]) -> np.ndarray:
        """
        Converts the 6 raw features into the 11 engineered features expected by the model:
        ['Type_Code', 'Air_Temp_C', 'Process_Temp_C', 'Temp_Diff', 'RPM', 'Torque', 
         'Power_kW', 'Tool_Wear_min', 'Overstrain', 'Heat_Stress', 'Torque_per_RPM']
        """
        type_map = {'L': 0, 'M': 1, 'H': 2}
        type_code = type_map.get(raw.get('Type', 'M'), 1)
        
        air_temp_k = raw.get('Air temperature [K]', 298.15)
        proc_temp_k = raw.get('Process temperature [K]', 308.15)
        rpm = raw.get('Rotational speed [rpm]', 0.0)
        torque = raw.get('Torque [Nm]', 0.0)
        tool_wear = raw.get('Tool wear [min]', 0.0)
        
        air_temp_c = air_temp_k - 273.15
        proc_temp_c = proc_temp_k - 273.15
        temp_diff = proc_temp_c - air_temp_c
        
        power_kw = (2 * math.pi * rpm * torque) / 60000.0
        overstrain = tool_wear * torque
        heat_stress = temp_diff * rpm
        torque_per_rpm = torque / rpm if rpm > 0 else 0.0
        
        features = [
            float(type_code),
            float(air_temp_c),
            float(proc_temp_c),
            float(temp_diff),
            float(rpm),
            float(torque),
            float(power_kw),
            float(tool_wear),
            float(overstrain),
            float(heat_stress),
            float(torque_per_rpm)
        ]
        
        return np.array(features, dtype=np.float64).reshape(1, -1)

# Singleton instance
aux_adapter = AuxAdapter()
