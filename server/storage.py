from pathlib import Path
import datetime
from typing import Tuple, Dict, Any
import json
import csv
import sqlite3
import logging

LOG = logging.getLogger("sensor_server.storage")


def make_data_dir(dir_path: str = "data") -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    p = repo_root / dir_path
    p.mkdir(parents=True, exist_ok=True)
    (p / "raw_data").mkdir(parents=True, exist_ok=True)
    (p / "processed_data").mkdir(parents=True, exist_ok=True)
    return p


def make_unique_filename(prefix: str = "session", ext: str = ".json") -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    return f"{prefix}_{ts}{ext}"


def _write_text(target: Path, text: str) -> Tuple[bool, str]:
    try:
        target.write_text(text, encoding="utf-8")
        return True, str(target.name)
    except Exception as exc:
        return False, str(exc)


def _write_csv_rows(target: Path, headers: list, rows: list) -> Tuple[bool, str]:
    try:
        with target.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for r in rows:
                writer.writerow(r)
        return True, str(target.name)
    except Exception as exc:
        return False, str(exc)


def _process_and_save(directory: Path, raw_filename: str, raw_text: str) -> Tuple[bool, Dict[str, Any]]:
    try:
        payload = json.loads(raw_text)
    except Exception as exc:
        return False, {"error": f"Invalid JSON: {exc}"}

    processed_dir = directory / "processed_data"
    base = Path(raw_filename).stem

    imu_list = payload.get("imu") or []
    imu_headers = ["t", "ax", "ay", "az", "gx", "gy", "gz"]
    imu_rows = []
    for item in imu_list:
        if isinstance(item, dict):
            imu_rows.append([
                item.get("t"),
                item.get("ax"),
                item.get("ay"),
                item.get("az"),
                item.get("gx"),
                item.get("gy"),
                item.get("gz"),
            ])

    imu_avg_hz = None
    if len(imu_rows) > 1:
        try:
            first_t = float(imu_rows[0][0])
            last_t = float(imu_rows[-1][0])
            interval = (last_t - first_t) / float(len(imu_rows) - 1)
            imu_avg_hz = 1000.0 / interval if interval > 0 else None
        except Exception:
            imu_hz_field = payload.get("imu_hz")
            try:
                imu_avg_hz = float(imu_hz_field) if imu_hz_field is not None else None
            except Exception:
                imu_avg_hz = None

    imu_name = base + "_imu.csv"
    imu_target = processed_dir / imu_name
    ok, info = _write_csv_rows(imu_target, imu_headers, imu_rows)
    if not ok:
        return False, {"error": f"Failed to write imu csv: {info}"}

    hr_list = payload.get("heart_rates") or []
    hr_headers = ["t", "bpm"]
    hr_rows = []
    for hr in hr_list:
        if isinstance(hr, dict):
            bpm = hr.get("bpm")
            if bpm is None:
                bpm = hr.get("value")
            hr_rows.append([hr.get("t"), bpm])

    hr_name = base + "_heart_rate.csv"
    hr_target = processed_dir / hr_name
    ok, info = _write_csv_rows(hr_target, hr_headers, hr_rows)
    if not ok:
        return False, {"error": f"Failed to write heart rate csv: {info}"}

    hr_avg_hz = None
    if len(hr_rows) > 1:
        try:
            first_t = float(hr_rows[0][0])
            last_t = float(hr_rows[-1][0])
            interval = (last_t - first_t) / float(len(hr_rows) - 1)
            hr_avg_hz = 1000.0 / interval if interval > 0 else None
        except Exception:
            hr_hz_field = payload.get("heart_rate_hz")
            try:
                hr_avg_hz = float(hr_hz_field) if hr_hz_field is not None else None
            except Exception:
                hr_avg_hz = None

    return True, {
        "raw": raw_filename,
        "processed": {"imu": imu_name, "heart_rate": hr_name},
        "sampling": {"imu_hz_measured": imu_avg_hz, "heart_rate_hz_measured": hr_avg_hz},
        "payload": payload,
    }


def save_raw_json_payload(directory: Path, raw_text: str) -> Tuple[bool, Any]:
    raw_dir = directory / "raw_data"
    fname = make_unique_filename()
    target = raw_dir / fname

    ok, info = _write_text(target, raw_text)
    if not ok:
        return False, info

    ok, info2 = _process_and_save(directory, fname, raw_text)
    if not ok:
        return False, info2

    # --- NEW: Run detailed analysis and print to console ---
    try:
        from .analysis import analyze_session
        payload_for_analysis = info2.get("payload") if isinstance(info2, dict) else {}
        analyze_session(payload_for_analysis)
    except Exception as e:
        LOG.error(f"Failed to run session analysis: {e}")
    # -------------------------------------------------------

    payload = info2.get("payload") if isinstance(info2, dict) else {}

    duration = None
    try:
        if payload.get("duration") is not None:
            duration = float(payload.get("duration"))
    except Exception:
        duration = None

    imu_rows_count = 0
    hr_values = []
    try:
        imu_list = payload.get("imu") or []
        for item in imu_list:
            imu_rows_count += 1
    except Exception:
        imu_rows_count = 0

    try:
        hr_list = payload.get("heart_rates") or []
        for item in hr_list:
            if isinstance(item, dict):
                v = item.get("bpm")
                if v is None:
                    v = item.get("value")
                try:
                    if v is not None:
                        hr_values.append(float(v))
                except Exception:
                    pass
            else:
                try:
                    hr_values.append(float(item))
                except Exception:
                    LOG.debug("Failed to parse heart rate value %r in %s", item, fname)
    except Exception:
        hr_values = []

    if duration is None:
        try:
            imu_list = payload.get("imu") or []
            if len(imu_list) > 1 and isinstance(imu_list[0], dict):
                first_t = float(imu_list[0].get("t"))
                last_t = float(imu_list[-1].get("t"))
                duration = (last_t - first_t) / 1000.0
        except Exception:
            duration = None

    imu_hz_measured = None
    if duration and duration > 0:
        try:
            imu_hz_measured = float(imu_rows_count) / float(duration)
        except Exception:
            imu_hz_measured = None

    heart_rate_hz_measured = None
    if duration and duration > 0:
        try:
            heart_rate_hz_measured = float(len(hr_values)) / float(duration) if len(hr_values) > 0 else None
        except Exception:
            heart_rate_hz_measured = None

    imu_hz_defined = None
    try:
        imu_hz_defined = payload.get("imu_hz")
        if imu_hz_defined is not None:
            imu_hz_defined = float(imu_hz_defined)
    except Exception:
        imu_hz_defined = None

    heart_hz_defined = None
    try:
        heart_hz_defined = payload.get("heart_rate_hz")
        if heart_hz_defined is not None:
            heart_hz_defined = float(heart_hz_defined)
    except Exception:
        heart_hz_defined = None

    heart_mean = None
    heart_max = None
    try:
        if len(hr_values) > 0:
            heart_mean = sum(hr_values) / float(len(hr_values))
            heart_max = int(max(hr_values))
    except Exception:
        heart_mean = None
        heart_max = None

    db_path = directory / "sessions.db"
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        created_at = int(datetime.datetime.now().timestamp())
        imu_csv = info2.get("processed", {}).get("imu")
        heart_csv = info2.get("processed", {}).get("heart_rate")
        cur.execute(
            "INSERT INTO sessions (created_at, raw_filename, imu_csv, heart_csv, duration, imu_hz_measured, imu_hz_sampling_rate_defined, heart_rate_hz_measured, heart_rate_hz_sampling_rate, heart_mean, heart_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (created_at, fname, imu_csv, heart_csv, duration, imu_hz_measured, imu_hz_defined, heart_rate_hz_measured, heart_hz_defined, heart_mean, heart_max),
        )
        conn.commit()
        conn.close()
    except Exception:
        LOG.exception("Failed to insert session metadata into %s", db_path)

    return True, info2
