from pathlib import Path
import datetime
from typing import Tuple, Dict, Any
import json
import csv


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
            imu_hz_field = payload.get("imu_hz") or payload.get("imuHz")
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
            if "bpm" in hr:
                bpm = hr["bpm"]
            elif "heart_rate" in hr:
                bpm = hr["heart_rate"]
            elif "value" in hr:
                bpm = hr["value"]
            else:
                bpm = None
            hr_rows.append([hr.get("t"), bpm])
        else:
            hr_rows.append([None, hr])

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
            hr_hz_field = payload.get("heart_rate_hz") or payload.get("hr_hz")
            try:
                hr_avg_hz = float(hr_hz_field) if hr_hz_field is not None else None
            except Exception:
                hr_avg_hz = None

    return True, {
        "raw": raw_filename,
        "processed": {"imu": imu_name, "heart_rate": hr_name},
        "sampling": {"imu_hz_measured": imu_avg_hz, "heart_rate_hz_measured": hr_avg_hz},
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

    return True, info2
