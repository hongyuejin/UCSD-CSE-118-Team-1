# UCSD-CSE-118-Team-1
Raspberry Pi Use GUide
1) How to install requirements on RPi with virtual env

```bash
python3 -m venv venv
source venv/bin/activate
make install
```

2) How to run the server (no need to open the addr, just keep the server running)

```bash
make run
# or: python3 sensor_server.py
```

3) What the server receives

- POST /end with Content-Type: application/json
- Body: JSON containing `heart_rates`, `imu`, `duration`, and optional `heart_rate_hz` / `imu_hz`.
- Example short payload:

```json
{
  "heart_rates": [{ "t": 500, "bpm": 94 }, { "t": 1000, "bpm": 95 }],
  "rotation_vectors":[{"x":0.119086,"y":-0.099887,"z":0.124266,"w":0.979999},{"x":0.119223,"y":-0.100368,"z":0.124222,"w":0.979939}],
  "imu": [{ "t": 160, "ax": 1.8, "ay": 0.1, "az": 9.3, "gx": 0.01, "gy": 0.0, "gz": 0.0 }],
  "duration": 2,
  "heart_rate_hz": 2,
  "imu_hz": 20
}
```

4) Where files are stored & how to view

- Raw JSON files: `data/raw_data/session_<timestamp>.json`
- Processed CSVs: `data/processed_data/session_<timestamp>_imu.csv` and `..._heart_rate.csv`

To check the received data, directly go to the data folder. 

## SQLite schema

Processed session metadata is stored in `data/sessions.db` in the `sessions` table with the following columns:

```
id INTEGER PRIMARY KEY
created_at INTEGER        -- unix timestamp
raw_filename TEXT         -- raw JSON filename in data/raw_data
imu_csv TEXT              -- processed IMU CSV filename in data/processed_data
heart_csv TEXT            -- processed heart-rate CSV filename in data/processed_data
duration REAL             -- seconds
imu_hz_measured REAL      -- measured IMU samples / duration
imu_hz_sampling_rate_defined REAL -- IMU sampling rate reported by device
heart_rate_hz_measured REAL -- measured heart-rate samples / duration
heart_rate_hz_sampling_rate REAL -- heart-rate sampling rate reported by device
heart_mean REAL
heart_max INTEGER
```



