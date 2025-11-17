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



