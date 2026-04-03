"""
Flight telemetry metric computation.

All three mandatory algorithms are implemented here:
  1. haversine()      — great-circle distance between GPS fixes
  2. trapz_velocity() — trapezoidal integration of IMU acceleration → velocity
  3. wgs84_to_enu()   — WGS-84 geodetic coordinates → local ENU (East-North-Up)
"""

import math

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 1. Haversine distance
# ─────────────────────────────────────────────────────────────────────────────


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points.

    Formula:
        a = sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)
        c = 2 · atan2(√a, √(1−a))
        d = R · c

    Args:
        lat1, lon1: Start point in decimal degrees.
        lat2, lon2: End point in decimal degrees.

    Returns:
        Distance in metres.
    """
    R = 6_371_000.0  # Mean Earth radius in metres

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ─────────────────────────────────────────────────────────────────────────────
# 2. Trapezoidal integration: acceleration → velocity
# ─────────────────────────────────────────────────────────────────────────────


def trapz_velocity(acc_z: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    """Compute vertical velocity by trapezoidal integration of IMU AccZ.

    Why AccZ?
        AccX/AccY contain horizontal body-frame accelerations mixed with
        centripetal and Coriolis terms. Without a full attitude matrix
        rotation, they cannot be cleanly integrated into world-frame velocity.
        AccZ — after mean-subtraction to remove the ~9.81 m/s² gravity bias —
        approximates the vertical (Up) acceleration in the near-inertial frame
        over short flight durations.

    Gravity removal:
        At rest, AccZ ≈ −9.81 m/s² (or +9.81 depending on IMU orientation).
        Subtracting the time-average removes this DC bias, leaving only the
        dynamic component due to actual vertical motion.

    Trapezoidal rule (explicit loop — shows the algorithm clearly for review):
        v[i] = v[i-1] + 0.5 · (a[i-1] + a[i]) · Δt

    Args:
        acc_z:  Array of vertical accelerations [m/s²], shape (N,).
        time_s: Corresponding timestamps in seconds, shape (N,).

    Returns:
        Vertical velocity array [m/s], shape (N,), starting at 0.
    """
    acc_debiased = acc_z - np.mean(acc_z)  # remove gravity + DC offset

    vel_z = np.zeros(len(time_s), dtype=np.float64)
    for i in range(1, len(time_s)):
        dt = time_s[i] - time_s[i - 1]
        vel_z[i] = vel_z[i - 1] + 0.5 * (acc_debiased[i - 1] + acc_debiased[i]) * dt

    return vel_z


# ─────────────────────────────────────────────────────────────────────────────
# 3. WGS-84 → ENU coordinate conversion
# ─────────────────────────────────────────────────────────────────────────────


def wgs84_to_enu(
    lat: float,
    lon: float,
    alt: float,
    lat0: float,
    lon0: float,
    alt0: float,
) -> tuple[float, float, float]:
    """Convert a WGS-84 geodetic point to local ENU (East-North-Up) metres.

    Origin (0, 0, 0) ENU = first valid GPS fix of the mission.

    Approximation (valid for distances < 50 km, error < 0.1 %):
        East  = R · Δλ · cos(φ₀)
        North = R · Δφ
        Up    = Δh

    where R = 6 378 137.0 m (WGS-84 semi-major axis) and
    φ₀ is the origin latitude.

    Args:
        lat, lon, alt: Target point (degrees, degrees, metres MSL).
        lat0, lon0, alt0: Origin point (first GPS fix).

    Returns:
        (east, north, up) in metres.
    """
    R = 6_378_137.0  # WGS-84 semi-major axis in metres

    east = R * math.radians(lon - lon0) * math.cos(math.radians(lat0))
    north = R * math.radians(lat - lat0)
    up = alt - alt0

    return east, north, up


# ─────────────────────────────────────────────────────────────────────────────
# Master metric computation
# ─────────────────────────────────────────────────────────────────────────────


def compute_all_metrics(
    gps: list[dict],
    imu: list[dict],
) -> dict:
    """Compute all mission metrics from parsed GPS and IMU records.

    Args:
        gps: List of dicts with keys TimeUS, Lat, Lng, Alt, Spd.
             Already filtered: Status >= 3, I == 0.
        imu: List of dicts with keys TimeUS, AccX, AccY, AccZ.
             Already filtered: I == 0.

    Returns:
        Dict with scalar metrics + serialisable trajectory lists.

    Raises:
        ValueError: If gps or imu lists are empty.
    """
    if not gps:
        raise ValueError("No valid GPS records (Status >= 3) found in log.")
    if not imu:
        raise ValueError("No IMU records found in log.")

    # ── GPS arrays ───────────────────────────────────────────────────────────
    times_gps = np.array([r["TimeUS"] / 1e6 for r in gps])  # seconds
    lats = np.array([r["Lat"] for r in gps])
    lngs = np.array([r["Lng"] for r in gps])
    alts = np.array([r["Alt"] for r in gps])
    spds = np.array([r["Spd"] for r in gps])

    # ── IMU arrays ───────────────────────────────────────────────────────────
    times_imu = np.array([r["TimeUS"] / 1e6 for r in imu])  # seconds
    acc_x = np.array([r["AccX"] for r in imu])
    acc_y = np.array([r["AccY"] for r in imu])
    acc_z = np.array([r["AccZ"] for r in imu])

    # ── 1. Total distance (haversine) ─────────────────────────────────────
    total_distance = sum(
        haversine(lats[i], lngs[i], lats[i + 1], lngs[i + 1])
        for i in range(len(lats) - 1)
    )

    # ── 2. Max horizontal speed (from GPS Spd field) ──────────────────────
    max_h_speed = float(np.max(spds))

    # ── 3. Max vertical speed (trapezoidal integration of IMU AccZ) ───────
    vel_z = trapz_velocity(acc_z, times_imu)
    max_v_speed = float(np.max(np.abs(vel_z)))

    # ── 4. Max acceleration magnitude (gravity removed) ───────────────────
    #   Net acceleration = sqrt(ax²+ay²+az²); subtract gravity magnitude
    #   so the metric reflects dynamic loading only.
    acc_magnitude = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
    gravity = 9.80665  # m/s²
    max_acceleration = float(np.max(np.abs(acc_magnitude - gravity)))

    # ── 5. Max altitude gain ──────────────────────────────────────────────
    max_altitude_gain = float(np.max(alts) - np.min(alts))

    # ── 6. Flight duration ────────────────────────────────────────────────
    flight_duration = float(times_gps[-1] - times_gps[0])

    # ── 7. Sample rates ───────────────────────────────────────────────────
    gps_sample_rate = float(len(gps) / flight_duration) if flight_duration > 0 else 0.0
    imu_duration = float(times_imu[-1] - times_imu[0])
    imu_sample_rate = float(len(imu) / imu_duration) if imu_duration > 0 else 0.0

    # ── 8. WGS-84 → ENU trajectory ───────────────────────────────────────
    lat0, lon0, alt0 = float(lats[0]), float(lngs[0]), float(alts[0])
    enu_points = []
    for lat, lon, alt in zip(lats.tolist(), lngs.tolist(), alts.tolist()):
        e, n, u = wgs84_to_enu(lat, lon, alt, lat0, lon0, alt0)
        enu_points.append(
            {
                "east": round(e, 3),
                "north": round(n, 3),
                "up": round(u, 3),
            }
        )

    gps_points = [
        {
            "t": round(float(t), 3),
            "lat": round(float(lat), 7),
            "lng": round(float(lng), 7),
            "alt": round(float(alt), 3),
            "spd": round(float(spd), 3),
        }
        for t, lat, lng, alt, spd in zip(times_gps, lats, lngs, alts, spds)
    ]

    # ── Integrity check ────────────────────────────────────────────────────
    assert len(gps_points) == len(enu_points), (
        f"gps_points ({len(gps_points)}) and enu_points ({len(enu_points)}) "
        "must have equal length"
    )

    # ── IMU data (for viewer charts) ──────────────────────────────────────
    imu_data = {
        "times": [round(float(t), 4) for t in times_imu],
        "vel_z": [round(float(v), 4) for v in vel_z],
        "acc_magnitude": [round(float(a), 4) for a in acc_magnitude],
    }

    # ── 9. FLIGHT ANALYTICS ─────────────────────────────────────────────────
    analytics = _compute_analytics(
        times_gps, lats, lngs, alts, spds,
        times_imu, acc_x, acc_y, acc_z, acc_magnitude, vel_z,
        enu_points, total_distance, flight_duration,
    )

    return {
        # Scalar metrics
        "total_distance": round(total_distance, 2),
        "max_h_speed": round(max_h_speed, 3),
        "max_v_speed": round(max_v_speed, 3),
        "max_acceleration": round(max_acceleration, 3),
        "max_altitude_gain": round(max_altitude_gain, 2),
        "flight_duration": round(flight_duration, 2),
        "gps_count": len(gps),
        "imu_count": len(imu),
        "gps_sample_rate": round(gps_sample_rate, 2),
        "imu_sample_rate": round(imu_sample_rate, 2),
        # Trajectory arrays (serialise to JSON before storing in Odoo)
        "gps_points": gps_points,
        "enu_points": enu_points,
        "imu_data": imu_data,
        # Flight analytics
        "analytics": analytics,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Flight analytics
# ─────────────────────────────────────────────────────────────────────────────

HOVER_SPEED_THRESHOLD = 0.5   # m/s — below this is considered hover
PHASE_MIN_DURATION = 2.0      # seconds — ignore phases shorter than this


def _compute_analytics(
    times_gps, lats, lngs, alts, spds,
    times_imu, acc_x, acc_y, acc_z, acc_magnitude, vel_z,
    enu_points, total_distance, flight_duration,
):
    """Compute rich flight analytics from raw telemetry arrays."""
    analytics = {}

    # ── Path efficiency ─────────────────────────────────────────────────────
    # Straight-line distance (start → end) vs total distance flown
    straight_line = haversine(
        float(lats[0]), float(lngs[0]),
        float(lats[-1]), float(lngs[-1]),
    )
    analytics["path_efficiency"] = round(
        straight_line / total_distance * 100 if total_distance > 0 else 0, 1
    )
    analytics["straight_line_distance"] = round(straight_line, 2)

    # ── Average speed ───────────────────────────────────────────────────────
    analytics["avg_speed"] = round(
        total_distance / flight_duration if flight_duration > 0 else 0, 2
    )

    # ── Climb / descent rates ───────────────────────────────────────────────
    alt_diffs = np.diff(alts)
    time_diffs_gps = np.diff(times_gps)
    time_diffs_gps[time_diffs_gps == 0] = 0.001  # avoid div by zero
    climb_rates = alt_diffs / time_diffs_gps
    analytics["max_climb_rate"] = round(float(np.max(climb_rates)), 2)
    analytics["max_descent_rate"] = round(float(np.abs(np.min(climb_rates))), 2)
    analytics["avg_altitude"] = round(float(np.mean(alts)), 1)

    # ── Flight phases ───────────────────────────────────────────────────────
    # Segment flight into: takeoff, climb, cruise, hover, descent, landing
    phases = []
    hover_time = 0.0
    climb_time = 0.0
    descent_time = 0.0
    cruise_time = 0.0

    for i in range(len(spds)):
        dt = float(time_diffs_gps[i]) if i < len(time_diffs_gps) else 0
        speed = float(spds[i])
        climb_rate = float(climb_rates[i]) if i < len(climb_rates) else 0

        if speed < HOVER_SPEED_THRESHOLD:
            hover_time += dt
        elif climb_rate > 0.5:
            climb_time += dt
        elif climb_rate < -0.5:
            descent_time += dt
        else:
            cruise_time += dt

    analytics["hover_time"] = round(hover_time, 1)
    analytics["cruise_time"] = round(cruise_time, 1)
    analytics["climb_time"] = round(climb_time, 1)
    analytics["descent_time"] = round(descent_time, 1)
    analytics["hover_ratio"] = round(
        hover_time / flight_duration * 100 if flight_duration > 0 else 0, 1
    )

    # ── Speed distribution (histogram buckets) ──────────────────────────────
    speed_buckets = {
        "0-2 m/s": 0, "2-5 m/s": 0, "5-10 m/s": 0,
        "10-20 m/s": 0, "20+ m/s": 0,
    }
    for i, s in enumerate(spds):
        dt = float(time_diffs_gps[i]) if i < len(time_diffs_gps) else 0
        sf = float(s)
        if sf < 2:
            speed_buckets["0-2 m/s"] += dt
        elif sf < 5:
            speed_buckets["2-5 m/s"] += dt
        elif sf < 10:
            speed_buckets["5-10 m/s"] += dt
        elif sf < 20:
            speed_buckets["10-20 m/s"] += dt
        else:
            speed_buckets["20+ m/s"] += dt
    # Convert to percentage
    analytics["speed_distribution"] = {
        k: round(v / flight_duration * 100 if flight_duration > 0 else 0, 1)
        for k, v in speed_buckets.items()
    }

    # ── Vibration analysis (IMU) ────────────────────────────────────────────
    # RMS of acceleration deviation from gravity — high values = vibration
    gravity = 9.80665
    acc_deviation = acc_magnitude - gravity
    vibration_rms = float(np.sqrt(np.mean(acc_deviation ** 2)))
    analytics["vibration_rms"] = round(vibration_rms, 3)

    # Vibration level classification
    if vibration_rms < 1.0:
        analytics["vibration_level"] = "LOW"
    elif vibration_rms < 3.0:
        analytics["vibration_level"] = "MEDIUM"
    else:
        analytics["vibration_level"] = "HIGH"

    # Per-axis vibration RMS
    analytics["vibration_x"] = round(float(np.std(acc_x)), 3)
    analytics["vibration_y"] = round(float(np.std(acc_y)), 3)
    analytics["vibration_z"] = round(float(np.std(acc_z)), 3)

    # ── Heading / turn analysis ─────────────────────────────────────────────
    # Compute heading from consecutive GPS points and count significant turns
    headings = []
    for i in range(1, len(lats)):
        dlng = float(lngs[i] - lngs[i - 1])
        dlat = float(lats[i] - lats[i - 1])
        heading = math.degrees(math.atan2(dlng, dlat)) % 360
        headings.append(heading)

    turn_count = 0
    total_heading_change = 0.0
    for i in range(1, len(headings)):
        delta = abs(headings[i] - headings[i - 1])
        if delta > 180:
            delta = 360 - delta
        total_heading_change += delta
        if delta > 15:  # significant turn > 15 degrees between GPS fixes
            turn_count += 1

    analytics["turn_count"] = turn_count
    analytics["total_heading_change"] = round(total_heading_change, 1)

    # ── GPS anomaly detection ───────────────────────────────────────────────
    # Detect GPS jumps — unrealistic distance between consecutive fixes
    gps_jumps = 0
    max_jump = 0.0
    for i in range(len(lats) - 1):
        dt = float(time_diffs_gps[i])
        if dt <= 0:
            continue
        dist = haversine(float(lats[i]), float(lngs[i]),
                         float(lats[i + 1]), float(lngs[i + 1]))
        implied_speed = dist / dt
        if implied_speed > 50:  # > 50 m/s = 180 km/h — likely GPS glitch
            gps_jumps += 1
            max_jump = max(max_jump, dist)

    analytics["gps_jumps"] = gps_jumps
    analytics["max_gps_jump"] = round(max_jump, 2)

    # ── Acceleration spike detection ────────────────────────────────────────
    acc_spike_threshold = 15.0  # m/s² above gravity
    acc_spikes = int(np.sum(np.abs(acc_deviation) > acc_spike_threshold))
    analytics["acceleration_spikes"] = acc_spikes

    # ── Altitude profile (sampled for chart) ────────────────────────────────
    # Downsample to ~100 points for the chart
    n_points = min(100, len(alts))
    indices = np.linspace(0, len(alts) - 1, n_points, dtype=int)
    analytics["altitude_profile"] = {
        "times": [round(float(times_gps[i] - times_gps[0]), 1) for i in indices],
        "altitudes": [round(float(alts[i]), 1) for i in indices],
    }

    # ── Speed profile (sampled for chart) ───────────────────────────────────
    analytics["speed_profile"] = {
        "times": [round(float(times_gps[i] - times_gps[0]), 1) for i in indices],
        "speeds": [round(float(spds[i]), 2) for i in indices],
    }

    return analytics
