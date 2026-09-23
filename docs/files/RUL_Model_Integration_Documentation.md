
# Model 2 — Turbofan RUL Prediction

Dataset Summary, Model Integration & Inference Pipeline Documentation


# 1. Purpose & Rationale

C-MAPSS provides run-to-failure engine sensor data with ground-truth Remaining Useful Life (RUL) labels, letting us build and validate the full RUL prediction pipeline — windowing, feature engineering, XGBoost regression, and confidence calibration — on a trusted, labeled benchmark before applying the same methodology to piston-engine data, which lacks this kind of labeled, full-lifecycle dataset.

In short: C-MAPSS proves the approach works end-to-end. The piston-engine adaptation is a later phase that reuses this validated pipeline rather than starting from scratch.

Rather than committing to a single algorithm upfront, multiple modeling approaches — XGBoost, a CNN-LSTM sequence model, and an XGBoost+CNN-LSTM ensemble — were trained and benchmarked on the same data and features, and the best-performing approach was selected for production (see Section 5).


# 2. Dataset Actually Used — C-MAPSS (Combined FD001–FD004)

Corrected, verified statistics for the dataset as merged and used in training (quotable summary):


| Metric | Value |
| --- | --- |
| Total raw columns per file | 26 (unit_number, time_cycles, setting_1–3, s_1–s_21) |
| Total engines (train) | 709 |
| Total engines (test) | 707 |
| Total engines (combined) | 1,416 |
| Total rows (train) | 160,359 |
| Total rows (test) | 104,897 |
| Total rows (combined) | 265,256 |
| Sensors kept for modeling (merged run) | 21 of 21 — none dropped (all sensors retained after merge) |
| Engineered features fed to XGBoost | 216 (24 raw columns × 9 window statistics each) |



All four C-MAPSS sub-datasets (FD001, FD002, FD003, FD004) were combined into a single training corpus so the model learns across varying operating-condition counts (1 vs 6) and fault-mode counts (1 vs 2) rather than being specialized to one regime.


# 3. Files Actually Needed for Inference


| File | Needed? | Purpose |
| --- | --- | --- |
| xgb_rul_model.json | YES | The trained XGBoost model that predicts RUL |
| condition_scaler.joblib | YES | Scales the engine operating-condition inputs |
| regime_kmeans.joblib | YES | Determines the engine's operating regime |
| regime_scalers.joblib | YES | Applies the correct sensor scaling for that regime |
| inference_config.json | YES | Stores configuration needed to reproduce the training/inference pipeline (window length, feature list, etc.) |



Directory layout:

RUL_MODEL/

├── xgb_rul_model.json

├── condition_scaler.joblib

├── regime_kmeans.joblib

├── regime_scalers.joblib

└── inference_config.json

These five files work together as one unit — none of them is usable in isolation.


# 4. How the Files Integrate — Real-Time Inference Flow

When a live engine streams sensor data, the saved artifacts are applied in this order:


Engine Sensors

↓

setting_1, setting_2, setting_3   +   s_1 … s_21

↓

condition_scaler.joblib  —  scales operating-condition inputs

↓

regime_kmeans.joblib  —  assigns the engine's current operating regime

↓

regime_scalers.joblib  —  applies the regime-specific sensor scaling

↓

Latest 30 cycles (rolling window)

↓

Feature extraction  —  mean, std, slope, last5_mean, etc.

↓

xgb_rul_model.json  —  trained XGBoost regressor

↓

Predicted RUL

↓

e.g. 47 cycles remaining


inference_config.json ties this together: it tells the inference code exactly how to reproduce the training-time pipeline at serve time — the rolling-window length (30 cycles), which raw columns feed feature extraction, the exact feature list/order expected by the model (216 engineered features), and any other reproducibility settings. Without it, the scalers, the regime model, and the XGBoost model can each load correctly but still be applied inconsistently with how they were trained.


# 5. Model Selection — Comparing Multiple Approaches

Before committing to XGBoost as the production model, multiple algorithms were trained and evaluated on the same merged C-MAPSS (FD001–FD004) corpus and the same engineered feature set, so that the comparison isolates the choice of model rather than differences in data or features. Three approaches were tested: a standalone XGBoost regressor, a standalone CNN-LSTM sequence model, and an ensemble combining XGBoost with the CNN-LSTM. Results are summarized below.


| Model / Approach | MAE (cycles) | RMSE (cycles) | NASA Score | 90% PI Coverage |
| --- | --- | --- | --- | --- |
| XGBoost (merged) — selected | 9.5462 | 13.4307 | 2260.79 | 90.66% |
| Ensemble (XGBoost + CNN-LSTM, merged) | 10.2105 | 14.3727 | 3021.49 | 91.37% |
| CNN-LSTM (merged) | 13.1500 | 19.0135 | 10926.07 | 90.66% |



XGBoost produced the lowest MAE, RMSE, and NASA score of the three approaches, and matched the CNN-LSTM on 90% prediction-interval coverage. The CNN-LSTM alone performed worst on every error metric, and the XGB+CNN-LSTM ensemble — while achieving marginally higher PI coverage — did not improve point-prediction accuracy enough to offset its added complexity and slower inference. XGBoost was therefore selected as the production model, and Sections 6–11 document its hyperparameter search, final performance, and integration in detail.


# 6. Model Training — Hyperparameter Search & Fit

Randomized/grid hyperparameter search completed in 23.6 minutes. Best mean cross-validation MAE: 10.523 cycles.

Best parameters found:


| Parameter | Value |
| --- | --- |
| max_depth | 6 |
| learning_rate | 0.02 |
| subsample | 1.0 |
| colsample_bytree | 0.7 |
| min_child_weight | 1 |
| reg_alpha | 0 |
| reg_lambda | 0.5 |



The final model was retrained on the full fit set using these best parameters. The tuned model outperformed the baseline and was selected as the final production model.


# 7. Final Tuned Model — Performance


| Metric | Value |
| --- | --- |
| MAE (Mean Absolute Error) | 9.5752 cycles |
| RMSE (Root Mean Squared Error) | 13.3598 cycles |
| R² | 0.8992 |
| NASA Score | 2161.2579 |
| Relative accuracy | 87.28% |
| Within ±5 cycles | 41.58% |
| Within ±10 cycles | 65.06% |
| Within ±15 cycles | 78.50% |
| Within ±20 cycles | 86.14% |
| Within ±25 cycles | 92.65% |
| 90% Prediction Interval coverage (target 90%) | 90.52% |
| Prediction Interval width | 45.64 cycles |



# 8. Top 15 Most Important Features


| Rank | Feature | Importance |
| --- | --- | --- |
| 1 | s_11_last5_mean | 0.274783 |
| 2 | s_4_last5_mean | 0.191516 |
| 3 | s_17_last5_mean | 0.168300 |
| 4 | s_3_last5_mean | 0.069038 |
| 5 | s_9_slope | 0.035087 |
| 6 | s_9_last5_mean | 0.026090 |
| 7 | s_11_slope | 0.024738 |
| 8 | s_14_slope | 0.023772 |
| 9 | s_4_slope | 0.012803 |
| 10 | s_14_last5_mean | 0.012166 |
| 11 | s_15_last5_mean | 0.008039 |
| 12 | s_15_slope | 0.007345 |
| 13 | s_2_last5_mean | 0.007150 |
| 14 | s_12_slope | 0.005388 |
| 15 | s_3_mean | 0.004967 |



The top four features (s_11_last5_mean, s_4_last5_mean, s_17_last5_mean, s_3_last5_mean) alone account for roughly 70% of total feature importance — the model relies heavily on the recent-window mean of a small set of sensors, with slope (trend) features providing secondary signal.


# 9. Performance by Original FD Subset


| FD Subset | N Engines | MAE | RMSE | NASA Score |
| --- | --- | --- | --- | --- |
| FD001 | 100 | 8.6709 | 12.2271 | 253.14 |
| FD002 | 259 | 9.7918 | 13.6156 | 804.91 |
| FD003 | 100 | 8.6897 | 11.8774 | 231.42 |
| FD004 | 248 | 10.0707 | 14.0731 | 871.79 |



FD001 and FD003 (single operating condition) achieve the lowest error and NASA score. FD002 and FD004 (six operating conditions) are harder, with FD004 — the combination of 6 operating conditions and 2 fault modes — showing the highest error, as expected for the most complex sub-dataset.


# 10. Saved Artifacts & Outputs


| Artifact Type | File(s) / Path |
| --- | --- |
| Model | xgb_rul_model.json |
| Preprocessing | condition_scaler.joblib, regime_kmeans.joblib, regime_scalers.joblib |
| Config | inference_config.json |
| Evaluation | xgb_final_evaluation.csv |
| By-FD breakdown | xgb_final_evaluation_by_fd.csv |
| Feature importance | xgb_feature_importance.csv |
| Per-engine predictions | xgb_per_engine_predictions.csv |



# 11. Final Summary

MAE: 9.58 cycles

RMSE: 13.36 cycles

R²: 0.8992

Relative accuracy: 87.3%

Within ±10 cycles: 65.1%

NASA score: 2161.3

90% prediction-interval coverage: 90.5% (target: 90%)
