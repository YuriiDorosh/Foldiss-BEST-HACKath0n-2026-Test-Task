/**
 * TrajectoryMap — renders the GPS flight path on a real OpenStreetMap tile layer.
 *
 * Props:
 *   gpsPoints  — array of { lat, lng, alt, spd, t }
 */

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export default function TrajectoryMap({ gpsPoints }) {
  const containerRef   = useRef(null);
  const mapInstanceRef = useRef(null);

  useEffect(() => {
    if (!gpsPoints || gpsPoints.length === 0) return;
    if (mapInstanceRef.current) return; // already mounted

    const coords = gpsPoints.map((p) => [p.lat, p.lng]);
    const center = coords[Math.floor(coords.length / 2)];

    // Create map
    const map = L.map(containerRef.current, { zoomControl: true }).setView(center, 15);
    mapInstanceRef.current = map;

    // OpenStreetMap tiles — free, no API key required
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
      maxZoom: 19,
    }).addTo(map);

    // Flight path polyline
    const polyline = L.polyline(coords, {
      color:   "#58a6ff",
      weight:  3,
      opacity: 0.85,
    }).addTo(map);

    map.fitBounds(polyline.getBounds(), { padding: [32, 32] });

    // Altitude colour segments (split path into chunks coloured by altitude gain)
    const alts = gpsPoints.map((p) => p.alt);
    const minAlt = Math.min(...alts);
    const maxAlt = Math.max(...alts);
    const range  = maxAlt - minAlt || 1;

    function altColor(alt) {
      // Blue (low) → Yellow → Red (high)  — matches Viridis-ish feel
      const t = (alt - minAlt) / range;
      const r = Math.round(t * 220);
      const g = Math.round(80 + t * 100);
      const b = Math.round(255 - t * 220);
      return `rgb(${r},${g},${b})`;
    }

    // Draw coloured segments
    for (let i = 0; i < coords.length - 1; i++) {
      L.polyline([coords[i], coords[i + 1]], {
        color:   altColor(alts[i]),
        weight:  4,
        opacity: 0.9,
      }).addTo(map);
    }

    // Start marker (green)
    const startIcon = L.divIcon({
      className: "",
      html: `<div style="
        width:14px;height:14px;border-radius:50%;
        background:#3fb950;border:2px solid #fff;
        box-shadow:0 0 4px rgba(0,0,0,0.5);
      "></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    L.marker(coords[0], { icon: startIcon })
      .bindTooltip("START", { permanent: false, direction: "top" })
      .addTo(map);

    // End marker (red)
    const endIcon = L.divIcon({
      className: "",
      html: `<div style="
        width:14px;height:14px;border-radius:50%;
        background:#f85149;border:2px solid #fff;
        box-shadow:0 0 4px rgba(0,0,0,0.5);
      "></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    L.marker(coords[coords.length - 1], { icon: endIcon })
      .bindTooltip("END", { permanent: false, direction: "top" })
      .addTo(map);

    // Popups on click along path
    gpsPoints.forEach((p, i) => {
      if (i % Math.max(1, Math.floor(gpsPoints.length / 40)) !== 0) return;
      L.circleMarker([p.lat, p.lng], {
        radius: 4, color: altColor(p.alt), fillOpacity: 0.7, weight: 1,
      })
        .bindPopup(
          `<b>Point ${i + 1}</b><br>` +
          `Lat: ${p.lat.toFixed(6)}<br>` +
          `Lng: ${p.lng.toFixed(6)}<br>` +
          `Alt: ${p.alt.toFixed(1)} m<br>` +
          `Speed: ${p.spd.toFixed(2)} m/s<br>` +
          `t: ${p.t.toFixed(2)} s`
        )
        .addTo(map);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [gpsPoints]);

  if (!gpsPoints || gpsPoints.length === 0) {
    return (
      <div style={styles.empty}>No GPS data available for map view.</div>
    );
  }

  return (
    <div style={styles.wrapper}>
      <div ref={containerRef} style={styles.map} />
      <div style={styles.legend}>
        <span style={{ color: "rgb(0,80,255)" }}>▬</span> Low altitude &nbsp;
        <span style={{ color: "rgb(110,130,145)" }}>▬</span> Mid &nbsp;
        <span style={{ color: "rgb(220,180,35)" }}>▬</span> High
      </div>
    </div>
  );
}

const styles = {
  wrapper: {
    width: "100%",
  },
  map: {
    width:        "100%",
    height:       "500px",
    borderRadius: "8px",
    border:       "1px solid #30363d",
    overflow:     "hidden",
  },
  legend: {
    marginTop:  "8px",
    fontSize:   "12px",
    color:      "#8b949e",
    textAlign:  "center",
  },
  empty: {
    height:     "500px",
    display:    "flex",
    alignItems: "center",
    justifyContent: "center",
    color:      "#8b949e",
    border:     "1px solid #30363d",
    borderRadius: "8px",
  },
};
