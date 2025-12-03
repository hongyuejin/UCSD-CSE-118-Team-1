from pathlib import Path
import datetime
from typing import Tuple, Dict, Any
import json
import csv
import sqlite3
import logging
import time
import re
import bisect

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
    sessions_dir = processed_dir / "sessions"
    shinai_dir = processed_dir / "shinai"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    shinai_dir.mkdir(parents=True, exist_ok=True)
    base = Path(raw_filename).stem

    # Detect shinai (tip-mounted) IMU-only payloads and persist specially
    device_id = payload.get("device_id")
    data_type = payload.get("data_type")
    # Detect shinai (tip-mounted) IMU-only payloads by data_type == 'imu_only'
    if data_type == "imu_only":
        imu_list = payload.get("imu") or []
        imu_headers = ["t", "ax", "ay", "az", "gx", "gy", "gz"]
        imu_rows = []
        times = []
        for item in imu_list:
            if isinstance(item, dict):
                try:
                    t = int(float(item.get("t"))) if item.get("t") is not None else None
                except Exception:
                    t = None
                if t is not None:
                    times.append(t)
                imu_rows.append([
                    t,
                    item.get("ax"),
                    item.get("ay"),
                    item.get("az"),
                    item.get("gx"),
                    item.get("gy"),
                    item.get("gz"),
                ])

        if times:
            start = int(min(times))
            end = int(max(times))
        else:
            start = int(time.time() * 1000)
            end = start

        shinai_name = f"shinai_{start}_{end}_imu.csv"
        shinai_target = shinai_dir / shinai_name
        ok, info = _write_csv_rows(shinai_target, imu_headers, imu_rows)
        if not ok:
            return False, {"error": f"Failed to write shinai imu csv: {info}"}

        # Create per-session matched shinai files (no timestamp-alignment merge by default)
        matched = []

        # Find wrist session imu files in both legacy root and sessions subfolders
        session_candidates = list(processed_dir.glob("session_*_imu.csv"))
        session_candidates += list(sessions_dir.glob("session_*/*_imu.csv"))

        shinai_rows_sorted = sorted([r for r in imu_rows if isinstance(r[0], int)], key=lambda x: x[0])

        for p in session_candidates:
            try:
                with p.open("r", encoding="utf-8") as fh:
                    reader = csv.reader(fh)
                    headers = next(reader, None)
                    wrist_rows = []
                    for row in reader:
                        if not row:
                            continue
                        try:
                            tval = int(float(row[0]))
                        except Exception:
                            continue
                        wrist_rows.append(tval)

                if not wrist_rows:
                    continue

                s_start = wrist_rows[0]
                s_end = wrist_rows[-1]

                # Write matched shinai samples that fall inside the wrist session window
                matched_rows = [r for r in shinai_rows_sorted if r[0] >= s_start and r[0] <= s_end]
                if not matched_rows:
                    # nothing to write for this session
                    continue

                # Determine session folder target: prefer sessions_dir/session_{s_start}_{s_end}
                session_folder = sessions_dir / f"session_{s_start}_{s_end}"
                session_folder.mkdir(parents=True, exist_ok=True)
                matched_name = f"matched_shinai_{s_start}_{s_end}_imu.csv"
                matched_target = session_folder / matched_name
                ok2, info2 = _write_csv_rows(matched_target, imu_headers, matched_rows)
                if ok2:
                    # store path relative to processed_data for convenience
                    relpath = str(Path("sessions") / f"session_{s_start}_{s_end}" / matched_name)
                    matched.append(relpath)
            except Exception:
                continue

        rel_shinai_path = str(Path("shinai") / shinai_name)
        return True, {
            "raw": raw_filename,
            "processed": {"shinai": rel_shinai_path, "matched_shinai": matched},
            "sampling": {},
            "payload": payload,
        }

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

    # For wearable sessions, write into a per-session folder under processed_data/sessions
    imu_times = []
    for r in imu_rows:
        try:
            if r[0] is not None:
                imu_times.append(int(float(r[0])))
        except Exception:
            continue

    if imu_times:
        s_start = int(min(imu_times))
        s_end = int(max(imu_times))
    else:
        s_start = int(time.time() * 1000)
        s_end = s_start

    session_folder = sessions_dir / f"session_{s_start}_{s_end}"
    session_folder.mkdir(parents=True, exist_ok=True)

    imu_name = base + "_imu.csv"
    imu_target = session_folder / imu_name
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
    hr_target = session_folder / hr_name
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

    rel_imu = str(Path("sessions") / f"session_{s_start}_{s_end}" / imu_name)
    rel_hr = str(Path("sessions") / f"session_{s_start}_{s_end}" / hr_name)
    return True, {
        "raw": raw_filename,
        "processed": {"imu": rel_imu, "heart_rate": rel_hr},
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
    metrics = {
        "strike_count": 0,
        "max_strike_force": 0.0,
        "avg_strike_force": 0.0,
        "avg_intensity": 0.0,
        "max_intensity": 0.0
    }
    try:
        from .analysis import analyze_session
        payload_for_analysis = info2.get("payload") if isinstance(info2, dict) else {}
        metrics = analyze_session(payload_for_analysis)
    except Exception:
        LOG.exception("Failed to run session analysis")
    LOG.debug("analyze_session metrics for %s: %s", fname, metrics)
    # -------------------------------------------------------

    payload = info2.get("payload") if isinstance(info2, dict) else {}

    # Prefer wrist-reported strike count if available in payload
    try:
        payload_strike_count = payload.get("strike_count")
        if payload_strike_count is not None:
            metrics["strike_count"] = int(payload_strike_count)
    except Exception:
        LOG.debug("Failed to coerce payload strike_count for %s", fname)

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
    
    # Determine device type (shinai if payload indicates imu_only)
    data_type = payload.get("data_type")
    device_id = payload.get("device_id", "")
    device_type = "shinai" if data_type == "imu_only" else "wear"

    try:
        # Ensure DB schema exists before opening connection
        try:
            from .db import init_db
            init_db()
        except Exception:
            LOG.exception("Failed to ensure DB initialized via init_db")

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        created_at = int(datetime.datetime.now().timestamp())
        imu_csv = info2.get("processed", {}).get("imu")
        heart_csv = info2.get("processed", {}).get("heart_rate")
        shinai_csv = info2.get("processed", {}).get("shinai")
        matched_list = info2.get("processed", {}).get("matched_shinai")
        try:
            matched_json = json.dumps(matched_list) if matched_list else None
        except Exception:
            matched_json = None
        # When processing a shinai payload, propagate matched shinai file paths
        # into the corresponding wear session rows so the UI can render charts.
        try:
            if device_type == "shinai" and matched_list:
                for relpath in matched_list:
                    try:
                        # relpath example: sessions/session_<start>_<end>/matched_shinai_<start>_<end>_imu.csv
                        m = re.match(r"sessions/session_(\d+)_(\d+)/", relpath)
                        if not m:
                            continue
                        s_start = m.group(1)
                        s_end = m.group(2)
                        session_folder_rel = f"sessions/session_{s_start}_{s_end}"
                        # Find wear session whose imu_csv is in the same session folder
                        cur.execute(
                            "SELECT id, matched_shinai FROM sessions WHERE device_type='wear' AND imu_csv LIKE ? ORDER BY id DESC LIMIT 1",
                            (session_folder_rel + "/%_imu.csv",)
                        )
                        wear_row = cur.fetchone()
                        if not wear_row:
                            # As a fallback, search any wear rows with session window in raw_filename
                            cur.execute(
                                "SELECT id, matched_shinai FROM sessions WHERE device_type='wear' AND imu_csv LIKE ?",
                                (session_folder_rel + "/%_imu.csv",)
                            )
                            wear_row = cur.fetchone()
                        if not wear_row:
                            continue

                        wear_id = wear_row[0]
                        existing = wear_row[1]
                        try:
                            existing_list = json.loads(existing) if existing else []
                        except Exception:
                            existing_list = []
                        # Append if not already present
                        if relpath not in existing_list:
                            existing_list.append(relpath)
                        new_json = json.dumps(existing_list)
                        cur.execute(
                            "UPDATE sessions SET matched_shinai = ? WHERE id = ?",
                            (new_json, wear_id)
                        )
                    except Exception:
                        LOG.exception("Failed to update wear session with matched shinai %s", relpath)
        except Exception:
            LOG.exception("Error while propagating matched shinai to wear sessions")
                # If there are matched shinai files, run dual analysis to derive shinai/dual metrics
        dual_metrics = {}
        try:
            if matched_list and len(matched_list) > 0:
                # For now, analyze the first matched shinai file (there will usually be one per session)
                matched_rel = matched_list[0]
                shinai_path = directory / "processed_data" / matched_rel
                shinai_imu = []
                try:
                    with shinai_path.open("r", encoding="utf-8") as fh:
                        reader = csv.reader(fh)
                        headers = next(reader, None)
                        for row in reader:
                            if not row:
                                continue
                            # Expect t, ax, ay, az, gx, gy, gz
                            try:
                                shinai_imu.append({
                                    "t": float(row[0]),
                                    "ax": float(row[1]) if row[1] != '' else None,
                                    "ay": float(row[2]) if row[2] != '' else None,
                                    "az": float(row[3]) if row[3] != '' else None,
                                    "gx": float(row[4]) if len(row) > 4 and row[4] != '' else None,
                                    "gy": float(row[5]) if len(row) > 5 and row[5] != '' else None,
                                    "gz": float(row[6]) if len(row) > 6 and row[6] != '' else None,
                                })
                            except Exception:
                                continue
                except Exception:
                    shinai_imu = []

                wear_data = {"imu": payload.get("imu", [])}
                shinai_data = {"imu": shinai_imu}
                params = {
                    "distance_inches": payload.get("distance_inches"),
                    "sword_weight_lbs": payload.get("sword_weight_lbs")
                }
                try:
                    from .dual_analysis import analyze_dual_session
                    dual_metrics = analyze_dual_session(wear_data, shinai_data, params) or {}
                except Exception:
                    LOG.exception("Exception while running analyze_dual_session")
                    dual_metrics = {}

            # If there was no matched wrist session but this payload contains shinai IMU (shinai-only),
            # attempt to analyze the shinai data standalone so we can populate per-strike metrics.
            data_type_local = payload.get("data_type")
            if (not dual_metrics or len(dual_metrics) == 0) and (data_type_local == "imu_only" or shinai_csv):
                try:
                    # Build shinai imu list from payload if available, otherwise try reading shinai_csv
                    shinai_imu = []
                    imu_list_from_payload = payload.get("imu") or []
                    if imu_list_from_payload:
                        for item in imu_list_from_payload:
                            if isinstance(item, dict):
                                try:
                                    shinai_imu.append({
                                        "t": float(item.get("t")),
                                        "ax": float(item.get("ax")) if item.get("ax") is not None and item.get("ax") != '' else None,
                                        "ay": float(item.get("ay")) if item.get("ay") is not None and item.get("ay") != '' else None,
                                        "az": float(item.get("az")) if item.get("az") is not None and item.get("az") != '' else None,
                                        "gx": float(item.get("gx")) if item.get("gx") is not None and item.get("gx") != '' else None,
                                        "gy": float(item.get("gy")) if item.get("gy") is not None and item.get("gy") != '' else None,
                                        "gz": float(item.get("gz")) if item.get("gz") is not None and item.get("gz") != '' else None,
                                    })
                                except Exception:
                                    continue
                    elif shinai_csv:
                        shinai_path = directory / "processed_data" / shinai_csv
                        try:
                            with shinai_path.open("r", encoding="utf-8") as fh:
                                reader = csv.reader(fh)
                                headers = next(reader, None)
                                for row in reader:
                                    if not row:
                                        continue
                                    try:
                                        shinai_imu.append({
                                            "t": float(row[0]),
                                            "ax": float(row[1]) if row[1] != '' else None,
                                            "ay": float(row[2]) if row[2] != '' else None,
                                            "az": float(row[3]) if row[3] != '' else None,
                                            "gx": float(row[4]) if len(row) > 4 and row[4] != '' else None,
                                            "gy": float(row[5]) if len(row) > 5 and row[5] != '' else None,
                                            "gz": float(row[6]) if len(row) > 6 and row[6] != '' else None,
                                        })
                                    except Exception:
                                        continue
                        except Exception:
                            shinai_imu = []

                    if shinai_imu:
                        wear_data = {"imu": payload.get("imu", [])}
                        shinai_data = {"imu": shinai_imu}
                        params = {
                            "distance_inches": payload.get("distance_inches"),
                            "sword_weight_lbs": payload.get("sword_weight_lbs")
                        }
                        try:
                            from .dual_analysis import analyze_dual_session
                            dual_metrics = analyze_dual_session(wear_data, shinai_data, params) or {}
                        except Exception:
                            LOG.exception("Exception while running analyze_dual_session for shinai-only payload")
                            dual_metrics = {}
                except Exception:
                    LOG.exception("Error while attempting shinai-only analysis")
                    dual_metrics = {}
        except Exception:
            dual_metrics = {}

        insert_params = (
            created_at, fname, imu_csv, heart_csv, shinai_csv, matched_json, duration, imu_hz_measured, imu_hz_defined,
            heart_rate_hz_measured, heart_hz_defined, heart_mean, heart_max, device_type,
            metrics.get("strike_count"), metrics.get("max_strike_force"), metrics.get("avg_strike_force"),
            metrics.get("avg_intensity"), metrics.get("max_intensity"),
            dual_metrics.get("max_tip_speed_mps"), dual_metrics.get("max_kinetic_energy_joules"),
            dual_metrics.get("straightness_score"), dual_metrics.get("consistency_score"),
            dual_metrics.get("shinai_strike_count"), dual_metrics.get("shinai_max_strike_force"),
            dual_metrics.get("shinai_avg_strike_force")
        )
        LOG.debug("Inserting session row with params: %s", insert_params)
        cur.execute(
            "INSERT INTO sessions (created_at, raw_filename, imu_csv, heart_csv, shinai_csv, matched_shinai, duration, imu_hz_measured, imu_hz_sampling_rate_defined, heart_rate_hz_measured, heart_rate_hz_sampling_rate, heart_mean, heart_max, device_type, strike_count, max_strike_force, avg_strike_force, avg_intensity, max_intensity, max_tip_speed_mps, max_kinetic_energy_joules, straightness_score, consistency_score, shinai_strike_count, shinai_max_strike_force, shinai_avg_strike_force) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            insert_params,
        )
        # capture the new session id so we can persist per-strike rows
        try:
            session_id = cur.lastrowid
        except Exception:
            session_id = None
        LOG.debug("resolved session_id after insert: %s", session_id)
        # If lastrowid is not available, try to lookup by raw filename
        if not session_id:
            try:
                cur.execute("SELECT id FROM sessions WHERE raw_filename = ? ORDER BY id DESC LIMIT 1", (fname,))
                r = cur.fetchone()
                if r:
                    session_id = r[0]
            except Exception:
                session_id = None

        # Persist per-strike rows into the strikes table if available
        try:
            LOG.debug("dual_metrics keys: %s", list(dual_metrics.keys()) if isinstance(dual_metrics, dict) else None)
            per_strikes = dual_metrics.get("per_strikes") if isinstance(dual_metrics, dict) else None
            LOG.debug("per_strikes present: %s", bool(per_strikes))
            LOG.debug("resolved session_id: %s", session_id)
            LOG.debug("dual_metrics keys (print removed)")
            inserted_strike_count = 0
            if per_strikes and isinstance(per_strikes, list) and len(per_strikes) > 0:
                for s in per_strikes:
                    try:
                        t_ms = s.get("t_ms") if s.get("t_ms") is not None else s.get("t")
                        if t_ms is None:
                            LOG.debug("skipping strike without t_ms: %s", s)
                            continue
                        try:
                            t_ms = int(float(t_ms))
                        except Exception:
                            LOG.debug("invalid t_ms for strike, skipping: %r", t_ms)
                            continue
                        peak = s.get("peak_g")
                        rms = s.get("rms_g")
                        integral = s.get("integral")
                        half_width = s.get("half_width_ms")
                        tip_speed = s.get("tip_speed_mps") if s.get("tip_speed_mps") is not None else None
                        created = int(datetime.datetime.now().timestamp())
                        params = (session_id, t_ms, peak, rms, integral, half_width, tip_speed, created)
                        LOG.debug("inserting strike with params: %s", params)
                        cur.execute(
                            "INSERT INTO strikes (session_id, t_ms, peak_g, rms_g, integral, half_width_ms, tip_speed_mps, created_at) VALUES (?,?,?,?,?,?,?,?)",
                            params,
                        )
                        inserted_strike_count += 1
                    except Exception:
                        LOG.exception("Failed to insert strike row for session %s, strike=%s", session_id, s)
                LOG.debug("inserted %s strikes for session %s", inserted_strike_count, session_id)
        except Exception:
            LOG.exception("Error while persisting per-strike metrics for %s", fname)

        conn.commit()
        conn.close()
    except Exception:
        LOG.exception("Failed to insert session metadata into %s", db_path)

    return True, info2
