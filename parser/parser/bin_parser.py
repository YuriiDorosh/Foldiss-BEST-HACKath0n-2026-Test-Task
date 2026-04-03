"""
ArduPilot .BIN log parser using pymavlink.

Extracts GPS and IMU records with the following filters:
  GPS: instance index I == 0 (primary receiver) AND Status >= 3 (3D fix minimum)
  IMU: instance index I == 0 (primary sensor)

ArduPilot GPS Status values:
  0 = No GPS
  1 = No Fix
  2 = 2D Fix
  3 = 3D Fix          ← minimum accepted
  4 = DGPS
  6 = 3D DGPS         ← typical SITL/RTK value
"""

import logging
import os

from pymavlink import mavutil

_logger = logging.getLogger(__name__)


def parse_bin(file_path: str) -> tuple[list[dict], list[dict]]:
    """Parse an ArduPilot binary .BIN log file.

    Args:
        file_path: Absolute path to the .BIN file on disk.

    Returns:
        (gps_records, imu_records) — lists of dicts with relevant fields.

    Raises:
        FileNotFoundError: If file_path does not exist.
        RuntimeError: If the file cannot be opened as a MAVLink log.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"BIN file not found: {file_path}")

    _logger.info(
        "Opening BIN log: %s  (size: %.1f KB)",
        file_path,
        os.path.getsize(file_path) / 1024,
    )

    try:
        mlog = mavutil.mavlink_connection(file_path, dialect="ardupilotmega")
    except Exception as exc:
        raise RuntimeError(f"Failed to open BIN file: {exc}") from exc

    gps_records: list[dict] = []
    imu_records: list[dict] = []

    while True:
        msg = mlog.recv_match(type=["GPS", "IMU"])
        if msg is None:
            break

        msg_type = msg.get_type()
        d = msg.to_dict()

        if msg_type == "GPS":
            # Primary receiver only; require at least a 3D fix
            if d.get("I", 1) != 0:
                continue
            if d.get("Status", 0) < 3:
                continue

            gps_records.append(
                {
                    "TimeUS": d["TimeUS"],
                    "Lat": d["Lat"],
                    "Lng": d["Lng"],
                    "Alt": d["Alt"],
                    "Spd": d["Spd"],
                    "Status": d["Status"],
                }
            )

        elif msg_type == "IMU":
            # Primary sensor only
            if d.get("I", 1) != 0:
                continue

            imu_records.append(
                {
                    "TimeUS": d["TimeUS"],
                    "AccX": d["AccX"],
                    "AccY": d["AccY"],
                    "AccZ": d["AccZ"],
                }
            )

    _logger.info(
        "Parsed %d GPS records (valid fix) and %d IMU records",
        len(gps_records),
        len(imu_records),
    )
    return gps_records, imu_records


def write_temp_bin(data: bytes, mission_id: int) -> str:
    """Write raw .BIN bytes to a temporary file and return the path."""
    tmp_dir = "/tmp/uav_logs"
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, f"mission_{mission_id}.bin")
    with open(path, "wb") as f:
        f.write(data)
    _logger.info("Wrote %d bytes to %s", len(data), path)
    return path
