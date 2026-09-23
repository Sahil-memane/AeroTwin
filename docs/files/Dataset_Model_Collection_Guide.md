**Dataset & Model Collection Guide**

*Digital Twin --- Engine Health Monitoring System \| Dataset sourcing & sorting reference for the 4 trained ML models*

1\. Purpose

This document is the working reference for dataset collection, verification, and sorting across the project. It answers two questions for every component of the architecture: (a) does this component need a labeled training dataset at all, and (b) if yes, which dataset covers it, where it comes from, and what\'s still missing.

> *Use this as the single source of truth when adding new datasets --- append rows rather than restarting the table, so provenance stays traceable for judges.*

2\. Architecture coverage at a glance

The system has 7 labeled components across its diagrams, but only 4 of them are trained ML models in the sense of requiring a labeled dataset. The table below maps all 7 so the scope of the dataset sheet is explicit and defensible.

| **\#** | **Component** | **Trained ML model?** | **Data status / what it needs** |
|----|----|----|----|
| 1 | **Digital twin core** | **No --- live synchronized state** | N/A for training. Uses real-time sensor stream + mission history (same inputs as row 1 of the dataset table). |
| 2 | **Physics model** | **No --- thermodynamic / performance equations** | GAP: needs engine performance maps, thermodynamic constants, manufacturer spec sheets for a piston engine (or a public proxy). Reference/config data, not a labeled ML dataset. |
| 3 | **Fault model** | **Yes** | Covered --- ALFA (UAV telemetry). |
| 4 | **RUL model** | **Yes** | Covered --- NASA turbofan (C-MAPSS). |
| 5 | **Bearing model** | **Yes** | Covered --- CWRU bearing data. |
| 6 | **Aux model** | **Yes** | Covered --- AI4I 2020 (milling) + engine failure dataset (source still unconfirmed --- see gap above). |
| 7 | **Simulation engine** | **Not really --- scenario replay / what-if tool** | GAP: needs mission / environmental profile data (altitude, temperature, throttle transients). Largely overlaps with the \'Mission & history\' input already planned for the twin core --- confirm it has enough scenario diversity (hot weather, high altitude, rapid throttle) since DRDO explicitly asked for this. |

> *Two open gaps remain outside the ML layer: the Physics model needs reference/spec data (not a training dataset), and the Simulation engine needs mission/environmental profile diversity. Neither blocks the 4 ML models below, but both should be tracked to their own owners.*

3\. Dataset sheet --- the 4 trained ML models

Full sourcing detail for every dataset feeding a trained model, sorted by which model it feeds.

| **Dataset** | **Source (with link)** | **Format** | **Key attributes / variables** | **Feeds model** |
|----|----|----|----|----|
| **UAV flight telemetry & sensor fault logs (ALFA)** | CMU AirLab --- theairlab.org/alfa-dataset
DOI 10.1184/R1/12707963 | ROS bag / CSV time-series | Flight state (attitude, GPS, IMU), actuator commands, fault injection timestamp, fault type label (engine failure + 7 control-surface fault types) | Fault model (7-class classifier) |
| **NASA turbofan engine degradation (C-MAPSS)** | NASA Prognostics Center of Excellence --- data.phmsociety.org/nasa
(Kaggle mirror: behrad3d/nasa-cmaps) | CSV, multivariate time series | 26 columns: unit ID, cycle number, 3 operational settings, 21 sensor measurements (temps, pressures, fan/core speeds) | RUL model (LSTM / XGBoost regression) |
| **Bearing fault diagnosis (CWRU)** | Case Western Reserve University Bearing Data Center ---
engineering.case.edu/bearingdatacenter/download-data-file | .mat vibration signal files (12 / 48 kHz) | Accelerometer vibration signal, fault location (inner race / outer race / rolling element), fault diameter (7-40 mils), motor load, RPM | Bearing / vibration model (FFT feature extraction + classifier) |
| **Milling machine predictive maintenance (AI4I 2020)** | Kaggle mirror --- kaggle.com/datasets/shivamb/machine-predictive-maintenance-classification | CSV, tabular | Air / process temperature, rotational speed, torque, tool wear (min), machine failure label (5 modes: TWF, HDF, PWF, OSF, RNF) + no-failure | Aux / transfer model (cross-domain pretraining) |
| **Engine failure dataset** | NOT CONFIRMED --- likely a generic Kaggle engine-health dataset. Re-verify and paste the exact link before submission. | Unconfirmed | Unconfirmed | Aux / transfer model (combines with milling data) |

4\. Open items before submission

4.1 Unconfirmed source (Aux model)

- Row 5, \"Engine failure dataset\", has no captured link --- track down the exact Kaggle/UCI page and paste the URL into the table above before this goes into the submission doc.

- Judges may ask for dataset provenance directly during evaluation; \"we don\'t remember where we got it\" is a preventable gap.

4.2 Domain gap & mitigation

- None of the 5 datasets are piston-engine-specific: turbofan ≠ piston, UAV telemetry ≠ engine internals, milling ≠ aero engine.

- Add a one-line mitigation note directly in the submission sheet, e.g.: \"Engine-agnostic architecture, validated on proxy datasets, designed for drop-in replacement with real piston / CAN-bus data at deployment.\"

4.3 Licensing

- All 5 datasets are public / research-use with no restrictive licensing that would block a hackathon demo.

- Double-check CWRU\'s terms specifically --- it requires direct registration/download from their portal rather than an open mirror, unlike the others.

4.4 Non-ML gaps to close separately

- Physics model: source engine performance maps, thermodynamic constants, or manufacturer spec sheets for a piston engine (or a public aero-engine thermodynamic reference as a proxy). File this as reference/config data, not inside the ML training table.

- Simulation engine: confirm the planned \"Mission & history\" data collection covers enough scenario diversity --- hot weather, high altitude, rapid throttle transients --- since DRDO explicitly asked for these conditions.

5\. Sorting checklist per model

Fault model

- Dataset: ALFA (UAV flight telemetry & fault logs)

- Status: sourced and linked

- Next: confirm ROS bag → CSV conversion pipeline for the 7-class fault labels

RUL model

- Dataset: NASA C-MAPSS turbofan degradation

- Status: sourced and linked

- Next: decide LSTM vs. XGBoost baseline and set aside a held-out test split

Bearing model

- Dataset: CWRU bearing vibration data

- Status: sourced and linked, but requires portal registration

- Next: complete CWRU registration early --- it\'s the one dataset not available via an open mirror

Aux / transfer model

- Datasets: AI4I 2020 (milling) confirmed; engine failure dataset unconfirmed

- Status: partially sourced

- Next: re-verify and link the second dataset before finalizing this row
