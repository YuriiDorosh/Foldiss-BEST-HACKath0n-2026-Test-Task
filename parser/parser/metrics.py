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
    }
