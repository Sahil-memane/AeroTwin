# Model 2 -- Remaining Useful Life (RUL) Prediction (Turbofan Engine)

**Domain:** Aerospace / Gas Turbine Engine Prognostics

## ML Task
Regression -- predict how many operating cycles remain before a turbofan engine fails.

## Description
NASA C-MAPSS (Commercial Modular Aero-Propulsion System Simulation) run-to-failure dataset.
Engines start healthy at cycle 1 and degrade over time until failure.
Training data contains complete run-to-failure histories.
Test data is truncated -- model must predict remaining cycles using RUL_FD00X.txt as ground truth.

## 4 Sub-Datasets (FD001 - FD004)
| Dataset | Train Rows | Test Rows | Train Units | Test Units | Op. Conditions | Fault Modes |
|---------|-----------|----------|-------------|------------|----------------|-------------|
| FD001   | 20,631    | 13,096   | 100         | 100        | 1              | 1 (HPC Degradation) |
| FD002   | 53,759    | 33,991   | 260         | 259        | 6              | 1 (HPC Degradation) |
| FD003   | 24,720    | 16,596   | 100         | 100        | 1              | 2 (HPC + Fan) |
| FD004   | 61,249    | 41,214   | 249         | 248        | 6              | 2 (HPC + Fan) |

## Files Structure
```
CMaps/
  train_FD001.txt   -- FD001 full run-to-failure engine histories (20,631 rows x 26 cols)
  test_FD001.txt    -- FD001 truncated test histories (13,096 rows x 26 cols)
  RUL_FD001.txt     -- FD001 true RUL values (100 rows x 1 col)
  train_FD002.txt   -- FD002 full run-to-failure (53,759 rows x 26 cols)
  test_FD002.txt    -- FD002 truncated test (33,991 rows x 26 cols)
  RUL_FD002.txt     -- FD002 true RUL values (259 rows x 1 col)
  train_FD003.txt   -- FD003 full run-to-failure (24,720 rows x 26 cols)
  test_FD003.txt    -- FD003 truncated test (16,596 rows x 26 cols)
  RUL_FD003.txt     -- FD003 true RUL values (100 rows x 1 col)
  train_FD004.txt   -- FD004 full run-to-failure (61,249 rows x 26 cols)
  test_FD004.txt    -- FD004 truncated test (41,214 rows x 26 cols)
  RUL_FD004.txt     -- FD004 true RUL values (248 rows x 1 col)
  readme.txt        -- Original NASA documentation
  Damage Propagation Modeling.pdf -- Academic reference paper
CMAPSSData.zip      -- Original compressed dataset v1 (12.4 MB)
data_set_v2.zip     -- Extended C-MAPSS dataset v2 (15.8 GB compressed)
```

## Columns (26 total -- NO header row in .txt files, assign manually)
| Col # | Name          | Description                              | Range              |
|-------|---------------|------------------------------------------|--------------------|
| 1     | unit_number   | Engine unit identifier                   | 1 to N             |
| 2     | time_cycles   | Operating cycle (timestep)               | 1 to max_cycle     |
| 3     | setting_1     | Altitude (kft)                           | 0 to 41.99         |
| 4     | setting_2     | Mach Number                              | 0 to 0.84          |
| 5     | setting_3     | Throttle Resolver Angle (%)              | 60 to 100          |
| 6     | s_1           | Fan Inlet Total Temperature (degR)       | 445 - 549          |
| 7     | s_2           | LPC Outlet Total Temperature (degR)      | 537 - 645          |
| 8     | s_3           | HPC Outlet Total Temperature (degR)      | 1353 - 1616        |
| 9     | s_4           | LPT Outlet Total Temperature (degR)      | 1048 - 1441        |
| 10    | s_5           | Fan Inlet Pressure (psia)                | 2.1 - 14.6         |
| 11    | s_6           | Bypass-Duct Pressure (psia)              | 8.4 - 21.6         |
| 12    | s_7           | HPC Outlet Pressure (psia)               | 138 - 284          |
| 13    | s_8           | Physical Fan Speed (rpm)                 | 1973 - 2388        |
| 14    | s_9           | Physical Core Speed (rpm)                | 7892 - 9244        |
| 15    | s_10          | Engine Pressure Ratio (EPR)              | 0.999 - 1.47       |
| 16    | s_11          | HPC Outlet Static Pressure (psia)        | 46.9 - 97.3        |
| 17    | s_12          | Fuel Flow Ratio (pps/psi)                | 520 - 1167         |
| 18    | s_13          | Corrected Fan Speed (rpm)                | 1895 - 2388        |
| 19    | s_14          | Corrected Core Speed (rpm)               | 7382 - 9244        |
| 20    | s_15          | Bypass Ratio                             | 5.66 - 8.51        |
| 21    | s_16          | Burner Fuel-Air Ratio                    | 0.028 - 0.038      |
| 22    | s_17          | Bleed Enthalpy (lb/s)                    | 388 - 400          |
| 23    | s_18          | Required Fan Speed (rpm)                 | 1973 - 2388        |
| 24    | s_19          | Required Fan Conversion Speed            | 100                |
| 25    | s_20          | HP Turbine Cool Air Flow (lb/s)          | 6.5 - 14.2         |
| 26    | s_21          | LP Turbine Cool Air Flow (lb/s)          | 14 - 16            |

## RUL Statistics
| File           | Engines | RUL Min | RUL Max | RUL Mean |
|----------------|---------|---------|---------|----------|
| RUL_FD001.txt  | 100     | 7       | 143     | 75.6     |
| RUL_FD002.txt  | 259     | 5       | 303     | ~84      |
| RUL_FD003.txt  | 100     | 12      | 185     | ~91      |
| RUL_FD004.txt  | 248     | 5       | 303     | ~93      |
