# Foldiss UAV — Project Specification

> BEST::HACKath0n 2026 | Challenge: "UAV Flight Telemetry Analysis & 3D Visualisation"

---

## 1. Problem Statement

ArduPilot flight controllers record every sensor reading into binary `.BIN` log files — dense,
unreadable by humans without tooling. Analysing them manually is slow, error-prone, and requires
deep domain knowledge. This platform automates the full pipeline:

```
raw .BIN file  →  parse  →  metrics  →  3D trajectory  →  AI text conclusion
```

---

## 2. Provided Test Data

| File | GPS points | Valid GPS fix | IMU rate | Flight duration | Max GPS speed |
|---|---|---|---|---|---|
| `00000001.BIN` | 262 | 262 (Status 6 — 3D DGPS) | 50 Hz | 52.2 s | 51.74 m/s |
| `00000019.BIN` | 118 | 117 (Status ≥ 3) | 50 Hz | 23.2 s | 45.02 m/s |

Both are ArduPilot SITL simulated flights near Canberra, Australia (~35°S, 149°E).
Aircraft type: fixed-wing (speed ~45–52 m/s, large altitude swings).

GPS filter rule: `Status >= 3` AND `I == 0` (primary receiver only).
IMU filter rule: `I == 0` (primary IMU only).

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        User (Browser)                    │
└────────────────┬─────────────────────┬───────────────────┘
                 │ Login / Upload / UI  │ Open 3D Viewer
                 ▼                     ▼
┌────────────────────────┐   ┌─────────────────────────────┐
│   Odoo 18              │   │   3D Viewer (Dash/Plotly)   │
│   foldiss_uav addon    │   │   port 8050                 │
│                        │   │   reads PostgreSQL directly  │
│  • Auth & user mgmt    │   └─────────────────────────────┘
│  • .BIN file upload    │
│  • Mission dashboard   │
│  • Metrics display     │
│  • Redirect to viewer  │
└──────┬─────────────────┘
       │ publish job (JSON)
       ▼
┌─────────────────┐
│   RabbitMQ      │◄──────────────────────────┐
│                 │                            │
│  queues:        │                            │
│  • uav.parse    │                            │
│  • uav.ai       │                            │
└──────┬──────────┘                            │
       │                                       │
  ┌────┴──────────────────┐                    │
  │  Parser Worker        │                    │
  │  (Python service)     │                    │
  │                       │                    │
  │  1. fetch .BIN via    │                    │
  │     Odoo XML-RPC      │                    │
  │  2. pymavlink parse   │                    │
  │  3. haversine dist    │                    │
  │  4. trapz vel/accel   │                    │
  │  5. WGS-84 → ENU      │                    │
  │  6. save to PG via    │                    │
  │     Odoo XML-RPC      │                    │
  │  7. publish uav.ai ───┼────────────────────┘
  └───────────────────────┘
                                  ┌────────────────────────┐
                                  │  AI Worker             │
        ┌─────────────────────────┤  (Python service)      │
        │                         │                        │
        │  PostgreSQL 15          │  1. consume uav.ai     │
        │  (single source of      │  2. load Qwen2.5-1.5B  │
        │   truth)                │  3. generate conclusion│
        │                         │  4. save via XML-RPC   │
        │  tables:                └────────────────────────┘
        │  • uav_mission
        │  • uav_parse_result
        │  • ir_attachment (Odoo)
        └──────────────────────────────────────────────────

Monitoring: Prometheus → Grafana (existing stack)
```

---

## 4. Services

### 4.1 Odoo — `foldiss_uav` addon

**Port:** 8069 (behind Nginx on 5433)

**Models:**

| Model | Table | Key fields |
|---|---|---|
| `uav.mission` | `uav_mission` | name, log_file (Binary), status, user_id |
| `uav.parse.result` | `uav_parse_result` | mission_id, metrics (Floats), gps_points (JSON), enu_points (JSON), imu_data (JSON) |

**Mission status flow:**
```
draft → queued → parsing → parsed → ai_processing → done
                                                    ↓
                                                  error
```

**Actions:**
- `action_start_parsing` — validates file, publishes to `uav.parse` queue, sets status = queued
- `action_open_viewer` — opens 3D viewer URL in new tab
- Webhook endpoint `POST /uav/webhook` — called by services to update mission status

---

### 4.2 Parser Worker

**Language:** Python 3.11
**Trigger:** RabbitMQ queue `uav.parse`

**Pipeline:**
1. Receive `{ mission_id, attachment_id }` from queue
2. Fetch raw `.BIN` bytes via `ir.attachment` XML-RPC call
3. Write to `/tmp/<mission_id>.bin`
4. Parse with `pymavlink.mavutil`
5. Run all metric calculations (see §6)
6. Update `uav.mission` + create `uav.parse.result` via XML-RPC
7. Publish `{ mission_id, parse_result_id }` to `uav.ai`
8. ACK message

**Error handling:** on exception → update mission status = error, NACK message (no requeue).

---

### 4.3 AI Worker

**Language:** Python 3.11
**Trigger:** RabbitMQ queue `uav.ai`
**Model:** `Qwen/Qwen2.5-1.5B-Instruct` (HuggingFace)
**Device:** CPU (torch.float32)
**Fine-tuning:** PEFT LoRA adapter (optional, loaded if present at `/app/lora_adapter/`)

**Pipeline:**
1. Receive `{ mission_id, parse_result_id }` from queue
2. Fetch metrics from `uav.parse.result` via XML-RPC
3. Build structured prompt (see §7)
4. Run model inference (max 512 new tokens)
5. Save conclusion text to `uav.mission.ai_conclusion` via XML-RPC
6. Set mission status = done

---

### 4.4 3D Viewer

**Language:** Python 3.11 / Dash 2.x
**Port:** 8050
**Route:** `/mission/<id>`

**Features:**
- 3D scatter/line plot of ENU trajectory (Plotly go.Scatter3d)
- Colour-map: speed (m/s) → viridis palette
- Hover: timestamp, lat/lng, altitude, speed
- Sidebar: all computed metrics
- Auto-refresh if mission not yet done (polling `/uav/api/mission/<id>`)

---

### 4.5 RabbitMQ

**Image:** `rabbitmq:3.13-management`
**Port:** 5672 (AMQP), 15672 (management UI)
**Queues:**

| Queue | Producer | Consumer | Durable |
|---|---|---|---|
| `uav.parse` | Odoo | Parser Worker | yes |
| `uav.ai` | Parser Worker | AI Worker | yes |

---

## 5. Data Flow (sequence)

```
User          Odoo            RabbitMQ       Parser         AI Worker     PostgreSQL
 │             │                 │              │               │              │
 │──upload──►  │                 │              │               │              │
 │             │──store attach.──┼──────────────┼───────────────┼──────────────►
 │             │──publish────────►              │               │              │
 │             │                 │──deliver─────►               │              │
 │             │                 │              │──parse .BIN   │              │
 │             │                 │              │──calc metrics │              │
 │             │                 │              │──save result──┼──────────────►
 │             │◄────────────────┼──xml-rpc upd─┤               │              │
 │             │                 │──publish─────┼───────────────►              │
 │             │                 │              │               │──load model  │
 │             │                 │              │               │──inference   │
 │             │                 │              │               │──save concl.─►
 │             │◄────────────────┼──────────────┼───xml-rpc upd─┤              │
 │◄─status upd─┤                 │              │               │              │
 │──open 3D────┼─────────────────┼──────────────┼───────────────┼──────────────►
              viewer reads PostgreSQL directly
```

---

## 6. Required Algorithms

### 6.1 Haversine Distance (mandatory)

Custom Python implementation — no external geo library.

```python
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two WGS-84 points.
    Returns metres.
    Uses the haversine formula:
      a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
      c = 2 · atan2(√a, √(1−a))
      d = R · c
    """
    R = 6_371_000.0  # mean Earth radius, metres
    ...
```

Total distance = sum of haversine(p_i, p_{i+1}) over all consecutive valid GPS points.

### 6.2 Trapezoidal Integration — IMU → velocity (mandatory)

Custom implementation using numpy, applied to IMU vertical acceleration.

```python
# Why vertical (AccZ)?
# AccX/AccY contain horizontal body-frame accelerations mixed with
# centripetal and Coriolis terms; without full attitude matrix rotation
# they cannot be cleanly integrated into world-frame velocity.
# AccZ (after mean-subtraction to remove gravity bias) gives vertical
# acceleration in near-inertial frame for short durations.

acc_z_debiased = acc_z - np.mean(acc_z)   # remove ~9.81 m/s² gravity bias
vel_z = np.cumtrapz(acc_z_debiased, time_s, initial=0.0)
max_vertical_speed_imu = float(np.max(np.abs(vel_z)))
```

Horizontal speed: taken directly from GPS `Spd` field (more accurate for fixed-wing).
Both values reported separately in the result.

### 6.3 WGS-84 → ENU Coordinate Conversion (mandatory)

Origin = first valid GPS fix of the mission.

```python
def wgs84_to_enu(lat, lon, alt, lat0, lon0, alt0):
    """
    Convert geodetic WGS-84 (degrees, metres) to local ENU (metres).
    Approximation valid for distances < 50 km (error < 0.1%).

    East  = R · Δλ · cos(φ0)
    North = R · Δφ
    Up    = Δh
    """
    R = 6_378_137.0  # WGS-84 semi-major axis
    east  = R * math.radians(lon - lon0) * math.cos(math.radians(lat0))
    north = R * math.radians(lat - lat0)
    up    = alt - alt0
    return east, north, up
```

### 6.4 Computed Metrics Summary

| Metric | Source | Method |
|---|---|---|
| Total distance | GPS Lat/Lng | Σ haversine(pᵢ, pᵢ₊₁) |
| Max horizontal speed | GPS `Spd` field | max() |
| Max vertical speed | IMU AccZ | trapz integration |
| Max acceleration | IMU AccX/Y/Z | max(‖acc‖) after gravity removal |
| Max altitude gain | GPS `Alt` | max(Alt) − min(Alt) |
| Flight duration | GPS `TimeUS` | (last − first) / 1e6 |
| GPS sample rate | GPS `TimeUS` | len / duration |
| IMU sample rate | IMU `TimeUS` | len / duration |

---

## 7. AI Prompt Template

```
You are a UAV flight data analyst. Analyse the following mission metrics and write a
concise technical report (5–8 sentences). Identify anomalies, performance highlights,
and potential safety concerns.

Mission: {mission_name}
Duration: {flight_duration:.1f} s
Total distance: {total_distance:.0f} m
Max horizontal speed (GPS): {max_h_speed:.2f} m/s
Max vertical speed (IMU trapz): {max_v_speed:.2f} m/s
Max acceleration: {max_acceleration:.2f} m/s²
Max altitude gain: {max_altitude_gain:.1f} m
GPS fix points: {gps_count}
IMU samples: {imu_count}

Provide your analysis:
```

---

## 8. Fine-Tuning Strategy

**Base model:** `Qwen/Qwen2.5-1.5B-Instruct`
**Method:** PEFT LoRA (rank=8, alpha=16, target modules: q_proj, v_proj)
**Dataset:** `ai/training_data.jsonl` — synthetic examples of metrics → flight conclusion
**Training:** `finetune.py` script (CPU or GPU), ~50–100 examples, 3 epochs
**Output:** LoRA adapter saved to `lora_adapter/`
**Inference:** load base model + merge adapter if present, else use base model directly

---

## 9. Ports Reference (full platform)

| Service | Port | Notes |
|---|---|---|
| App (Nginx → Odoo) | 5433 | Main entry |
| Odoo internal | 8069 | Container-to-container |
| PostgreSQL | 5435 | |
| RabbitMQ AMQP | 5672 | Internal only |
| RabbitMQ Management UI | 15672 | Debug |
| 3D Viewer | 8050 | External |
| PgAdmin | 5050 | Dev only |
| Grafana | 3003 | Monitoring |

---

## 10. Evaluation Criteria Mapping

| Criterion | Weight | How we cover it |
|---|---|---|
| MVP functionality (parsing, metrics, 3D) | 40% | pymavlink + all 3 algorithms + Dash viewer |
| Algorithmic basis (haversine, trapz, ENU) | 20% | Custom implementations, documented in code |
| Nice-to-have (Web UI, AI) | 15% | Odoo UI + Qwen2.5-1.5B with LoRA fine-tune |
| Architecture & code quality | 10% | Modular services, typed Python, Odoo OCA conventions |
| Documentation / Presentation | 15% | spec.md, tech-stack.md, README, code comments |
