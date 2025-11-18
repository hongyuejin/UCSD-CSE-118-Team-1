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
            duration REAL,
            imu_hz_measured REAL,
            imu_hz_sampling_rate_defined REAL,
            heart_rate_hz_measured REAL,
            heart_rate_hz_sampling_rate REAL,
            heart_mean REAL,
            heart_max INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
