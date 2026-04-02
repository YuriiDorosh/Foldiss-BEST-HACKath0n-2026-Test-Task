/**
 * MissionPage — main page for a single UAV mission.
 *
 * Route: /mission/:id
 *
 * Behaviour:
 *   1. Poll /uav/api/mission/<id> every 3 s until status is "done" or "error".
 *   2. Once "done", fetch full trajectory data.
 *   3. Render Trajectory3D + MetricsPanel + AiConclusion.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import Trajectory3D   from "../components/Trajectory3D";
import MetricsPanel   from "../components/MetricsPanel";
import AiConclusion   from "../components/AiConclusion";
import { fetchMissionStatus, fetchMissionData } from "../api/odoo";

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES = new Set(["done", "error"]);
const FETCH_STATUSES    = new Set(["parsed", "ai_processing", "done"]);

export default function MissionPage() {
  const { id } = useParams();

  const [status,      setStatus]      = useState("loading");
  const [missionData, setMissionData] = useState(null);
  const [error,       setError]       = useState(null);

  const pollRef   = useRef(null);
  const fetchedRef = useRef(false);

  // ── Fetch full data once parse is done ──────────────────────────────────
  const loadData = useCallback(async () => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    try {
      const data = await fetchMissionData(id);
      setMissionData(data);
    } catch (e) {
      setError(`Failed to load mission data: ${e.message}`);
    }
  }, [id]);

  // ── Status poller ────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const s = await fetchMissionStatus(id);
        if (cancelled) return;

        setStatus(s.status);

        if (s.status === "error") {
          setError(s.error_message || "An unknown error occurred.");
          return; // stop polling
        }

        if (FETCH_STATUSES.has(s.status)) {
          loadData(); // non-blocking — may already be in flight
        }

        if (!TERMINAL_STATUSES.has(s.status)) {
          pollRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (cancelled) return;
        setError(`Polling error: ${e.message}`);
      }
    }

    poll();

    return () => {
      cancelled = true;
      clearTimeout(pollRef.current);
    };
  }, [id, loadData]);

  // ── Helpers ──────────────────────────────────────────────────────────────
  const metrics = missionData ? {
    total_distance:    missionData.total_distance,
    max_h_speed:       missionData.max_h_speed,
    max_v_speed:       missionData.max_v_speed,
    max_acceleration:  missionData.max_acceleration,
    max_altitude_gain: missionData.max_altitude_gain,
    flight_duration:   missionData.flight_duration,
    gps_count:         missionData.gps_count,
    imu_count:         missionData.imu_count,
    gps_sample_rate:   missionData.gps_sample_rate,
    imu_sample_rate:   missionData.imu_sample_rate,
  } : {};

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={styles.page}>
      {/* ── Top bar ── */}
      <header style={styles.header}>
        <Link to="/" style={styles.back}>← Missions</Link>
        <h1 style={styles.title}>Mission #{id}</h1>
        <StatusBadge status={status} />
      </header>

      {/* ── Error banner ── */}
      {error && (
        <div style={styles.errorBanner}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* ── Loading spinner while waiting for parse ── */}
      {!missionData && !error && status !== "done" && (
        <div style={styles.waiting}>
          <Spinner />
          <p style={styles.waitingText}>
            {WAITING_TEXT[status] || `Status: ${status}…`}
          </p>
        </div>
      )}

      {/* ── Main content once data is available ── */}
      {missionData && (
        <div style={styles.content}>
          {/* 3D trajectory */}
          <section style={styles.section}>
            <Trajectory3D
              enuPoints={missionData.enu_points || []}
              gpsPoints={missionData.gps_points || []}
            />
          </section>

          {/* Metrics */}
          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>Flight Metrics</h2>
            <MetricsPanel
              metrics={metrics}
              imuData={missionData.imu_data || {}}
            />
          </section>

          {/* AI conclusion */}
          <section style={styles.section}>
            <AiConclusion
              conclusion={missionData.ai_conclusion}
              aiStatus={missionData.ai_status || "pending"}
            />
          </section>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const COLOR = {
    loading:       "#8b949e",
    draft:         "#8b949e",
    queued:        "#d29922",
    parsing:       "#d29922",
    parsed:        "#58a6ff",
    ai_processing: "#d29922",
    done:          "#3fb950",
    error:         "#f85149",
  };
  const c = COLOR[status] || "#8b949e";
  return (
    <span style={{
      padding: "3px 10px",
      border: `1px solid ${c}`,
      borderRadius: "12px",
      color: c,
      fontSize: "11px",
      fontWeight: 600,
      letterSpacing: "0.07em",
      textTransform: "uppercase",
    }}>
      {status}
    </span>
  );
}

function Spinner() {
  return (
    <div style={{
      width: "36px", height: "36px",
      border: "3px solid #30363d",
      borderTopColor: "#58a6ff",
      borderRadius: "50%",
      animation: "spin 0.8s linear infinite",
      margin: "0 auto 16px",
    }} />
  );
}

// ── Waiting messages by status ────────────────────────────────────────────────
const WAITING_TEXT = {
  draft:         "Mission is in draft. Start parsing from Odoo.",
  queued:        "Mission queued — waiting for parser worker…",
  parsing:       "Parsing flight log…",
  parsed:        "Log parsed — AI analysis starting…",
  ai_processing: "AI is analysing the flight…",
};

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
  page: {
    maxWidth: "1100px",
    margin: "0 auto",
    padding: "24px 16px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    marginBottom: "24px",
    flexWrap: "wrap",
  },
  back: {
    color: "#58a6ff",
    textDecoration: "none",
    fontSize: "14px",
  },
  title: {
    fontSize: "22px",
    fontWeight: 700,
    color: "#e6edf3",
    flex: 1,
  },
  errorBanner: {
    background: "#2d0f10",
    border: "1px solid #f85149",
    borderRadius: "6px",
    padding: "12px 16px",
    color: "#f85149",
    marginBottom: "20px",
    fontSize: "14px",
  },
  waiting: {
    textAlign: "center",
    padding: "60px 20px",
  },
  waitingText: {
    color: "#8b949e",
    fontSize: "14px",
  },
  content: {
    display: "flex",
    flexDirection: "column",
    gap: "24px",
  },
  section: {
    background: "#0d1117",
  },
  sectionTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#e6edf3",
    marginBottom: "14px",
  },
};

// Inject keyframe animation globally once
if (typeof document !== "undefined" && !document.getElementById("uav-spin-kf")) {
  const s = document.createElement("style");
  s.id = "uav-spin-kf";
  s.textContent = "@keyframes spin { to { transform: rotate(360deg); } }";
  document.head.appendChild(s);
}
