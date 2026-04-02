/**
 * MetricsPanel — displays all scalar flight metrics in a grid of cards,
 * plus IMU charts (vertical velocity and acceleration magnitude over time).
 *
 * Props:
 *   metrics  {object}  — flat dict of scalar values from the API
 *   imuData  {object}  — { times, vel_z, acc_magnitude }
 */

import React, { useMemo } from "react";
import Plot from "react-plotly.js";

// ── Metric card definitions ───────────────────────────────────────────────────
const CARD_DEFS = [
  { key: "total_distance",    label: "Total Distance",      unit: "m",   decimals: 1 },
  { key: "max_h_speed",       label: "Max Horiz. Speed",    unit: "m/s", decimals: 2 },
  { key: "max_v_speed",       label: "Max Vert. Speed",     unit: "m/s", decimals: 2 },
  { key: "max_acceleration",  label: "Max Acceleration",    unit: "m/s²",decimals: 2 },
  { key: "max_altitude_gain", label: "Max Altitude Gain",   unit: "m",   decimals: 1 },
  { key: "flight_duration",   label: "Flight Duration",     unit: "s",   decimals: 1 },
  { key: "gps_count",         label: "GPS Records",         unit: "",    decimals: 0 },
  { key: "imu_count",         label: "IMU Records",         unit: "",    decimals: 0 },
  { key: "gps_sample_rate",   label: "GPS Sample Rate",     unit: "Hz",  decimals: 2 },
  { key: "imu_sample_rate",   label: "IMU Sample Rate",     unit: "Hz",  decimals: 2 },
];

function MetricCard({ label, value, unit }) {
  return (
    <div style={styles.card}>
      <div style={styles.cardLabel}>{label}</div>
      <div style={styles.cardValue}>
        {value !== undefined && value !== null ? value : "—"}
        {unit ? <span style={styles.cardUnit}> {unit}</span> : null}
      </div>
    </div>
  );
}

// ── IMU line chart ────────────────────────────────────────────────────────────
function ImuChart({ times = [], values = [], label, color }) {
  const layout = {
    paper_bgcolor: "#161b22",
    plot_bgcolor: "#0d1117",
    font: { color: "#e6edf3", size: 11 },
    margin: { l: 50, r: 10, t: 30, b: 40 },
    title: { text: label, font: { size: 12, color: "#e6edf3" } },
    xaxis: { title: "Time (s)", color: "#8b949e", gridcolor: "#21262d", zeroline: false },
    yaxis: { color: "#8b949e", gridcolor: "#21262d", zeroline: true, zerolinecolor: "#30363d" },
    showlegend: false,
  };

  return (
    <Plot
      data={[{
        type: "scattergl",
        mode: "lines",
        x: times,
        y: values,
        line: { color, width: 1.5 },
      }]}
      layout={layout}
      style={{ width: "100%", height: "220px" }}
      config={{ responsive: true, displayModeBar: false }}
    />
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MetricsPanel({ metrics = {}, imuData = {} }) {
  const formattedCards = useMemo(() =>
    CARD_DEFS.map(({ key, label, unit, decimals }) => ({
      label,
      unit,
      value: metrics[key] !== undefined
        ? (decimals === 0
            ? Number(metrics[key]).toLocaleString()
            : Number(metrics[key]).toFixed(decimals))
        : undefined,
    })),
  [metrics]);

  return (
    <div>
      {/* ── Scalar metric cards ─── */}
      <div style={styles.grid}>
        {formattedCards.map((c) => (
          <MetricCard key={c.label} {...c} />
        ))}
      </div>

      {/* ── IMU charts ─── */}
      {imuData.times && imuData.times.length > 0 && (
        <div style={styles.chartsRow}>
          <div style={styles.chartBox}>
            <ImuChart
              times={imuData.times}
              values={imuData.vel_z}
              label="Vertical Velocity (m/s)"
              color="#58a6ff"
            />
          </div>
          <div style={styles.chartBox}>
            <ImuChart
              times={imuData.times}
              values={imuData.acc_magnitude}
              label="Acceleration Magnitude (m/s²)"
              color="#f0883e"
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: "12px",
    marginBottom: "24px",
  },
  card: {
    background: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    padding: "14px 16px",
  },
  cardLabel: {
    fontSize: "11px",
    color: "#8b949e",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: "6px",
  },
  cardValue: {
    fontSize: "22px",
    fontWeight: 600,
    color: "#e6edf3",
    lineHeight: 1.2,
  },
  cardUnit: {
    fontSize: "13px",
    fontWeight: 400,
    color: "#8b949e",
  },
  chartsRow: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
  },
  chartBox: {
    background: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    overflow: "hidden",
  },
};
