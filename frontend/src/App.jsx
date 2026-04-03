/**
 * App — root React component.
 *
 * Routes:
 *   /               → simple landing page (redirect helper to Odoo)
 *   /mission/:id    → MissionPage (3D viewer, metrics, AI conclusion)
 */

import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import MissionPage from "./pages/MissionPage";

function LandingPage() {
  return (
    <div style={{
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      minHeight: "100vh", gap: "16px",
    }}>
      <h1 style={{ fontSize: "28px", color: "#e6edf3" }}>UAV Flight Viewer</h1>
      <p style={{ color: "#8b949e", fontSize: "14px" }}>
        Open a mission from Odoo to view the 3D trajectory and AI analysis.
      </p>
      <a
        href={`${"http://23.94.107.20:5433"}/odoo/uav-missions`}
        style={{
          padding: "10px 20px",
          background: "#1f6feb",
          color: "#fff",
          borderRadius: "6px",
          textDecoration: "none",
          fontSize: "14px",
          fontWeight: 600,
        }}
      >
        Open Odoo
      </a>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"              element={<LandingPage />} />
        <Route path="/mission/:id"   element={<MissionPage />} />
        <Route path="*"              element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
