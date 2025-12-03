import math
import numpy as np
import logging

LOG = logging.getLogger("sensor_server.dual_analysis")


def calculate_shinai_strike_metrics(shinai_rows, threshold=2.0, min_dist_ms=200, window_ms=150):
    """
    Calculate per-strike metrics from shinai tip accel magnitudes.

    Returns summary: count, max_force_g, avg_force_g, avg_rms_g, avg_integral, avg_half_width_ms
    """
    from .analysis import detect_kendo_strikes
    if not shinai_rows:
        return {
            "shinai_strike_count": 0,
            "shinai_max_strike_force": 0.0,
            "shinai_avg_strike_force": 0.0,
            "shinai_avg_rms": 0.0,
            "shinai_avg_integral": 0.0,
            "shinai_avg_half_width_ms": 0.0,
        }

    # Ensure rows are list of [t, ax, ay, az, gx, gy, gz] or at least first 4 entries
    accel_rows = []
    for row in shinai_rows:
        try:
            t = float(row[0])
            ax = float(row[1])
            ay = float(row[2])
            az = float(row[3])
            mag = math.sqrt(ax*ax + ay*ay + az*az)
            accel_rows.append((t, mag))
        except Exception:
            continue

    if not accel_rows:
        return {
            "shinai_strike_count": 0,
            "shinai_max_strike_force": 0.0,
            "shinai_avg_strike_force": 0.0,
            "shinai_avg_rms": 0.0,
            "shinai_avg_integral": 0.0,
            "shinai_avg_half_width_ms": 0.0,
        }

    # Use detect_kendo_strikes to find primary peaks (it expects rows in accel format)
    # Convert accel_rows back to imu_rows format expected by detect_kendo_strikes
    imu_like = [[r[0], r[1], 0.0, 0.0, 0, 0, 0] for r in accel_rows]
    kstats = detect_kendo_strikes(imu_like, threshold=threshold, min_dist_ms=min_dist_ms)
    timestamps = kstats.get("strike_timestamps", [])

    per_peak_forces = []
    per_peak_rms = []
    per_peak_integrals = []
    per_peak_half_widths = []

    # Build fast access list
    times = [r[0] for r in accel_rows]
    mags = [r[1] for r in accel_rows]

    per_strike_list = []
    for ts in timestamps:
        start_t = ts - window_ms
        end_t = ts + window_ms
        # collect samples in window
        seg_times = []
        seg_mags = []
        for t, m in accel_rows:
            if t >= start_t and t <= end_t:
                seg_times.append(t)
                seg_mags.append(m)

        if not seg_mags:
            continue

        # Peak force (max magnitude in window)
        peak = max(seg_mags)
        per_peak_forces.append(peak)

        # RMS
        sq = [x*x for x in seg_mags]
        rms = math.sqrt(sum(sq) / len(sq)) if seg_mags else 0.0
        per_peak_rms.append(rms)

        # Integral (approximate area under mag curve). Use trapezoid rule with ms -> s
        integral = 0.0
        if len(seg_times) > 1:
            for i in range(1, len(seg_times)):
                dt = (seg_times[i] - seg_times[i-1]) / 1000.0
                integral += 0.5 * (seg_mags[i] + seg_mags[i-1]) * dt
        per_peak_integrals.append(integral)

        # Half-width: time between crossing half-peak before and after peak
        half = peak * 0.5
        # find index of peak in seg_mags
        try:
            peak_idx = seg_mags.index(peak)
        except ValueError:
            peak_idx = None

        half_left = None
        half_right = None
        if peak_idx is not None:
            # search left
            for i in range(peak_idx, -1, -1):
                if seg_mags[i] <= half:
                    half_left = seg_times[i]
                    break
            # search right
            for i in range(peak_idx, len(seg_mags)):
                if seg_mags[i] <= half:
                    half_right = seg_times[i]
                    break

        if half_left is not None and half_right is not None:
            half_width_ms = half_right - half_left
        else:
            half_width_ms = 0.0
        per_peak_half_widths.append(half_width_ms)

        # Peak timestamp
        peak_time = None
        if peak_idx is not None:
            try:
                peak_time = seg_times[peak_idx]
            except Exception:
                peak_time = ts

        per_strike_list.append({
            "t_ms": peak_time,
            "peak_g": peak,
            "rms_g": rms,
            "integral": integral,
            "half_width_ms": half_width_ms,
            "window_start": start_t,
            "window_end": end_t,
        })

    count = len(per_peak_forces)
    shinai_max = max(per_peak_forces) if per_peak_forces else 0.0
    shinai_avg = sum(per_peak_forces) / count if count else 0.0
    avg_rms = sum(per_peak_rms) / count if per_peak_rms else 0.0
    avg_integral = sum(per_peak_integrals) / count if per_peak_integrals else 0.0
    avg_half = sum(per_peak_half_widths) / count if per_peak_half_widths else 0.0

    return {
        "shinai_strike_count": count,
        "shinai_max_strike_force": shinai_max,
        "shinai_avg_strike_force": shinai_avg,
        "shinai_avg_rms": avg_rms,
        "shinai_avg_integral": avg_integral,
        "shinai_avg_half_width_ms": avg_half,
        "per_strikes": per_strike_list,
    }

def calculate_tip_speed(wrist_gyro, distance_inches):
    """
    Calculates the tip speed based on wrist angular velocity and distance.
    v = omega * r
    
    Args:
        wrist_gyro: List of [t, gx, gy, gz] (rad/s)
        distance_inches: Distance from wrist to tip (inches)
        
    Returns:
        float: Max tip speed (m/s)
    """
    distance_m = distance_inches * 0.0254
    max_speed = 0.0
    
    for row in wrist_gyro:
        try:
            gx = float(row[1])
            gy = float(row[2])
            gz = float(row[3])
            omega = math.sqrt(gx*gx + gy*gy + gz*gz)
            speed = omega * distance_m
            if speed > max_speed:
                max_speed = speed
        except (ValueError, IndexError):
            continue
            
    return max_speed

def calculate_kinetic_energy(velocity, mass_lbs):
    """
    Calculates kinetic energy.
    E = 0.5 * m * v^2
    
    Args:
        velocity: Speed (m/s)
        mass_lbs: Mass (lbs)
        
    Returns:
        float: Energy (Joules)
    """
    mass_kg = mass_lbs * 0.453592
    return 0.5 * mass_kg * (velocity ** 2)

def calculate_straightness(imu_rows):
    """
    Calculates straightness based on the variance of motion off the primary axis.
    We assume the primary axis of a strike is the one with the highest variance.
    
    The formula uses:
    - variance_major: The largest variance among the three acceleration axes (X, Y, Z)
    - variance_secondary: The second-largest variance among the three axes
    
    Straightness = 1.0 - (variance_secondary / variance_major)
    
    Args:
        imu_rows: List of [t, ax, ay, az, ...]
        
    Returns:
        float: Straightness score (0.0 to 1.0)
    """
    if not imu_rows or len(imu_rows) < 2:
        return 0.0
        
    accel_data = []
    for row in imu_rows:
        try:
            accel_data.append([float(row[1]), float(row[2]), float(row[3])])
        except (ValueError, IndexError):
            continue
            
    if not accel_data:
        return 0.0
        
    data = np.array(accel_data)
    variances = np.var(data, axis=0)
    sorted_vars = np.sort(variances)
    
    major_var = sorted_vars[-1]
    secondary_var = sorted_vars[-2]  # Second-largest variance among X, Y, Z
    
    if major_var == 0:
        return 0.0
        
    # If perfect straight line, secondary_var is 0 -> score 1.0
    # If chaotic, secondary_var approaches major_var -> score 0.0
    return 1.0 - (secondary_var / major_var)

def calculate_consistency(wrist_rows, shinai_rows):
    """
    Calculates consistency between multiple separate strikes.
    Segments the shinai data based on detected strikes and compares consecutive strikes.
    
    Args:
        wrist_rows: List of [t, ax, ay, az, ...] (Unused in this new metric but kept for signature compatibility)
        shinai_rows: List of [t, ax, ay, az, ...]
        
    Returns:
        float: Consistency score (average correlation between consecutive strikes, -1.0 to 1.0)
    """
    from .analysis import detect_kendo_strikes
    
    # 1. Detect strikes to find timestamps
    kendo_stats = detect_kendo_strikes(shinai_rows)
    timestamps = kendo_stats.get("strike_timestamps", [])
    
    if len(timestamps) < 2:
        return 0.0
        
    # 2. Segment data around strikes
    segments = []
    window_ms = 200 # +/- 200ms
    
    # Convert rows to a more accessible format (dict by timestamp or just search)
    # Since rows are sorted by time, we can search efficiently or just iterate
    # For simplicity, let's just iterate for each strike (O(N*M) but N is small)
    
    for ts in timestamps:
        start_t = ts - window_ms
        end_t = ts + window_ms
        
        segment_mags = []
        for row in shinai_rows:
            try:
                t = float(row[0])
                if t >= start_t and t <= end_t:
                    mag = math.sqrt(float(row[1])**2 + float(row[2])**2 + float(row[3])**2)
                    segment_mags.append(mag)
            except (ValueError, IndexError):
                continue
        
        # Normalize segment length (resample to fixed size, e.g., 50 samples)
        if segment_mags:
            # Simple resampling: linear interpolation to 50 points
            target_len = 50
            if len(segment_mags) > 1:
                x_old = np.linspace(0, 1, len(segment_mags))
                x_new = np.linspace(0, 1, target_len)
                resampled = np.interp(x_new, x_old, segment_mags)
                segments.append(resampled)
    
    if len(segments) < 2:
        return 0.0
        
    # 3. Calculate correlation between consecutive segments
    correlations = []
    for i in range(len(segments) - 1):
        s1 = segments[i]
        s2 = segments[i+1]
        corr = np.corrcoef(s1, s2)[0, 1]
        if not np.isnan(corr):
            correlations.append(corr)
            
    if not correlations:
        return 0.0
        
    return sum(correlations) / len(correlations)

def analyze_dual_session(wear_data, shinai_data, params):
    """
    Orchestrates the dual-device analysis.
    
    Args:
        wear_data: Dict containing 'imu' list for wrist
        shinai_data: Dict containing 'imu' list for shinai
        params: Dict with 'distance_inches' and 'sword_weight_lbs'
        
    Returns:
        dict: Analysis report
    """
    # Guard against None values in params
    try:
        distance = float(params.get("distance_inches") or 0)
    except Exception:
        distance = 0.0
    try:
        weight = float(params.get("sword_weight_lbs") or 0)
    except Exception:
        weight = 0.0
    
    wrist_imu = wear_data.get("imu", [])
    shinai_imu = shinai_data.get("imu", [])
    
    # Extract gyro for speed calc
    wrist_gyro = []
    for row in wrist_imu:
        if isinstance(row, dict):
             wrist_gyro.append([row.get("t"), row.get("gx"), row.get("gy"), row.get("gz")])
        elif isinstance(row, list) and len(row) >= 7:
             wrist_gyro.append([row[0], row[4], row[5], row[6]])

    # Extract accel for straightness/consistency
    wrist_accel_rows = []
    for row in wrist_imu:
        if isinstance(row, dict):
            wrist_accel_rows.append([row.get("t"), row.get("ax"), row.get("ay"), row.get("az")])
        elif isinstance(row, list) and len(row) >= 4:
            wrist_accel_rows.append(row[:4])  # Extract only [t, ax, ay, az]

    shinai_accel_rows = []
    for row in shinai_imu:
        if isinstance(row, dict):
            shinai_accel_rows.append([row.get("t"), row.get("ax"), row.get("ay"), row.get("az")])
        elif isinstance(row, list) and len(row) >= 4:
            shinai_accel_rows.append(row[:4])  # Extract only [t, ax, ay, az]

    # Calculate Metrics
    max_tip_speed = calculate_tip_speed(wrist_gyro, distance)
    max_kinetic_energy = calculate_kinetic_energy(max_tip_speed, weight)
    straightness = calculate_straightness(shinai_accel_rows)
    consistency = calculate_consistency(wrist_accel_rows, shinai_accel_rows)
    # Strike metrics from shinai tip
    strike_metrics = calculate_shinai_strike_metrics(shinai_accel_rows)
    
    return {
        "max_tip_speed_mps": max_tip_speed,
        "max_kinetic_energy_joules": max_kinetic_energy,
        "straightness_score": straightness,
        "consistency_score": consistency,
        # Add shinai-derived strike metrics
        "shinai_strike_count": strike_metrics.get("shinai_strike_count"),
        "shinai_max_strike_force": strike_metrics.get("shinai_max_strike_force"),
        "shinai_avg_strike_force": strike_metrics.get("shinai_avg_strike_force"),
        "shinai_avg_rms": strike_metrics.get("shinai_avg_rms"),
        "shinai_avg_integral": strike_metrics.get("shinai_avg_integral"),
        "shinai_avg_half_width_ms": strike_metrics.get("shinai_avg_half_width_ms"),
        "per_strikes": strike_metrics.get("per_strikes"),
    }
    
