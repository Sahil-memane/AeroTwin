UAV Sensor Fault Detection System
Technical Documentation
# Table of Contents
1. Overview
2. Input Telemetry Schema
3. Output Fault Classes
4. Dataset & Ground Truth
5. Train/Test Split Design
6. Model Approach Comparison (ML vs DL)
7. Final Model Performance (Confusion Matrix Analysis)
8. Deployed Artifact Package
9. System Integration Guide (Real-Time Deployment)
10. Failsafe Action Mapping
# 1. Overview
This system performs real-time multi-class sensor fault detection for UAVs (drones) using onboard flight-controller telemetry. It classifies each 4-second window of flight data into one of 7 states — nominal flight or one of 6 sensor failure modes — and recommends an automated failsafe response.
The model ingests 32 telemetry channels sampled at 20 Hz over a 4-second sliding window (80 timesteps x 32 channels), evaluated every 1 second (20-step stride) once the buffer is full.
# 2. Input Telemetry Schema

# 3. Output Fault Classes & Database Schema
The model returns an integer class ID (0-6), a human-readable label, and a 7-element probability vector.

This is stored in the `fault_predictions` database table using the following schema:
- `ts`: (DateTime) Timestamp of the prediction
- `engine_id`: (UUID) Engine identifier
- `model_version_id`: (UUID) ML Model version identifier
- `class_id`: (Integer) Integer class ID from 0 to 6
- `fault_class`: (String) Human readable label ('No failure', 'RC', 'GPS', 'Aileron', 'Elevator', 'Rudder', 'Engine failure')
- `confidence`: (Float) The maximum probability value (confidence of the predicted class)
- `probabilities`: (JSON) The full 7-element probability vector array
# 4. Dataset & Ground Truth
70 flight sessions (10 per class x 7 classes) were processed into 27,312 sliding windows (4 s window, 1 s stride, 20 Hz), with row-level labeling based on active fault-injection status.

# 5. Train/Test Split Design
Method: StratifiedGroupKFold
Grouping variable: Flight Session ID — prevents any leakage of the same flight into both train and test
Stratification variable: Flight primary fault category — keeps class balance consistent across folds


The held-out test set spans 15 completely unseen flight sessions, so reported metrics reflect true generalization rather than in-flight interpolation.
# 6. Model Approach Comparison (ML vs DL)
Two candidate architectures were trained and evaluated on the identical 5,710 held-out test windows:
Two-Stage LightGBM — a gradient-boosted tree pipeline where Stage 1 performs binary Normal-vs-Fault detection, and Stage 2 (run only on windows flagged as faulty) performs 6-way fault isolation. Both stages consume a 465-dimension engineered feature vector per window (statistical moments, spectral band energies, EKF residuals, sensor norms).
Two-Stage PyTorch CNN-BiLSTM — a deep-learning pipeline using the same two-stage detect-then-isolate structure, but operating on raw/normalized time-series windows through convolutional and bidirectional LSTM layers instead of hand-engineered features.

## Head-to-Head Results

## Why LightGBM Was Selected
1. Accuracy and generalization: LightGBM outperformed the CNN-BiLSTM by over 20 points of accuracy and 33 points of macro-F1 on completely unseen flight sessions, indicating it generalizes far better to new flights rather than memorizing session-specific patterns.
2. Class-imbalance robustness: The much larger macro-F1 gap (vs. weighted-F1 gap) shows the DL model struggled disproportionately on minority fault classes (RC, GPS, Compass), while LightGBM's engineered features and class_weight='balanced' training kept minority-class performance high.
3. Training and iteration speed: At roughly 50x faster training, LightGBM allows rapid retraining as new flight data or fault modes are added, without requiring GPU infrastructure.
4. Interpretability: Tree-based feature importances (spectral energy, EKF residuals, sensor-norm features) are directly traceable to physical sensor behavior, which matters for a safety-critical failsafe system that may need certification or post-incident review.
5. Deployment footprint: Gradient-boosted trees are lightweight to serialize and run inference on resource-constrained companion computers (Raspberry Pi, Jetson Orin Nano) without a deep-learning runtime or GPU.

Conclusion: The Two-Stage LightGBM pipeline was selected as the production model based on superior accuracy, minority-class robustness, training efficiency, and edge-deployment suitability.
# 7. Final Model Performance (Confusion Matrix Analysis)
Evaluated on all 5,710 held-out test windows from unseen flight sessions:
                     Predicted Labels
True Labels        0      1      2      3      4      5      6   | Total
-----------------------------------------------------------------------
0 (No Failure)   3030     58      0      4      7     94      1   |  3194
1 (RC Failure)     12    191      0      0      0     26      0   |   229
2 (GPS Failure)     0      0    157      0      0      0      0   |   157
3 (Accel Failure)  10      0      0    631      1      0      0   |   642
4 (Gyro Failure)    5      0      0     84    739      0      0   |   828
5 (Compass Fail)    7      4      0      0      0    305      0   |   316
6 (Baro Failure)    2      0      0      0      0      0    342   |   344
-----------------------------------------------------------------------
Total Predicted  3066    253    157    719    747    425    343   |  5710
## Class-by-Class Breakdown

## Overall Summary Metrics

# 8. Deployed Artifact Package
Production deployment ships as a self-contained model directory (saved_models/best_model/) containing:

This package is self-contained and dependency-light enough for real-time inference on an onboard companion computer.
# 9. System Integration Guide (Real-Time Deployment)
## Step 1 — Telemetry Stream Buffering
On the onboard companion computer (Raspberry Pi 4/5, Jetson Orin Nano, or x86 board) receiving MAVLink telemetry from the flight controller (Pixhawk / ArduPilot / PX4), maintain a rolling buffer of the 32 channels at 20 Hz:
import collections
import numpy as np
 
BUFFER_LEN = 80        # 4 seconds @ 20 Hz
NUM_CHANNELS = 32
 
telemetry_buffer = collections.deque(maxlen=BUFFER_LEN)
 
def on_mavlink_telemetry_received(telemetry_sample_32ch):
    """
    Called every 50ms (20 Hz).
    telemetry_sample_32ch: list of 32 floats, ordered to match the
    channel schema in Section 2.
    """
    telemetry_buffer.append(telemetry_sample_32ch)
 
    # Once the buffer is full, evaluate a new window every 1 second (20 steps)
    if len(telemetry_buffer) == BUFFER_LEN and (current_tick % 20 == 0):
        window = np.array(telemetry_buffer)   # shape: (80, 32)
        evaluate_fault_status(window)
## Step 2 — Run Inference
Feed each completed (80, 32) window into the loaded model package to obtain a class ID, fault label, and confidence distribution:
def evaluate_fault_status(window):
    # window shape: (80, 32)
    class_id, fault_name, prob_dict = run_fault_inference(window)
    confidence = prob_dict[fault_name]
 
    if class_id != 0 and confidence > 0.70:
        trigger_failsafe_handler(class_id, fault_name, confidence)
    else:
        print(f"[Nominal] Flight healthy (Confidence: {prob_dict['No Failure']*100:.1f}%)")
A confidence threshold (0.70 in this example) is used to avoid triggering failsafes on borderline or noisy predictions — tune this per platform based on acceptable false-alarm vs. missed-detection tradeoffs.
## Step 3 — Actionable Failsafe Handler
Route the detected fault class to the appropriate autopilot command:
def trigger_failsafe_handler(fault_id, fault_name, confidence):
    print(f"[FAULT ALERT] Detected {fault_name} with {confidence*100:.1f}% confidence!")
 
    if fault_id == 1:   # RC Failure
        set_flight_mode("RTL")
 
    elif fault_id == 2: # GPS Failure
        switch_ekf_source("OPTICAL_FLOW")
        set_flight_mode("ALT_HOLD")
 
    elif fault_id == 3: # Accelerometer Failure
        switch_primary_imu(instance=2)
 
    elif fault_id == 4: # Gyro Failure
        switch_primary_gyro(instance=2)
        set_flight_mode("LAND")
 
    elif fault_id == 5: # Compass Failure
        disable_compass_fusion()
 
    elif fault_id == 6: # Barometer Failure
        set_altitude_source("GPS_ALT")
## Step 4 — Validate Before Flight
Confirm the companion computer's channel ordering exactly matches the 32-channel schema in Section 2 — mismatched ordering will silently corrupt predictions.
Run the pipeline against logged flight data (.bin/.log replay) before live deployment to confirm the confidence threshold and failsafe triggers behave as expected.
Log every triggered fault event (class, confidence, timestamp) alongside raw telemetry for post-flight review and future retraining.
## Step 5 — Operational Monitoring
Track false-positive rate on nominal flights in the field; adjust the confidence threshold if false RTL/LAND triggers occur.
Periodically retrain as new flight sessions are logged, especially for classes with lower precision (RC Failure, Compass Failure) to reduce confusion with No Failure.

# 10. Failsafe Action Mapping (Quick Reference)
| Channel | Category | Unit | Nominal Range | Failure Signature |
| --- | --- | --- | --- | --- |
| IMU_GyrX | Angular Rate | rad/s | -0.5 to +0.5 | Drift, bias injection, saturation (Gyro Failure) |
| IMU_GyrY | Angular Rate | rad/s | -0.5 to +0.5 | Drift, bias injection, saturation (Gyro Failure) |
| IMU_GyrZ | Angular Rate | rad/s | -0.5 to +0.5 | Uncommanded yaw offset (Gyro Failure) |
| IMU_AccX | Acceleration | m/s² | -2.0 to +2.0 | High-frequency noise/bias (Accel Failure) |
| IMU_AccY | Acceleration | m/s² | -2.0 to +2.0 | High-frequency noise/bias (Accel Failure) |
| IMU_AccZ | Acceleration | m/s² | -11.5 to -8.0 (≈ -9.81) | Deviation from gravity at rest (Accel Failure) |
| ATT_Roll | Attitude | deg | -30° to +30° | Kinematic response to motion |
| ATT_Pitch | Attitude | deg | -30° to +30° | Kinematic response to motion |
| ATT_Yaw | Heading | deg | 0° to 360° | Compass direction of nose |
| ATT_ErrRP | Control Error | deg | 0° to 3° | Diverges when attitude can't track target |
| ATT_ErrYaw | Control Error | deg | 0° to 5° | Heading error divergence |
| XKF1_Roll | EKF Estimate | deg | -30° to +30° | Diverges from ATT_Roll during sensor failure |
| XKF1_Pitch | EKF Estimate | deg | -30° to +30° | Diverges from ATT_Pitch during sensor failure |
| XKF1_Yaw | EKF Estimate | deg | 0° to 360° | Diverges from ATT_Yaw during compass/gyro failure |
| BARO_Alt | Barometric Alt | m | 0.0 to 100.0 | Jumps, freezes, drift (Baro Failure) |
| BARO_Press | Static Pressure | Pa | 93,000-95,000 | Sudden drops/spikes (Baro Failure) |
| BARO_Temp | Sensor Temp | °C | 30.0-33.0 | Ambient compartment temperature |
| BARO_CRt | Climb Rate | m/s | -5.0 to +5.0 | Contradicts real vertical velocity (Baro Failure) |
| GPS_NSats | Satellites | count | 10-14 | Drops below 4/0 during outage/spoofing |
| GPS_HDop | Horiz. Dilution | ratio | 0.6-1.2 | Surges above 2.5-5.0 during degradation |
| GPS_Spd | Ground Speed | m/s | 0.0-18.0 | Freezes/jumps during spoofing |
| GPS_Alt | GPS Altitude | m | 0.0-120.0 | Disagreement with barometer |
| MAG_MagX | Magnetic Field X | mGauss | -300 to +300 | Interference/bias shift (Compass Failure) |
| MAG_MagY | Magnetic Field Y | mGauss | -300 to +300 | Interference/bias shift (Compass Failure) |
| MAG_MagZ | Magnetic Field Z | mGauss | -450 to +100 | Field distortion (Compass Failure) |
| BAT_Volt | Battery Voltage | V | 11.1-12.65 | Nominal discharge curve |
| BAT_Curr | Current Draw | A | 2.0-45.0 | Power consumption |
| VIBE_VibeX | Airframe Vibe X | m/s² | < 0.05 | Structural vibration |
| VIBE_VibeY | Airframe Vibe Y | m/s² | < 0.05 | Structural vibration |
| VIBE_VibeZ | Airframe Vibe Z | m/s² | < 0.08 | Rotor/motor harmonics |
| MAV_rxp | MAVLink RX Packets | count | > 20/sec | Freezes/drops to 0 during RC loss |
| MAV_txp | MAVLink TX Packets | count | > 20/sec | Telemetry transmitter counter |

| ID | Label | System Meaning | Recommended Failsafe |
| --- | --- | --- | --- |
| 0 | No Failure | Nominal operation, within envelope | Continue autonomous mission |
| 1 | RC Failure | Manual RC/GCS link lost | Trigger RTL or auto-loiter |
| 2 | GPS Failure | GNSS fix degraded, lost, or spoofed | Fall back to optical-flow/EKF dead-reckoning + Altitude Hold |
| 3 | Accelerometer Failure | Linear acceleration corrupted | Switch to redundant IMU, reduce aggressive maneuvers |
| 4 | Gyro Failure | Angular rate sensor drifted/saturated/dead | Switch gyro instance, level wings, emergency land |
| 5 | Compass Failure | Magnetometer corrupted by EMI | Disable compass fusion in EKF, use GPS course-over-ground |
| 6 | Barometer Failure | Static port blocked / transducer fault | Switch altitude reference to GPS Alt / rangefinder |

| Class ID | Class | Window Count | Share | Status |
| --- | --- | --- | --- | --- |
| 0 | No Failure | 15,104 | 55.3% | Nominal + pre-injection phases |
| 1 | RC Failure | 1,123 | 4.1% | Active fault injection |
| 2 | GPS Failure | 900 | 3.3% | Active fault injection |
| 3 | Accelerometer Failure | 3,086 | 11.3% | Active fault injection |
| 4 | Gyro Failure | 2,883 | 10.6% | Active fault injection |
| 5 | Compass Failure | 2,289 | 8.4% | Active fault injection |
| 6 | Barometer Failure | 1,927 | 7.1% | Active fault injection |
| Total |  | 27,312 | 100.0% | Clean ground truth |

| Class ID | Class | Train Windows (55 sessions) | Test Windows (15 sessions) | Test Share |
| --- | --- | --- | --- | --- |
| 0 | No Failure | 11,910 | 3,194 | 21.1% |
| 1 | RC Failure | 894 | 229 | 20.4% |
| 2 | GPS Failure | 743 | 157 | 17.4% |
| 3 | Accelerometer Failure | 2,444 | 642 | 20.8% |
| 4 | Gyro Failure | 2,055 | 828 | 28.7% |
| 5 | Compass Failure | 1,973 | 316 | 13.8% |
| 6 | Barometer Failure | 1,583 | 344 | 17.9% |
| Total |  | 21,602 | 5,710 | 20.9% |

| Metric | Two-Stage LightGBM (ML) | Two-Stage CNN-BiLSTM (DL) | Delta (ML Advantage) |
| --- | --- | --- | --- |
| Held-Out Test Accuracy | 94.48% | 70.98% | +23.50% |
| Macro-Average F1 | 92.07% | 58.67% | +33.40% |
| Weighted-Average F1 | 94.67% | 72.36% | +22.31% |
| Training Time | ~4.5 seconds (vectorized) | ~4 minutes (CPU) | ~50x faster |

| Class | Correct / Total | Precision | Recall | Notes |
| --- | --- | --- | --- | --- |
| GPS Failure (2) | 157/157 | 100.0% | 100.0% | Zero confusion with any other class |
| Barometer Failure (6) | 342/344 | 99.7% | 99.4% | Near-perfect isolation |
| Gyro Failure (4) | 739/828 | 98.9% | 89.3% | Confuses with Accel Failure (shared IMU vibrational coupling) |
| No Failure (0) | 3030/3194 | 98.8% | 94.9% | Low false-alarm rate on nominal flight |
| Accelerometer Failure (3) | 631/642 | 87.8% | 98.3% | Some overlap with Gyro Failure |
| RC Failure (1) | 191/229 | 75.5% | 83.4% | Some confusion with No Failure / Compass |
| Compass Failure (5) | 305/316 | 71.8% | 96.5% | High recall, moderate precision |

| Metric | Value |
| --- | --- |
| Overall Accuracy | 94.48% |
| Macro-Average F1 | 92.07% |
| Weighted-Average F1 | 94.67% |

| Component | Purpose |
| --- | --- |
| Stage 1 binary detector weights | Normal vs. Fault-Active classification (class_weight='balanced') |
| Stage 2 multiclass isolator weights | 6-way fault classification, trained only on active-fault windows; outputs [P(RC), P(GPS), P(Accel), P(Gyro), P(Compass), P(Baro)] |
| Feature name manifest | Ordered list of all 465 engineered features (statistical moments, spectral band energies, EKF residuals, sensor norms) extracted per window |
| Model metadata | Channel order, architecture type, and verified test metrics, for validation at load time |

| Detected Fault | Immediate Autopilot Action |
| --- | --- |
| RC Failure | Return-to-Launch (RTL) or auto-loiter |
| GPS Failure | Optical-flow/EKF dead-reckoning, Altitude Hold |
| Accelerometer Failure | Switch to redundant IMU instance |
| Gyro Failure | Switch gyro instance, level wings, initiate LAND |
| Compass Failure | Disable compass fusion in EKF |
| Barometer Failure | Switch altitude reference to GPS Alt |
