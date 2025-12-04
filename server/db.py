from pathlib import Path
import sqlite3


def init_db() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "sessions.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER,
            raw_filename TEXT,
            imu_csv TEXT,
            heart_csv TEXT,
            shinai_csv TEXT,
            matched_shinai TEXT,
            duration REAL,
            imu_hz_measured REAL,
            imu_hz_sampling_rate_defined REAL,
            heart_rate_hz_measured REAL,
            heart_rate_hz_sampling_rate REAL,
            heart_mean REAL,
            heart_max INTEGER,
            device_type TEXT,
            strike_count INTEGER,
            max_strike_force REAL,
            avg_strike_force REAL,
            avg_intensity REAL,
            max_intensity REAL
            ,
            -- Shinai / Dual-derived metrics
            max_tip_speed_mps REAL,
            max_kinetic_energy_joules REAL,
            straightness_score REAL,
            consistency_score REAL,
            shinai_strike_count INTEGER,
            shinai_max_strike_force REAL,
            shinai_avg_strike_force REAL
        )
        """
    )
    # Ensure new columns exist for older DBs: add shinai_csv and matched_shinai if missing
    cur.execute("PRAGMA table_info(sessions)")
    cols = [r[1] for r in cur.fetchall()]
    if "shinai_csv" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN shinai_csv TEXT")
    if "matched_shinai" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN matched_shinai TEXT")
    # Add any new dual/shinai metric columns if they're missing in older DBs
    if "max_tip_speed_mps" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN max_tip_speed_mps REAL")
    if "max_kinetic_energy_joules" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN max_kinetic_energy_joules REAL")
    if "straightness_score" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN straightness_score REAL")
    if "consistency_score" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN consistency_score REAL")
    if "shinai_strike_count" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN shinai_strike_count INTEGER")
    if "shinai_max_strike_force" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN shinai_max_strike_force REAL")
    if "shinai_avg_strike_force" not in cols:
        cur.execute("ALTER TABLE sessions ADD COLUMN shinai_avg_strike_force REAL")
    conn.commit()
    conn.close()

    # Ensure strikes table exists for per-strike persistence
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS strikes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            t_ms INTEGER,
            peak_g REAL,
            rms_g REAL,
            integral REAL,
            half_width_ms REAL,
            tip_speed_mps REAL,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
