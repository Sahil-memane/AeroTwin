# Model 4 -- Auxiliary Predictive Maintenance (Milling Machine + Engine Failure)

**Domain:** Industrial Equipment / CNC Machine Tool & Engine Reliability

## ML Task
Binary and multi-label failure classification from tabular sensor readings.

## Description
Two complementary tabular datasets for industrial predictive maintenance:

### Sub-dataset A: AI4I 2020 (CNC Milling Machine -- UCI ML Repository)
Synthetic dataset reflecting real-world CNC milling machine telemetry.
Each row represents one machining operation with 5 possible failure modes.

### Sub-dataset B: Engine Failure Dataset
Engine health monitoring sensor logs with binary pass/fail failure indicator.
Useful for binary anomaly detection and failure threshold modeling.

## Files
| File                            | Dataset              | Rows   | Cols | Task                         |
|---------------------------------|----------------------|--------|------|------------------------------|
| ai4i2020.csv                    | AI4I 2020 Full       | 10,000 | 14   | Multi-label failure classify  |
| ai4i2020-selected-columns.csv   | AI4I 2020 Selected   | 10,000 | 7    | Binary failure prediction     |
| engine_failure_dataset.csv      | Engine Failure       | 1,222  | 16   | Binary failure classification |

## AI4I 2020 Features (ai4i2020.csv -- 14 columns)
| Column                    | Type   | Range          | Start Val | End Val | Meaning                        |
|---------------------------|--------|----------------|-----------|---------|--------------------------------|
| UDI                       | int    | 1 - 10000      | 1         | 10000   | Unique identifier              |
| Product ID                | str    | M/L/H + serial | M14860    | M24859  | Product quality variant        |
| Type                      | str    | L / M / H      | M         | M       | Quality grade                  |
| Air temperature [K]       | float  | 295.3 - 304.5  | 298.1     | 298.9   | Ambient temperature            |
| Process temperature [K]   | float  | 305.7 - 313.8  | 308.6     | 309.0   | Machining process temp         |
| Rotational speed [rpm]    | float  | 1168 - 2886    | 1551      | 1500    | Spindle rotational speed       |
| Torque [Nm]               | float  | 3.8 - 76.6     | 42.8      | 40.2    | Motor torque output            |
| Tool wear [min]           | float  | 0 - 253        | 0         | 5       | Accumulated tool usage time    |
| Machine failure           | int    | 0 / 1          | 0         | 0       | TARGET: Any failure occurred   |
| TWF                       | int    | 0 / 1          | 0         | 0       | Tool Wear Failure              |
| HDF                       | int    | 0 / 1          | 0         | 0       | Heat Dissipation Failure       |
| PWF                       | int    | 0 / 1          | 0         | 0       | Power Failure                  |
| OSF                       | int    | 0 / 1          | 0         | 0       | Overstrain Failure             |
| RNF                       | int    | 0 / 1          | 0         | 0       | Random Failure                 |

## AI4I 2020 Selected Columns (ai4i2020-selected-columns.csv -- 7 columns)
Reduced version for binary failure classification:
Type, Air temperature, Process temperature, Rotational speed, Torque, Tool wear, Machine failure

## Engine Failure Dataset (engine_failure_dataset.csv -- 1,222 rows x 16 cols)
Engine operational health monitoring sensor log.
Features include temperature, pressure, rotational speed, oil metrics,
vibration indicators, and a binary `failure` target column.

## Class Balance
- AI4I 2020: ~3.4% failure rate (339 failures out of 10,000 records)
- Engine Failure: Check `failure` column distribution after loading
