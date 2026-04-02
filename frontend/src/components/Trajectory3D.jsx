/**
 * Trajectory3D — interactive 3-D flight path rendered with Plotly.
 *
 * Displays:
 *   - 3D scatter trace coloured by altitude (Viridis colorscale)
 *   - Markers for start (green) and end (red)
 *
 * Props:
 *   enuPoints  {Array<{east, north, up}>}
 *   gpsPoints  {Array<{t, lat, lng, alt, spd}>}   (used for hover text)
 */

import React, { useMemo } from "react";
import Plot from "react-plotly.js";

export default function Trajectory3D({ enuPoints = [], gpsPoints = [] }) {
  const { east, north, up, altColor, hoverText } = useMemo(() => {
    const east      = enuPoints.map((p) => p.east);
    const north     = enuPoints.map((p) => p.north);
    const up        = enuPoints.map((p) => p.up);
    const altColor  = up; // colour by altitude gain
    const hoverText = enuPoints.map((p, i) => {
      const g = gpsPoints[i] || {};
      return (
        `E: ${p.east.toFixed(1)} m<br>` +
        `N: ${p.north.toFixed(1)} m<br>` +
        `Alt gain: ${p.up.toFixed(1)} m<br>` +
        `Speed: ${(g.spd ?? 0).toFixed(2)} m/s<br>` +
        `T+${(g.t ?? 0).toFixed(1)} s`
      );
    });
    return { east, north, up, altColor, hoverText };
  }, [enuPoints, gpsPoints]);

  if (enuPoints.length === 0) {
    return (
      <div style={styles.placeholder}>No trajectory data available.</div>
    );
  }

  const trace = {
    type: "scatter3d",
    mode: "lines+markers",
    x: east,
    y: north,
    z: up,
    text: hoverText,
    hoverinfo: "text",
    line: {
      color: altColor,
      colorscale: "Viridis",
      width: 4,
    },
    marker: {
      size: 2,
      color: altColor,
      colorscale: "Viridis",
      colorbar: {
        title: "Alt gain (m)",
        thickness: 12,
        tickfont: { color: "#e6edf3", size: 10 },
        titlefont: { color: "#e6edf3", size: 11 },
      },
    },
  };

  // Start marker
  const startMarker = {
    type: "scatter3d",
    mode: "markers+text",
    x: [east[0]],
    y: [north[0]],
    z: [up[0]],
    text: ["START"],
    textposition: "top center",
    textfont: { color: "#3fb950", size: 11 },
    marker: { size: 8, color: "#3fb950", symbol: "circle" },
    hoverinfo: "skip",
    showlegend: false,
  };

  // End marker
  const endMarker = {
    type: "scatter3d",
    mode: "markers+text",
    x: [east[east.length - 1]],
    y: [north[north.length - 1]],
    z: [up[up.length - 1]],
    text: ["END"],
    textposition: "top center",
    textfont: { color: "#f85149", size: 11 },
    marker: { size: 8, color: "#f85149", symbol: "circle" },
    hoverinfo: "skip",
    showlegend: false,
  };

  const layout = {
    paper_bgcolor: "#161b22",
    plot_bgcolor: "#161b22",
    font: { color: "#e6edf3" },
    margin: { l: 0, r: 0, t: 30, b: 0 },
    title: {
      text: "3D Flight Trajectory (ENU frame)",
      font: { color: "#e6edf3", size: 14 },
    },
    scene: {
      bgcolor: "#0d1117",
      xaxis: { title: "East (m)", color: "#8b949e", gridcolor: "#21262d" },
      yaxis: { title: "North (m)", color: "#8b949e", gridcolor: "#21262d" },
      zaxis: { title: "Up (m)", color: "#8b949e", gridcolor: "#21262d" },
      camera: { eye: { x: 1.4, y: 1.4, z: 0.9 } },
    },
    showlegend: false,
  };

  return (
    <Plot
      data={[trace, startMarker, endMarker]}
      layout={layout}
      style={{ width: "100%", height: "520px" }}
      config={{ responsive: true, displayModeBar: true, displaylogo: false }}
    />
  );
}

const styles = {
  placeholder: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "300px",
    color: "#8b949e",
    background: "#161b22",
    borderRadius: "8px",
    fontSize: "14px",
  },
};
