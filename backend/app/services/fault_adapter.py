import numpy as np
from scipy.stats import skew, kurtosis

# The 32 channels in exact order
CHANNELS = [
    "IMU_GyrX", "IMU_GyrY", "IMU_GyrZ",
    "IMU_AccX", "IMU_AccY", "IMU_AccZ",
    "ATT_Roll", "ATT_Pitch", "ATT_Yaw",
    "ATT_ErrRP", "ATT_ErrYaw",
    "XKF1_Roll", "XKF1_Pitch", "XKF1_Yaw",
    "BARO_Alt", "BARO_Press", "BARO_Temp", "BARO_CRt",
    "GPS_NSats", "GPS_HDop", "GPS_Spd", "GPS_Alt",
    "MAG_MagX", "MAG_MagY", "MAG_MagZ",
    "BAT_Volt", "BAT_Curr",
    "VIBE_VibeX", "VIBE_VibeY", "VIBE_VibeZ",
    "MAV_rxp", "MAV_txp"
]

# Channels the piston adapter below does NOT drive from telemetry — it writes a
# fixed constant into them on every reading (attitude, EKF, GPS, magnetometer,
# MAVLink radio stats). A real UAV feed would vary these; a piston engine has
# no such sensors. Kept in sync with piston_to_uav_telemetry (a test asserts
# these are exactly the constant columns).
PLACEHOLDER_CHANNELS = (
    "ATT_Roll", "ATT_Pitch", "ATT_Yaw", "ATT_ErrRP", "ATT_ErrYaw",
    "XKF1_Roll", "XKF1_Pitch", "XKF1_Yaw",
    "GPS_NSats", "GPS_HDop", "GPS_Spd", "GPS_Alt",
    "MAG_MagX", "MAG_MagY", "MAG_MagZ",
    "MAV_rxp", "MAV_txp",
)


def input_coverage() -> float:
    """Share of the model's 32 input channels driven by measured telemetry
    (the rest are fixed placeholders). Structural for this adapter: it does
    not depend on the values in any particular reading."""
    return (len(CHANNELS) - len(PLACEHOLDER_CHANNELS)) / len(CHANNELS)


def piston_to_uav_telemetry(data: dict, prev_vibe: dict = None) -> np.ndarray:
    """
    Maps incoming piston telemetry to the 32-channel UAV schema.
    """
    out = np.zeros(32, dtype=np.float64)
    
    # 1. IMU Accel -> map from vibration (add gravity to Z)
    out[3] = data.get("vibration_x", 0.0)
    out[4] = data.get("vibration_y", 0.0)
    out[5] = data.get("vibration_z", 0.0) - 9.81
    
    # 2. IMU Gyro -> derive from rate of change of vibration (simple proxy)
    if prev_vibe is not None:
        out[0] = data.get("vibration_x", 0.0) - prev_vibe.get("x", 0.0)
        out[1] = data.get("vibration_y", 0.0) - prev_vibe.get("y", 0.0)
        out[2] = data.get("vibration_z", 0.0) - prev_vibe.get("z", 0.0)
        
    # 3. Baro proxies
    out[16] = data.get("cht", 30.0)         # BARO_Temp proxy
    out[15] = data.get("oil_pressure", 94000.0)  # BARO_Press proxy (scaled up to Pa)
    out[14] = data.get("egt", 0.0)          # BARO_Alt proxy
    out[17] = data.get("oil_temp", 0.0) - 90.0 # BARO_CRt proxy
    
    # 4. Battery proxies
    out[25] = data.get("rpm", 0.0) / 100.0  # BAT_Volt proxy
    out[26] = data.get("fuel_flow", 0.0)    # BAT_Curr proxy
    
    # 5. VIBE channels (raw)
    out[27] = data.get("vibration_x", 0.0)
    out[28] = data.get("vibration_y", 0.0)
    out[29] = data.get("vibration_z", 0.0)
    
    # Fill remaining with nominal defaults to keep features stable
    # ATT
    out[6], out[7], out[8] = 0.0, 0.0, 0.0
    out[9], out[10] = 0.0, 0.0
    # XKF1
    out[11], out[12], out[13] = 0.0, 0.0, 0.0
    # GPS
    out[18] = 12.0 # NSats
    out[19] = 1.0  # HDop
    out[20] = 10.0 # Spd
    out[21] = 50.0 # Alt
    # MAG
    out[22], out[23], out[24] = 100.0, -100.0, 50.0
    # MAV
    out[30] = 50.0 # rxp
    out[31] = 50.0 # txp
    
    return out

def extract_window_features(window_array: np.ndarray) -> np.ndarray:
    """
    Extracts the 465 features from an (80, 32) window array.
    """
    features = []
    
    # 1. Channel-wise statistics (32 * 14 = 448 features)
    for i in range(32):
        col = window_array[:, i]
        col_diff = np.diff(col) if len(col) > 1 else np.zeros(1)
        
        # Base stats
        c_mean = np.mean(col)
        c_std = np.std(col)
        c_min = np.min(col)
        c_max = np.max(col)
        c_p2p = c_max - c_min
        
        # Skew/kurt (handle flatlines safely)
        c_skew = float(skew(col)) if c_std > 1e-6 else 0.0
        c_kurt = float(kurtosis(col)) if c_std > 1e-6 else 0.0
        
        # Rate stats
        c_rate_mean = np.mean(col_diff)
        c_rate_std = np.std(col_diff)
        c_rate_max = np.max(np.abs(col_diff))
        
        # Spectral bands (FFT power)
        fft_vals = np.abs(np.fft.rfft(col - c_mean))
        n_bands = len(fft_vals)
        b0 = float(np.sum(fft_vals[0:max(1, n_bands//4)])) if n_bands >= 1 else 0.0
        b1 = float(np.sum(fft_vals[n_bands//4:max(2, n_bands//2)])) if n_bands >= 2 else 0.0
        b2 = float(np.sum(fft_vals[n_bands//2:max(3, 3*n_bands//4)])) if n_bands >= 3 else 0.0
        b3 = float(np.sum(fft_vals[3*n_bands//4:])) if n_bands >= 4 else 0.0
        
        features.extend([
            float(c_mean), float(c_std), float(c_min), float(c_max), float(c_p2p),
            float(c_skew), float(c_kurt),
            float(c_rate_mean), float(c_rate_std), float(c_rate_max),
            b0, b1, b2, b3
        ])
        
    # 2. Residual features (17 features)
    # resid_ATT_Roll_XKF1_Roll
    r_roll = window_array[:, 6] - window_array[:, 11]
    features.extend([float(np.mean(np.abs(r_roll))), float(np.max(np.abs(r_roll)))])
    
    # resid_ATT_Pitch_XKF1_Pitch
    r_pitch = window_array[:, 7] - window_array[:, 12]
    features.extend([float(np.mean(np.abs(r_pitch))), float(np.max(np.abs(r_pitch)))])
    
    # resid_ATT_Yaw_XKF1_Yaw
    r_yaw = window_array[:, 8] - window_array[:, 13]
    features.extend([float(np.mean(np.abs(r_yaw))), float(np.max(np.abs(r_yaw)))])
    
    # acc_norm
    acc_norm = np.sqrt(window_array[:, 3]**2 + window_array[:, 4]**2 + window_array[:, 5]**2)
    acc_dev = np.abs(acc_norm - 9.81)
    features.extend([float(np.mean(acc_dev)), float(np.std(acc_dev)), float(np.max(acc_dev))])
    
    # gyr_norm
    gyr_norm = np.sqrt(window_array[:, 0]**2 + window_array[:, 1]**2 + window_array[:, 2]**2)
    features.extend([float(np.mean(gyr_norm)), float(np.max(gyr_norm))])
    
    # mag_norm
    mag_norm = np.sqrt(window_array[:, 22]**2 + window_array[:, 23]**2 + window_array[:, 24]**2)
    features.extend([float(np.mean(mag_norm)), float(np.std(mag_norm))])
    
    # vibe_norm
    vibe_norm = np.sqrt(window_array[:, 27]**2 + window_array[:, 28]**2 + window_array[:, 29]**2)
    features.extend([float(np.mean(vibe_norm)), float(np.max(vibe_norm))])
    
    # mav_rxp_drop
    mav_rxp = window_array[:, 30]
    rxp_drop = np.maximum(0, 50.0 - mav_rxp) # assume 50 is nominal
    features.extend([float(np.mean(rxp_drop)), float(np.std(mav_rxp))])
    
    return np.array(features, dtype=np.float64)
