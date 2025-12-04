import math
import logging
import statistics

LOG = logging.getLogger("sensor_server.analysis")


def calculate_hr_zones(hr_values):
    """
    Calculates time spent in different HR zones.
    Zones:
    - Resting/Warm Up: < 100 bpm
    - Fat Burn: 100 - 130 bpm
    - Cardio: 130 - 150 bpm
    - Peak: > 150 bpm
    """
    zones = {
        "Resting/Warm Up (<100)": 0,
        "Fat Burn (100-130)": 0,
        "Cardio (130-150)": 0,
        "Peak (>150)": 0,
    }

    if not hr_values:
        return zones

    for bpm in hr_values:
        if bpm < 100:
            zones["Resting/Warm Up (<100)"] += 1
        elif bpm < 130:
            zones["Fat Burn (100-130)"] += 1
        elif bpm < 150:
            zones["Cardio (130-150)"] += 1
        else:
            zones["Peak (>150)"] += 1

    return zones


def calculate_movement_intensity(imu_rows):
    """
    Calculates statistics on wrist activity using accelerometer vector magnitude.
    This is a descriptive metric (G) for general activity - not a per-strike force.
    """
    if not imu_rows:
        return {"wrist_activity_mean_g": 0.0, "wrist_activity_max_g": 0.0}

    intensities = []
    used_source = None
    for row in imu_rows:
        accel_used = False
        try:
            ax = row[1]
            ay = row[2]
            az = row[3]
            if ax is not None and ay is not None and az is not None:
                axf = float(ax)
                ayf = float(ay)
                azf = float(az)
                magnitude = math.sqrt(axf * axf + ayf * ayf + azf * azf)
                intensities.append(magnitude / 9.80665)
                used_source = "accel"
                accel_used = True
        except Exception:
            pass

        if accel_used:
            continue

        try:
            gx = row[4]
            gy = row[5]
            gz = row[6]
            if gx is not None and gy is not None and gz is not None:
                gxf = float(gx)
                gyf = float(gy)
                gzf = float(gz)
                magnitude = math.sqrt(gxf * gxf + gyf * gyf + gzf * gzf)
                intensities.append(magnitude / 9.80665)
                if used_source is None:
                    used_source = "gyro"
        except Exception:
            continue

    if used_source:
        LOG.debug("calculate_movement_intensity used source=%s, samples=%d", used_source, len(intensities))

    if not intensities:
        return {"wrist_activity_mean_g": 0.0, "wrist_activity_max_g": 0.0}

    try:
        gravity_bias = statistics.median(intensities)
    except statistics.StatisticsError:
        gravity_bias = 1.0
    if gravity_bias <= 0:
        gravity_bias = 1.0

    net_values = [max(val - gravity_bias, 0.0) for val in intensities]
    mean_g = sum(net_values) / len(net_values)
    max_g = max(net_values) if net_values else 0.0

    return {"wrist_activity_mean_g": mean_g, "wrist_activity_max_g": max_g}


def analyze_session(payload):
    """
    Orchestrates the analysis. Extracts data from the payload, calls calculation functions,
    and prints a formatted report to the console.
    """
    report_lines = []
    report_lines.append("\n" + "=" * 40)
    report_lines.append("       SESSION ANALYSIS REPORT       ")
    report_lines.append("=" * 40)

    # 1. Heart Rate Analysis
    hr_list = payload.get("heart_rates") or []
    hr_values = []
    for item in hr_list:
        val = None
        if isinstance(item, dict):
            val = item.get("bpm") or item.get("value")
        else:
            val = item

        if val is not None:
            try:
                hr_values.append(float(val))
            except ValueError:
                pass

    report_lines.append(f"\n[Heart Rate Analysis]")
    if hr_values:
        avg_hr = sum(hr_values) / len(hr_values)
        max_hr = max(hr_values)
        report_lines.append(f"Average HR: {avg_hr:.1f} bpm")
        report_lines.append(f"Max HR:     {max_hr:.1f} bpm")

        zones = calculate_hr_zones(hr_values)
        report_lines.append("Time in Zones (samples):")
        for zone, count in zones.items():
            report_lines.append(f"  - {zone}: {count}")
    else:
        report_lines.append("No Heart Rate data available.")

    # 2. IMU & Kendo Analysis
    imu_list = payload.get("imu") or []
    imu_rows = []
    accel_count = 0
    gyro_count = 0
    for item in imu_list:
        if isinstance(item, dict):
            t = item.get("t")
            ax = item.get("ax") if item.get("ax") is not None else item.get("accel_x") if item.get("accel_x") is not None else item.get("x") if item.get("x") is not None else None
            ay = item.get("ay") if item.get("ay") is not None else item.get("accel_y") if item.get("accel_y") is not None else item.get("y") if item.get("y") is not None else None
            az = item.get("az") if item.get("az") is not None else item.get("accel_z") if item.get("accel_z") is not None else item.get("z") if item.get("z") is not None else None
            gx = item.get("gx") if item.get("gx") is not None else item.get("gyro_x") if item.get("gyro_x") is not None else None
            gy = item.get("gy") if item.get("gy") is not None else item.get("gyro_y") if item.get("gyro_y") is not None else None
            gz = item.get("gz") if item.get("gz") is not None else item.get("gyro_z") if item.get("gyro_z") is not None else None
            if ax is not None or ay is not None or az is not None:
                accel_count += 1
            if gx is not None or gy is not None or gz is not None:
                gyro_count += 1
            imu_rows.append([t, ax, ay, az, gx, gy, gz])
    LOG.debug(
        "analyze_session: total imu samples=%d accel_samples=%d gyro_samples=%d",
        len(imu_rows),
        accel_count,
        gyro_count,
    )

    report_lines.append(f"[Movement & Kendo Summary]")
    strike_count_value = 0
    if imu_rows:
        activity = calculate_movement_intensity(imu_rows)
        mean_g = activity.get("wrist_activity_mean_g", 0.0)
        max_g = activity.get("wrist_activity_max_g", 0.0)
        report_lines.append(f"Wrist activity (mean): {mean_g:.2f} G")
        report_lines.append(f"Wrist activity (max):  {max_g:.2f} G")

        # Kendo Stats (wrist provides strike count/timestamps only)
        reported_strike_count = payload.get("strike_count")
        target_strike_count = None
        if reported_strike_count is not None:
            try:
                target_strike_count = int(reported_strike_count)
            except Exception:
                LOG.debug("Invalid strike_count in payload: %r", reported_strike_count)
        if target_strike_count is not None and target_strike_count < 0:
            target_strike_count = None
        kendo_stats = detect_kendo_strikes(imu_rows, target_count=target_strike_count)
        strike_count = kendo_stats.get("strike_count", 0)
        strike_count_value = target_strike_count if target_strike_count is not None else strike_count
        timestamps = kendo_stats.get("strike_timestamps", [])
        report_lines.append(f"Kendo Strikes (wrist): {strike_count_value}")

        # Derived time-based metrics
        avg_isi_ms = 0.0
        strike_rate_per_min = 0.0
        if len(timestamps) >= 2:
            intervals = [j - i for i, j in zip(timestamps[:-1], timestamps[1:])]
            avg_isi_ms = sum(intervals) / len(intervals)
            strike_rate_per_min = 60000.0 / avg_isi_ms if avg_isi_ms > 0 else 0.0

        report_lines.append(f"Avg inter-strike interval: {avg_isi_ms:.0f} ms")
        report_lines.append(f"Strike rate (wrist): {strike_rate_per_min:.1f} strikes/min")
        report_lines.append("Strike forces: see shinai tip analysis (per-strike peak, RMS, impulse)")
    else:
        report_lines.append("No IMU data available.")

    report_lines.append("\n" + "=" * 40 + "\n")

    print("\n".join(report_lines))

    # Return metrics for storage
    metrics = {
        "strike_count": 0,
        "max_strike_force": 0.0,
        "avg_strike_force": 0.0,
        # Backwards-compatible DB fields (populated from wrist activity mean/max)
        "avg_intensity": 0.0,
        "max_intensity": 0.0,
        # New friendly metrics (not yet stored separately in DB)
        "wrist_activity_mean_g": 0.0,
        "wrist_activity_max_g": 0.0,
        "avg_inter_strike_ms": 0.0,
        "strike_rate_per_min": 0.0,
    }

    if imu_rows:
        metrics["wrist_activity_mean_g"] = mean_g
        metrics["wrist_activity_max_g"] = max_g
        # populate compatible fields for DB
        metrics["avg_intensity"] = mean_g
        metrics["max_intensity"] = max_g
        metrics["avg_inter_strike_ms"] = avg_isi_ms
        metrics["strike_rate_per_min"] = strike_rate_per_min
        metrics["strike_count"] = strike_count_value
        metrics["max_strike_force"] = kendo_stats.get("max_strike_force", 0.0)
        metrics["avg_strike_force"] = kendo_stats.get("avg_strike_force", 0.0)

    return metrics


def detect_kendo_strikes(imu_rows, threshold=2.0, min_dist_ms=200, target_count=None):
    """
    Detects sword strikes based on accelerometer peaks.

    Args:
        imu_rows: List of [t, ax, ay, az, gx, gy, gz]
        threshold: Acceleration magnitude threshold (G) to count as a strike.
        min_dist_ms: Minimum time (ms) between strikes to avoid double counting.
        target_count: Optional strike count reference from the wearable.

    Returns:
        dict: {
            "strike_count": int,
            "max_strike_force": float,
            "avg_strike_force": float,
            "strike_timestamps": list[float],
            "calibrated_threshold": float,
            "raw_detected_count": int,
        }
    """
    net_series = _build_net_g_series(imu_rows)
    if not net_series:
        return {
            "strike_count": 0,
            "max_strike_force": 0.0,
            "avg_strike_force": 0.0,
            "strike_timestamps": [],
            "calibrated_threshold": threshold,
            "raw_detected_count": 0,
        }

    strikes = _peak_detect_from_series(net_series, threshold, min_dist_ms)
    raw_detected = len(strikes)
    used_threshold = threshold

    if target_count and target_count > 0:
        used_threshold, strikes = _calibrate_threshold_to_target(
            net_series,
            min_dist_ms,
            target_count,
            threshold,
            strikes,
        )
        LOG.debug(
            "detect_kendo_strikes calibrated using target=%s raw=%s final=%s threshold=%.2f",
            target_count,
            raw_detected,
            len(strikes),
            used_threshold,
        )

    count = len(strikes)
    max_force = max([s[1] for s in strikes]) if strikes else 0.0
    avg_force = sum([s[1] for s in strikes]) / count if strikes else 0.0

    return {
        "strike_count": count,
        "max_strike_force": max_force,
        "avg_strike_force": avg_force,
        "strike_timestamps": [s[0] for s in strikes],
        "calibrated_threshold": used_threshold,
        "raw_detected_count": raw_detected,
    }


def _build_net_g_series(imu_rows):
    series = []
    fallback_time = 0.0
    for row in imu_rows:
        used_fallback_time = False
        try:
            timestamp = float(row[0])
        except (TypeError, ValueError):
            timestamp = fallback_time
            used_fallback_time = True

        if used_fallback_time:
            fallback_time += 10.0

        ax = row[1]
        ay = row[2]
        az = row[3]
        if ax is None or ay is None or az is None:
            continue

        try:
            axf = float(ax)
            ayf = float(ay)
            azf = float(az)
        except (TypeError, ValueError):
            continue

        magnitude = math.sqrt(axf * axf + ayf * ayf + azf * azf) / 9.80665
        net_g = max(magnitude - 1.0, 0.0)
        series.append((timestamp, net_g))

    return series


def _peak_detect_from_series(series, threshold, min_dist_ms):
    strikes = []
    if not series:
        return strikes

    last_strike_time = series[0][0] - min_dist_ms
    for timestamp, magnitude in series:
        if magnitude > threshold:
            if (timestamp - last_strike_time) > min_dist_ms:
                strikes.append((timestamp, magnitude))
                last_strike_time = timestamp
            elif strikes and magnitude > strikes[-1][1]:
                strikes[-1] = (timestamp, magnitude)
                last_strike_time = timestamp
    return strikes


def _calibrate_threshold_to_target(series, min_dist_ms, target_count, base_threshold, base_result):
    if not series or target_count <= 0:
        return base_threshold, base_result

    magnitudes = [value for _, value in series]
    if not magnitudes:
        return base_threshold, base_result

    low = 0.1
    high = max(max(magnitudes) + 0.5, base_threshold + 0.5)
    best_threshold = base_threshold
    best_strikes = base_result
    best_diff = abs(len(base_result) - target_count)

    for _ in range(8):
        if high - low < 0.05:
            break
        mid = (low + high) / 2.0
        candidate = _peak_detect_from_series(series, mid, min_dist_ms)
        diff = abs(len(candidate) - target_count)

        if diff < best_diff or (diff == best_diff and abs(mid - base_threshold) < abs(best_threshold - base_threshold)):
            best_diff = diff
            best_strikes = candidate
            best_threshold = mid

        if len(candidate) > target_count:
            low = mid
        elif len(candidate) < target_count:
            high = mid
        else:
            break

    return best_threshold, best_strikes


def interpret_session_metrics(metrics: dict) -> dict:
    """
    Produce a beginner-friendly interpretation of numeric session metrics.

    Input expects keys commonly produced by analysis functions, for example:
      - avg_intensity (G)
      - straightness_score (0..1)
      - consistency_score (0..1)
      - heart_mean (bpm)

    Returns a dict with categorical labels and a short recommendation string.
    """
    # Read numeric inputs with safe fallbacks
    avg_intensity = 0.0
    try:
        avg_intensity = float(metrics.get("avg_intensity", metrics.get("wrist_activity_mean_g", 0.0)) or 0.0)
    except Exception:
        avg_intensity = 0.0

    straightness = 0.0
    try:
        straightness = float(metrics.get("straightness_score", 0.0) or 0.0)
    except Exception:
        straightness = 0.0

    consistency = 0.0
    try:
        consistency = float(metrics.get("consistency_score", 0.0) or 0.0)
    except Exception:
        consistency = 0.0

    heart_mean = 0.0
    try:
        heart_mean = float(metrics.get("heart_mean", 0.0) or 0.0)
    except Exception:
        heart_mean = 0.0

    # Effort categories (based on avg_intensity in G) - tuneable thresholds
    if avg_intensity < 1.5:
        effort_cat = "Low"
        effort_color = "#4CAF50"
    elif avg_intensity < 3.5:
        effort_cat = "Moderate"
        effort_color = "#FF9800"
    else:
        effort_cat = "High"
        effort_color = "#F44336"

    # Control score: weighted combination of straightness & consistency
    # If both scores are missing/zero, mark as N/A instead of penalizing
    control_score = None
    # Treat N/A only when both are missing (None), not when they are 0.0
    if (metrics.get("straightness_score") is None) and (metrics.get("consistency_score") is None):
        control_cat = "N/A"
        control_color = "#9E9E9E"
        control_score = None
    else:
        control_score = (0.6 * straightness) + (0.4 * consistency)
        if control_score >= 0.75:
            control_cat = "Good"
            control_color = "#4CAF50"
        elif control_score >= 0.5:
            control_cat = "Average"
            control_color = "#FFEB3B"
        else:
            control_cat = "Needs work"
            control_color = "#F44336"

    # Heart categories
    if heart_mean == 0:
        heart_cat = "N/A"
        heart_color = "#9E9E9E"
    elif heart_mean < 90:
        heart_cat = "Calm"
        heart_color = "#4CAF50"
    elif heart_mean < 130:
        heart_cat = "Moderate"
        heart_color = "#FF9800"
    else:
        heart_cat = "Elevated"
        heart_color = "#F44336"

    # Simple recommendations based on combinations
    recommendation = ""
    if effort_cat == "High" and control_cat == "Needs work":
        recommendation = "You're swinging hard but losing form - focus on slow control drills (3x1min)."
    elif effort_cat == "Low" and control_cat == "Good":
        recommendation = "Good control - try adding short power reps while keeping form."
    elif control_cat == "Needs work":
        recommendation = "Work on straightness and repeatability: slow, focused swings."
    else:
        recommendation = "Nice session - keep practicing and watch trends over time."

    # If heart is elevated, add short tip
    if heart_cat == "Elevated":
        recommendation += " Rest longer between sets if needed."

    return {
        "effort_category": effort_cat,
        "effort_color": effort_color,
        "effort_value": round(avg_intensity, 2),
        "control_category": control_cat,
        "control_color": control_color,
        "control_score": (round(control_score, 2) if control_score is not None else None),
        "heart_category": heart_cat,
        "heart_color": heart_color,
        "heart_value": round(heart_mean, 0),
        "recommendation": recommendation,
    }

# Centralized compute-and-persist for session metrics
def compute_and_persist_session_metrics(session_id: int) -> bool:
    """Compute derived metrics from CSVs for a session and persist to DB.

    Returns True if metrics were computed and saved, False otherwise.
    """
    import sqlite3, json, math
    from pathlib import Path
    from .views import _repo_data_paths
    from .dual_analysis import (
        calculate_straightness,
        calculate_consistency,
        calculate_shinai_strike_metrics,
    )

    db_path, processed_dir, _ = _repo_data_paths()
    if not db_path.exists():
        return False

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    sess = dict(row)

    # Resolve CSV path: prefer matched shinai, else imu_csv
    shinai_path = None
    try:
        matched_raw = sess.get("matched_shinai")
        if matched_raw:
            try:
                matched_list = json.loads(matched_raw) if isinstance(matched_raw, str) else matched_raw
            except Exception:
                matched_list = matched_raw
            if isinstance(matched_list, list) and len(matched_list) > 0:
                candidate = processed_dir / matched_list[0]
                if candidate.exists():
                    shinai_path = candidate
        if shinai_path is None and sess.get("imu_csv"):
            candidate2 = processed_dir / sess.get("imu_csv")
            if candidate2.exists():
                shinai_path = candidate2
    except Exception:
        shinai_path = None

    if shinai_path is None:
        conn.close()
        return False

    # Load rows
    import csv as _csv
    shinai_rows = []
    try:
        with shinai_path.open("r", encoding="utf-8") as fh:
            reader = _csv.reader(fh)
            _ = next(reader, None)
            for r in reader:
                if r:
                    shinai_rows.append(r)
    except Exception:
        conn.close()
        return False

    # Compute metrics
    straightness = None
    consistency = None
    try:
        straightness = float(calculate_straightness(shinai_rows))
        consistency = float(calculate_consistency([], shinai_rows))
    except Exception as e:
        LOG.warning("Metric computation failed for session %s: %s", session_id, e)
        pass

    impact = None
    max_g = avg_g = strike_count = None
    try:
        impact = calculate_shinai_strike_metrics(shinai_rows)
        strike_count = impact.get("shinai_strike_count")
        max_g = impact.get("shinai_max_strike_force")
        avg_g = impact.get("shinai_avg_strike_force")
    except Exception:
        pass

    # Pace from DB if available else estimate
    duration = sess.get("duration") or 0
    if duration and strike_count:
        rate_per_min = (strike_count / duration) * 60.0
        avg_interval_ms = (duration / max(strike_count, 1)) * 1000.0
    else:
        rate_per_min = None
        avg_interval_ms = None

    # Energy from wrist gyro if available
    max_tip_speed = None
    energy_cal = None
    try:
        imu_rel = sess.get("imu_csv")
        if imu_rel:
            imu_path = processed_dir / imu_rel
            if imu_path.exists():
                max_gyro_mag = 0.0
                with imu_path.open("r", encoding="utf-8") as fh:
                    reader = _csv.reader(fh)
                    _ = next(reader, None)
                    for rowr in reader:
                        if not rowr or len(rowr) < 7:
                            continue
                        try:
                            gx = float(rowr[4]) if rowr[4] != '' else 0.0
                            gy = float(rowr[5]) if rowr[5] != '' else 0.0
                            gz = float(rowr[6]) if rowr[6] != '' else 0.0
                            gyro_mag = (gx*gx + gy*gy + gz*gz) ** 0.5
                            if gyro_mag > max_gyro_mag:
                                max_gyro_mag = gyro_mag
                        except Exception:
                            continue
                if max_gyro_mag > 0:
                    distance_m = 1.2
                    mass_kg = 0.57
                    max_tip_speed = max_gyro_mag * distance_m
                    energy_j = 0.5 * mass_kg * (max_tip_speed ** 2)
                    energy_cal = energy_j * 0.000239006
    except Exception:
        pass

    # Persist
    try:
        cur.execute(
            "UPDATE sessions SET straightness_score = ?, consistency_score = ?, shinai_strike_count = ?, shinai_max_strike_force = ?, shinai_avg_strike_force = ?, max_tip_speed_mps = ?, max_kinetic_energy_joules = ? WHERE id = ?",
            (
                straightness, consistency, strike_count, max_g, avg_g,
                max_tip_speed, energy_j,
                session_id,
            ),
        )
        conn.commit()
    except Exception as e:
        LOG.error("Persist failed for session %s: %s", session_id, e)
        conn.close()
        return False
    conn.close()
    return True
