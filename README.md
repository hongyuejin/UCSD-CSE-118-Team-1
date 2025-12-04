# UCSD-CSE-118-Team-1 - Kendo Training Analysis Server

Raspberry Pi server for analyzing Kendo training sessions using dual-device IMU and heart rate data.

## Features

### Single Device Analysis (Wrist Watch)
- **Heart Rate**: Tracks average and maximum heart rate (BPM) to gauge exertion.
- **Movement Intensity**: Calculates average and maximum acceleration intensity (G).
- **Strike Detection**: Identifies sword strikes using peak detection on accelerometer data.
- **Calories**: Estimates theoretical energy cost (cal) based on wrist angular velocity.

### Dual Device Analysis (Wrist + Shinai Sensor)
When a Shinai sensor is paired, the system provides advanced form and impact metrics:
- **Straightness**: Analyzes strike trajectory variance to measure how straight the strike is (0.0 - 1.0).
- **Consistency**: Compares consecutive strikes to measure technique consistency (0.0 - 1.0).
- **True Impact**: Measures actual strike force (G) and impact details at the sword tip.

### Beginner-Friendly Interpretations
- **Effort**: Categorized as Low, Moderate, or High based on wrist movement intensity.
- **Control**: A composite score of Straightness and Consistency, categorized as "Needs Work", "Average", or "Good".
- **Heart**: Simple "Calm", "Moderate", or "Elevated" status based on average BPM.
- **Actionable Guidance**: Provides specific training advice based on the combination of Effort and Control scores.

### Web Interface
- **Dashboard**: Lists all sessions with "Wrist Movement" and "Control" badges for quick assessment.
- **Session Details**: Full breakdown of metrics, including experimental physics data and interpretive guidance.
- **Dual Sensor Analysis**: Page for manually selecting session pairs to run dual analysis (useful for debugging or manual matching).
- Access at `http://<raspberry-pi-ip>:5000/`

## Setup

### Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Requirements:
- Flask >= 2.0
- numpy (for dual analysis)

### Running the Server

```bash
python sensor_server.py
# Server will run on http://0.0.0.0:5000
```

Alternatively, you can use the Makefile:
```bash
make run
```

## API Endpoints

### POST /end
Receives session data from watch apps and performs analysis.

**Request Headers:**
- Content-Type: application/json

**Request Body (Wear App):**
```json
{
  "heart_rates": [{ "t": 500, "bpm": 94 }, { "t": 1000, "bpm": 95 }],
  "imu": [{ "t": 160, "ax": 1.8, "ay": 0.1, "az": 9.3, "gx": 0.01, "gy": 0.0, "gz": 0.0 }],
  "rotation_vectors": [{"x": 0.119, "y": -0.099, "z": 0.124, "w": 0.979}],
  "duration": 60,
  "heart_rate_hz": 1,
  "imu_hz": 20
}
```

### POST /analyze_dual
Analyzes a pair of sessions (wear + shinai) for dual-device metrics.

**Request Body:**
```json
{
  "wear_session_id": "session_2025-11-26_22-00-00_123456.json",
  "shinai_session_id": "session_2025-11-26_22-00-05_234567.json",
  "distance_inches": 30,
  "sword_weight_lbs": 1.1
}
```

### POST /admin/backfill
Triggers re-computation of advanced metrics (Straightness, Consistency, Impact) for all existing sessions in the database. Useful after code updates or when new metrics are added.

**Response:**
```json
{
  "status": "success",
  "processed": [1, 2, 3],
  "failed": []
}
```

## Web Routes

- `GET /` - Sessions dashboard with summary badges.
- `GET /session/<id>` - Detailed session view with metrics and guidance.
- `GET /dual_analysis` - Dual sensor analysis form.
- `POST /analyze_dual_web` - Submit dual analysis and view results.

## Data Storage

### File Structure
- `data/raw_data/` - Original JSON payloads from watch apps.
- `data/processed_data/` - Processed CSV files (IMU and heart rate).
- `data/sessions.db` - SQLite database with session metadata and analysis results.

### Database Schema

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    created_at INTEGER,           -- Unix timestamp
    raw_filename TEXT,            -- Raw JSON filename
    imu_csv TEXT,                 -- Processed IMU CSV
    heart_csv TEXT,               -- Processed heart rate CSV
    duration REAL,                -- Session duration (seconds)
    imu_hz_measured REAL,
    imu_hz_sampling_rate_defined REAL,
    heart_rate_hz_measured REAL,
    heart_rate_hz_sampling_rate REAL,
    heart_mean REAL,              -- Average heart rate (bpm)
    heart_max INTEGER,            -- Maximum heart rate (bpm)
    device_type TEXT,             -- 'wear' or 'shinai'
    strike_count INTEGER,         -- Number of strikes detected
    max_strike_force REAL,        -- Maximum strike force (G)
    avg_strike_force REAL,        -- Average strike force (G)
    avg_intensity REAL,           -- Average movement intensity (G)
    max_intensity REAL,           -- Maximum movement intensity (G)
    
    -- Advanced / Dual Metrics
    max_tip_speed_mps REAL,       -- Max tip speed (m/s)
    max_kinetic_energy_joules REAL, -- Max kinetic energy (J)
    straightness_score REAL,      -- Form score (0-1)
    consistency_score REAL,       -- Form score (0-1)
    shinai_strike_count INTEGER,  -- Strikes detected from shinai sensor
    shinai_max_strike_force REAL, -- Max force from shinai sensor (G)
    shinai_avg_strike_force REAL  -- Avg force from shinai sensor (G)
);
```

### Analysis Algorithms

### Strike Detection
- **Method**: Peak detection on accelerometer magnitude.
- **Threshold**: 2.0 G (configurable).
- **Min Distance**: 200ms between strikes to prevent double-counting.
- **Output**: Strike count, max/avg force, timestamps.

### 2. Physics Estimates (Dual Device Only)
Uses the gyroscope data from the wrist sensor to estimate the tip speed of the shinai.

- **Tip Speed**: $v = \omega \cdot r$
  - $\omega$: Angular velocity (rad/s) from Gyroscope
  - $r$: Length of shinai (1.20m)
- **Kinetic Energy**: $E = 0.5 \cdot m \cdot v^2$
  - $m$: Mass of shinai (0.51kg)
  - **Calories**: Converted from Joules ($1 J = 0.000239 kcal$)
- **Straightness**: 1.0 - (variance_minor / variance_major) on acceleration axes.
- **Consistency**: Correlation between consecutive strike profiles.

## Visual Demonstrations

### Web Interface

The dashboard shows all sessions with color-coded device badges and analysis metrics:

![Web interface with analysis data](docs/images/dashboard_demo.png)

### Dual Sensor Analysis Workflow

Complete workflow showing session selection, parameter input, and results visualization:

![Dual sensor analysis workflow](docs/images/dual_analysis_workflow.webp)

## Console Output Example

```
========================================
       SESSION ANALYSIS REPORT
========================================

[Heart Rate Analysis]
Average HR: 125.3 bpm
Max HR:     165.0 bpm
Time in Zones (samples):
  - Resting/Warm Up (<100): 15
  - Fat Burn (100-130): 45
  - Cardio (130-150): 30
  - Peak (>150): 10

[Movement & Kendo Summary]
Wrist activity (mean): 1.85 G
Wrist activity (max):  5.42 G
Kendo Strikes (wrist): 12
Avg inter-strike interval: 850 ms
Strike rate (wrist): 70.6 strikes/min
Strike forces: see shinai tip analysis (per-strike peak, RMS, impulse)

========================================
```
