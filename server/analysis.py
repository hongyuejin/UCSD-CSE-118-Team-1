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
        "Peak (>150)": 0
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
    Calculates statistics on movement intensity using accelerometer vector magnitude.
    """
    if not imu_rows:
        return {"avg_intensity": 0.0, "max_intensity": 0.0}

    intensities = []
    for row in imu_rows:
        # row format: [t, ax, ay, az, gx, gy, gz]
        # We use ax, ay, az which are at indices 1, 2, 3
        try:
            ax = float(row[1])
            ay = float(row[2])
            az = float(row[3])
            magnitude = math.sqrt(ax*ax + ay*ay + az*az)
            intensities.append(magnitude)
        except (ValueError, IndexError):
            continue

    if not intensities:
        return {"avg_intensity": 0.0, "max_intensity": 0.0}

    avg_intensity = sum(intensities) / len(intensities)
    max_intensity = max(intensities)

    return {"avg_intensity": avg_intensity, "max_intensity": max_intensity}

def analyze_session(payload):
    """
    Orchestrates the analysis. Extracts data from the payload, calls calculation functions,
    and prints a formatted report to the console.
    """
    report_lines = []
    report_lines.append("\n" + "="*40)
    report_lines.append("       SESSION ANALYSIS REPORT       ")
    report_lines.append("="*40)

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
                # Skip invalid heart rate values that cannot be converted to float
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
    
    report_lines.append(f"\n[Movement & Kendo Analysis]")
    if imu_rows:
        intensity_stats = calculate_movement_intensity(imu_rows)
        report_lines.append(f"Average Intensity: {intensity_stats['avg_intensity']:.2f} G")
        report_lines.append(f"Max Intensity:     {intensity_stats['max_intensity']:.2f} G")

        # Kendo Stats
        kendo_stats = detect_kendo_strikes(imu_rows)
        report_lines.append(f"Kendo Strikes:     {kendo_stats['strike_count']}")
        report_lines.append(f"Max Strike Force:  {kendo_stats['max_strike_force']:.2f} G")
        report_lines.append(f"Avg Strike Force:  {kendo_stats['avg_strike_force']:.2f} G")
    else:
        report_lines.append("No IMU data available.")

    report_lines.append("\n" + "="*40 + "\n")
    
    print("\n".join(report_lines))

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
            "avg_strike_force": float
        }
    """
    strikes = []
    last_strike_time = -min_dist_ms
    
    for row in imu_rows:
        try:
            t = float(row[0])
            ax = float(row[1])
            ay = float(row[2])
            az = float(row[3])
            magnitude = math.sqrt(ax*ax + ay*ay + az*az)
            
            if magnitude > threshold:
                if (t - last_strike_time) > min_dist_ms:
                    strikes.append(magnitude)
                    last_strike_time = t
                else:
                    # If within window, check if this peak is higher (update the strike)
                    if strikes and magnitude > strikes[-1]:
                        strikes[-1] = magnitude
        except (ValueError, IndexError):
            continue
            
    count = len(strikes)
    max_force = max(strikes) if strikes else 0.0
    avg_force = sum(strikes) / count if strikes else 0.0
    
    return {
        "strike_count": count,
        "max_strike_force": max_force,
        "avg_strike_force": avg_force
    }

