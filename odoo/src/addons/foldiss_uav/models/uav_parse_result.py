from odoo import fields, models


class UavParseResult(models.Model):
    """Stores all computed artefacts from parsing one ArduPilot .BIN log file.

    Scalar metrics (floats/ints) are stored as proper columns so Odoo views
    and related fields can display them.  Large trajectory arrays are stored as
    JSON text to avoid column-count bloat.
    """

    _name = "uav.parse.result"
    _description = "UAV Parse Result"

    # ── Relation ─────────────────────────────────────────────────────────────
    mission_id = fields.Many2one(
        comodel_name="uav.mission",
        string="Mission",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # ── Scalar metrics ───────────────────────────────────────────────────────
    total_distance = fields.Float(
        string="Total Distance (m)",
        digits=(16, 2),
        help="Sum of haversine distances between consecutive GPS fixes.",
    )
    max_h_speed = fields.Float(
        string="Max Horizontal Speed (m/s)",
        digits=(16, 3),
        help="Maximum ground speed from the GPS Spd field.",
    )
    max_v_speed = fields.Float(
        string="Max Vertical Speed (m/s)",
        digits=(16, 3),
        help="Maximum |velocity| derived by trapezoidal integration of IMU AccZ.",
    )
    max_acceleration = fields.Float(
        string="Max Acceleration (m/s²)",
        digits=(16, 3),
        help="Maximum net acceleration magnitude from IMU (gravity removed).",
    )
    max_altitude_gain = fields.Float(
        string="Max Altitude Gain (m)",
        digits=(16, 2),
        help="max(Alt) − min(Alt) over all valid GPS fixes.",
    )
    flight_duration = fields.Float(
        string="Flight Duration (s)",
        digits=(16, 2),
        help="(last_TimeUS − first_TimeUS) / 1e6 over valid GPS fixes.",
    )
    gps_count = fields.Integer(string="GPS Points")
    imu_count = fields.Integer(string="IMU Samples")
    gps_sample_rate = fields.Float(
        string="GPS Sample Rate (Hz)",
        digits=(16, 2),
    )
    imu_sample_rate = fields.Float(
        string="IMU Sample Rate (Hz)",
        digits=(16, 2),
    )

    # ── Trajectory JSON ──────────────────────────────────────────────────────
    gps_points = fields.Text(
        string="GPS Points (JSON)",
        help="List of {t, lat, lng, alt, spd} dicts for every valid GPS fix.",
    )
    enu_points = fields.Text(
        string="ENU Points (JSON)",
        help="List of {east, north, up} dicts in metres from the first GPS fix. "
        "Computed via WGS-84 → ENU conversion.",
    )
    imu_data = fields.Text(
        string="IMU Data (JSON)",
        help="Dict with keys: times, vel_z (trapz-integrated), acc_magnitude.",
    )
    analytics = fields.Text(
        string="Flight Analytics (JSON)",
        help="Computed flight analytics: phases, vibration, path efficiency, etc.",
    )
