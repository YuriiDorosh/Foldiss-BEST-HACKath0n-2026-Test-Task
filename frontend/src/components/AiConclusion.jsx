/**
 * AiConclusion — renders the LLM-generated flight analysis text.
 *
 * Props:
 *   conclusion  {string|null}   — markdown-like text from the AI worker
 *   aiStatus    {string}        — "pending" | "processing" | "done" | "error"
 */

import React from "react";
import PropTypes from "prop-types";

const STATUS_COLOR = {
  pending:    "#8b949e",
  processing: "#d29922",
  done:       "#3fb950",
  error:      "#f85149",
};

const STATUS_LABEL = {
  pending:    "Waiting for AI analysis…",
  processing: "AI is analysing the flight…",
  done:       null,
  error:      "AI analysis failed.",
};

AiConclusion.propTypes = {
  conclusion: PropTypes.string,
  aiStatus:   PropTypes.string,
};

export default function AiConclusion({ conclusion = null, aiStatus = "pending" }) {
  const color = STATUS_COLOR[aiStatus] || "#8b949e";
  const statusLabel = STATUS_LABEL[aiStatus];

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>AI Flight Analysis</span>
        <span style={{ ...styles.badge, borderColor: color, color }}>
          {aiStatus.toUpperCase()}
        </span>
      </div>

      {statusLabel && (
        <p style={{ ...styles.statusMsg, color }}>{statusLabel}</p>
      )}

      {conclusion && (
        <div style={styles.body}>
          {conclusion.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return <h3 key={i} style={styles.h3}>{line.slice(3)}</h3>;
            }
            if (line.startsWith("- ") || line.startsWith("* ")) {
              return (
                <div key={i} style={styles.bullet}>
                  <span style={styles.bulletDot}>•</span>
                  <span>{line.slice(2)}</span>
                </div>
              );
            }
            if (line.trim() === "") return <div key={i} style={{ height: "8px" }} />;
            return <p key={i} style={styles.para}>{line}</p>;
          })}
        </div>
      )}

      {!conclusion && aiStatus === "done" && (
        <p style={{ color: "#8b949e", fontSize: "13px" }}>
          No conclusion text returned by AI worker.
        </p>
      )}
    </div>
  );
}

const styles = {
  container: {
    background: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    padding: "20px 24px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "14px",
  },
  title: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#e6edf3",
  },
  badge: {
    fontSize: "10px",
    fontWeight: 600,
    padding: "2px 8px",
    border: "1px solid",
    borderRadius: "12px",
    letterSpacing: "0.08em",
  },
  statusMsg: {
    fontSize: "13px",
    marginBottom: "8px",
  },
  body: {
    lineHeight: 1.65,
    fontSize: "14px",
    color: "#c9d1d9",
  },
  h3: {
    fontSize: "15px",
    fontWeight: 600,
    color: "#58a6ff",
    margin: "16px 0 6px",
  },
  para: {
    margin: "4px 0",
  },
  bullet: {
    display: "flex",
    gap: "8px",
    margin: "4px 0",
  },
  bulletDot: {
    color: "#58a6ff",
    flexShrink: 0,
  },
};
