import math
import logging

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
    for row in imu_rows:
        # row format: [t, ax, ay, az, gx, gy, gz]
        try:
            ax = float(row[1])
            ay = float(row[2])
            az = float(row[3])
            magnitude = math.sqrt(ax * ax + ay * ay + az * az)
            intensities.append(magnitude)
        except (ValueError, IndexError):
            continue

    if not intensities:
        return {"wrist_activity_mean_g": 0.0, "wrist_activity_max_g": 0.0}

    mean_g = sum(intensities) / len(intensities)
    max_g = max(intensities)

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

    report_lines.append(f"[Movement & Kendo Summary]")
    if imu_rows:
        activity = calculate_movement_intensity(imu_rows)
        mean_g = activity.get("wrist_activity_mean_g", 0.0)
        max_g = activity.get("wrist_activity_max_g", 0.0)
        report_lines.append(f"Wrist activity (mean): {mean_g:.2f} G")
        report_lines.append(f"Wrist activity (max):  {max_g:.2f} G")

        # Kendo Stats (wrist provides strike count/timestamps only)
        kendo_stats = detect_kendo_strikes(imu_rows)
        strike_count = kendo_stats.get("strike_count", 0)
        timestamps = kendo_stats.get("strike_timestamps", [])
        report_lines.append(f"Kendo Strikes (wrist): {strike_count}")

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
        metrics["strike_count"] = kendo_stats.get("strike_count", 0)
        metrics["max_strike_force"] = 0.0
        metrics["avg_strike_force"] = 0.0

    return metrics


def detect_kendo_strikes(imu_rows, threshold=2.0, min_dist_ms=200):
    """
    Detects sword strikes based on accelerometer peaks.

    Args:
        imu_rows: List of [t, ax, ay, az, gx, gy, gz]
        threshold: Acceleration magnitude threshold (G) to count as a strike.
        min_dist_ms: Minimum time (ms) between strikes to avoid double counting.

    Returns:
        dict: {
            "strike_count": int,
            "max_strike_force": float,
            "avg_strike_force": float,
            "strike_timestamps": list[float]
        }
    """
    strikes = []  # List of (timestamp, magnitude)
    last_strike_time = -min_dist_ms

    for row in imu_rows:
        try:
            t = float(row[0])
            ax = float(row[1])
            ay = float(row[2])
            az = float(row[3])
            magnitude = math.sqrt(ax * ax + ay * ay + az * az)

            if magnitude > threshold:
                if (t - last_strike_time) > min_dist_ms:
                    strikes.append((t, magnitude))
                    last_strike_time = t
                else:
                    # If within window, check if this peak is higher (update the strike)
                    if strikes and magnitude > strikes[-1][1]:
                        strikes[-1] = (t, magnitude)
                        last_strike_time = t  # Update time to the peak
        except (ValueError, IndexError):
            continue

    count = len(strikes)
    max_force = max([s[1] for s in strikes]) if strikes else 0.0
    avg_force = sum([s[1] for s in strikes]) / count if strikes else 0.0

    return {
        "strike_count": count,
        "max_strike_force": max_force,
        "avg_strike_force": avg_force,
        "strike_timestamps": [s[0] for s in strikes],
    }
