/**
 * Odoo API helpers.
 *
 * All endpoints are served by foldiss_uav/controllers/main.py.
 *
 * VITE_ODOO_URL  — base URL of the Odoo instance (injected at build time
 *                  or proxied by Vite dev server).
 */

const BASE = import.meta.env.VITE_ODOO_URL || "";

/**
 * Poll the current status of a mission.
 * GET /uav/api/mission/<id>
 * Returns: { id, status, error_message }
 */
export async function fetchMissionStatus(missionId) {
  const res = await fetch(`${BASE}/uav/api/mission/${missionId}`);
  if (!res.ok) throw new Error(`Status poll failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch the full trajectory + metrics + AI conclusion for a mission.
 * GET /uav/api/mission/<id>/trajectory
 * Returns: {
 *   gps_points, enu_points, imu_data,
 *   total_distance, max_h_speed, max_v_speed,
 *   max_acceleration, max_altitude_gain, flight_duration,
 *   gps_count, imu_count, gps_sample_rate, imu_sample_rate,
 *   ai_conclusion, ai_status
 * }
 */
export async function fetchMissionData(missionId) {
  const res = await fetch(`${BASE}/uav/api/mission/${missionId}/trajectory`);
  if (!res.ok) throw new Error(`Trajectory fetch failed: ${res.status}`);
  return res.json();
}
