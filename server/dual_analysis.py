import math
import numpy as np
import logging

LOG = logging.getLogger("sensor_server.dual_analysis")

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
    distance = float(params.get("distance_inches", 0))
    weight = float(params.get("sword_weight_lbs", 0))
    
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
            wrist_accel_rows.append(row) # Assuming list format matches

    shinai_accel_rows = []
    for row in shinai_imu:
        if isinstance(row, dict):
            shinai_accel_rows.append([row.get("t"), row.get("ax"), row.get("ay"), row.get("az")])
        elif isinstance(row, list) and len(row) >= 4:
            shinai_accel_rows.append(row)

    # Calculate Metrics
    max_tip_speed = calculate_tip_speed(wrist_gyro, distance)
    max_kinetic_energy = calculate_kinetic_energy(max_tip_speed, weight)
    straightness = calculate_straightness(shinai_accel_rows)
    consistency = calculate_consistency(wrist_accel_rows, shinai_accel_rows)
    
    return {
        "max_tip_speed_mps": max_tip_speed,
        "max_kinetic_energy_joules": max_kinetic_energy,
        "straightness_score": straightness,
        "consistency_score": consistency
    }
