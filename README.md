# Foldiss UAV — Flight Log Analysis Platform

Automated analysis platform for ArduPilot UAV flight logs. Upload a `.BIN` file, get parsed telemetry, 3D trajectory visualization, real map view, and AI-generated flight conclusions.

## Architecture

```
User
 │
 ├── Odoo 18 (:5433)          Mission management, file upload, status tracking
 │     ├── PostgreSQL 15       All data storage
 │     └── RabbitMQ            Async job queue
 │           ├── Parser Worker  .BIN → GPS/IMU metrics + flight analytics
 │           └── AI Worker      Qwen2.5-1.5B → HTML flight conclusion
 │
 └── React Frontend (:3000)    3D trajectory, map view, metrics, AI analysis
```

Full architecture diagram: [`docs/architecture.puml`](docs/architecture.puml)

## Prerequisites

- **Docker** and **Docker Compose** (v2)
- **Python 3.11+** (for init script and model download)
- **Make**
- **~6 GB disk** for AI model + Docker images
- (Optional) **HuggingFace token** for gated model access

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/YuriiDorosh/Foldiss-BEST-HACKath0n-2026-Test-Task.git
cd Foldiss-BEST-HACKath0n-2026-Test-Task

cp .env.example .env
# Edit .env if needed (defaults work for local development)
```

### 2. Download the AI model (~3 GB, one-time)

```bash
# Add your HuggingFace token to .env (optional, for gated models):
# HF_TOKEN=hf_xxxxxxxxxxxxx

make download-model
```

This downloads `Qwen/Qwen2.5-1.5B-Instruct` into `artifacts/models/hub/`. The AI worker runs fully offline after this step.

### 3. Start everything

**Option A — Cold start (first time, builds everything from scratch):**

```bash
make ultra
```

This runs the full bootstrap:
1. Creates `artifacts/` directories
2. Creates Docker network `backend`
3. Tears down any existing containers + volumes
4. Builds all images (no cache)
5. Starts Odoo stack (DB + Odoo + Nginx)
6. Starts RabbitMQ, Parser, AI Worker, Frontend
7. Waits for Odoo and installs `foldiss_uav` addon

**Option B — Normal start (images already built):**

```bash
make up-all
```

### 4. Access the platform

| Service | URL | Credentials |
|---|---|---|
| **Odoo** (main UI) | http://localhost:5433 | `admin` / `admin` |
| **Frontend** (3D viewer) | http://localhost:3000 | — |
| **RabbitMQ** management | http://localhost:15672 | `guest` / `guest` |
| **PgAdmin** | http://localhost:5050 | `admin@admin.com` / `admin` |
| **Grafana** | http://localhost:3003 | `admin` / `admin` |

## Usage

1. Open **Odoo** at http://localhost:5433
2. Navigate to **UAV Missions**
3. Create a new mission and upload an ArduPilot `.BIN` flight log
4. Click **Start Parsing**
5. Wait for parsing to complete (a few seconds)
6. Click **Open 3D Viewer** to see the trajectory in the React frontend
7. AI analysis runs automatically after parsing — results appear in the **AI Analysis** tab

## Makefile Reference

### Full Stack

| Command | Description |
|---|---|
| `make ultra` | Full cold start from scratch (wipes volumes, no-cache build) |
| `make up-all` | Start everything (Odoo + services) |
| `make up-all-build` | Rebuild all images, then start |
| `make down-all` | Stop everything |
| `make nuke` | Remove ALL Docker containers, images, volumes, networks |

### Individual Services

| Command | Description |
|---|---|
| `make up-odoo` | Start Odoo stack only |
| `make up-services` | Start RabbitMQ + Parser + AI + Frontend |
| `make up-rabbitmq` | Start only RabbitMQ |
| `make up-parser` | Start only Parser Worker |
| `make up-ai` | Start only AI Worker |
| `make up-frontend` | Start only Frontend |

Rebuild variants: `make up-parser-build`, `make up-ai-build`, `make up-frontend-build`

### Logs

| Command | Description |
|---|---|
| `make logs-all` | Follow all service logs |
| `make logs-parser` | Follow Parser Worker logs |
| `make logs-ai` | Follow AI Worker logs |
| `make logs-frontend` | Follow Frontend logs |
| `make logs-rabbitmq` | Follow RabbitMQ logs |

### Setup

| Command | Description |
|---|---|
| `make init-odoo` | Wait for Odoo + install `foldiss_uav` addon |
| `make download-model` | Download Qwen2.5 model into `artifacts/models/` |

## Project Structure

```
.
├── odoo/                        # Odoo 18 stack
│   ├── src/addons/foldiss_uav/  # Custom addon (mission model, views, API)
│   ├── docker_compose/          # Compose files for Odoo, DB, monitoring
│   └── Makefile                 # Odoo-specific commands
├── parser/                      # Parser Worker (pymavlink)
│   ├── parser/
│   │   ├── bin_parser.py        # .BIN file parsing (GPS + IMU extraction)
│   │   └── metrics.py           # Flight metrics + analytics computation
│   └── main.py                  # RabbitMQ consumer entry point
├── ai/                          # AI Worker (Qwen2.5-1.5B-Instruct)
│   ├── ai/
│   │   ├── model.py             # LLM loading + inference + HTML sanitization
│   │   └── prompt.py            # Prompt construction for flight analysis
│   └── main.py                  # RabbitMQ consumer entry point
├── frontend/                    # React frontend (Vite + Plotly + Leaflet)
│   └── src/
│       ├── pages/MissionPage.jsx
│       └── components/          # Trajectory3D, TrajectoryMap, MetricsPanel, AiConclusion
├── scripts/
│   └── init_odoo.py             # Bootstrap script (addon installation)
├── artifacts/                   # Model weights (git-ignored, bind-mounted)
│   ├── models/hub/              # HuggingFace cache
│   └── lora/                    # LoRA adapter (optional)
├── docs/
│   └── architecture.puml        # Full architecture diagram (PlantUML)
├── docker-compose.yml           # Root services: RabbitMQ, Parser, AI, Frontend
├── Makefile                     # Top-level orchestration
└── .env.example                 # Environment template
```

## Data Flow

```
1. User uploads .BIN file in Odoo → mission created (status: draft)
2. User clicks "Start Parsing" → Odoo publishes to RabbitMQ (uav.parse queue)
3. Parser Worker consumes job:
   - Downloads .BIN via XML-RPC
   - Parses GPS (fix status >= 3, receiver 0) and IMU (sensor 0)
   - Computes metrics: Haversine distance, trapezoidal IMU integration, WGS-84→ENU
   - Computes analytics: path efficiency, flight phases, vibration RMS, turn detection
   - Saves results to Odoo, publishes to uav.ai queue
4. AI Worker consumes job:
   - Reads metrics + analytics from Odoo via XML-RPC
   - Generates HTML flight conclusion using Qwen2.5-1.5B
   - Saves conclusion to Odoo, marks mission "done"
5. Frontend polls Odoo API every 3s, renders 3D trajectory + map + metrics + AI analysis
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_DB` | `postgres` | Database name |
| `POSTGRES_USER` | `odoo` | Database user |
| `POSTGRES_PASSWORD` | `StrongDBPass_123` | Database password |
| `RABBITMQ_HOST` | `rabbitmq` | RabbitMQ hostname |
| `RABBITMQ_USER` | `guest` | RabbitMQ user |
| `RABBITMQ_PASSWORD` | `guest` | RabbitMQ password |
| `ODOO_URL` | `http://odoo:8069` | Odoo internal URL (for workers) |
| `ODOO_DB` | `postgres` | Odoo database name |
| `ODOO_USER` | `admin` | Odoo admin username |
| `ODOO_PASSWORD` | `admin` | Odoo admin password |
| `VITE_ODOO_EXTERNAL_URL` | `http://localhost:5433` | Public Odoo URL (for frontend links) |
| `HF_TOKEN` | — | HuggingFace token (for model download) |
| `NGINX_PORT` | `5433` | Nginx proxy port for Odoo |

## Algorithms

- **Haversine Formula** — Great-circle distance between GPS points
- **Trapezoidal Integration** — AccZ → vertical velocity estimation
- **WGS-84 → ENU** — Geodetic to local Cartesian coordinate conversion
- **Flight Phase Detection** — Hover/cruise/climb/descent classification
- **Vibration RMS** — Per-axis acceleration residual analysis
- **Path Efficiency** — Straight-line vs. actual distance ratio
- **Turn Detection** — Heading change analysis (>15 deg threshold)
- **GPS Anomaly Detection** — Implied speed filter (>50 m/s = jump)
- **Acceleration Spike Detection** — Magnitude filter (>15 m/s² above gravity)

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Odoo 18, Python 3.11 |
| Database | PostgreSQL 15 |
| Message Broker | RabbitMQ 3.13 |
| Parser | pymavlink, NumPy |
| AI Model | Qwen/Qwen2.5-1.5B-Instruct (CPU, float32) |
| AI Framework | HuggingFace Transformers, PyTorch |
| Frontend | React 18, Vite, Plotly.js, Leaflet |
| Proxy | Nginx |
| Monitoring | Prometheus, Grafana, Loki |
| Containerization | Docker, Docker Compose |

## Troubleshooting

**Odoo not starting?**
```bash
make logs-odoo          # Check Odoo container logs
make init-odoo          # Re-run init script (waits up to 10 min)
```

**AI Worker offline error?**
```bash
# Model must be downloaded first
make download-model
# Then restart AI worker
make up-ai-build
```

**Frontend can't reach Odoo?**
The frontend Nginx proxies `/uav/*` to Odoo. Make sure Odoo is running before starting the frontend:
```bash
make up-odoo            # Start Odoo first
make up-frontend        # Then frontend
```

**Reset everything?**
```bash
make nuke               # Removes ALL Docker data
make ultra              # Full rebuild from scratch
```

## License

BEST::HACKath0n 2026 Test Task
