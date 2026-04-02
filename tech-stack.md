# Foldiss UAV — Tech Stack

> Reference document for every technology, library, model, and pattern used in the platform.

---

## 1. Service Map

```
┌──────────────────────────────────────────────────────────────────────┐
│  Service          │  Language    │  Key Framework      │  Port       │
├──────────────────────────────────────────────────────────────────────┤
│  Odoo (foldiss_uav addon)  Python 3.11   Odoo 18 ORM/OWL   5433/8069│
│  Parser Worker    │  Python 3.11 │  pymavlink + numpy  │  —          │
│  AI Worker        │  Python 3.11 │  transformers/PEFT  │  —          │
│  3D Viewer        │  Python 3.11 │  Dash 2 + Plotly    │  8050       │
│  RabbitMQ         │  Erlang      │  RabbitMQ 3.13      │  5672/15672 │
│  PostgreSQL       │  C           │  PostgreSQL 15      │  5435       │
│  Nginx            │  C           │  Nginx 1.25         │  5433       │
│  Prometheus       │  Go          │  Prometheus 2.x     │  —          │
│  Grafana          │  Go          │  Grafana 10.x       │  3003       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Odoo Addon — `foldiss_uav`

### Framework
| Item | Detail |
|---|---|
| Base | Odoo 18 Community |
| ORM | Odoo ORM (models.Model) |
| Views | XML form/list/kanban views |
| Frontend | Odoo Web Client (OWL 3) |
| Messaging | `mail.thread` mixin for status tracking |
| File storage | `ir.attachment` (PostgreSQL BLOB) |
| Queue client | `pika 1.3.2` (already in base-requirements) |

### Models created

**`uav.mission`**
```
id              Integer  PK
name            Char     required
log_file        Binary   stored as ir.attachment
log_filename    Char
status          Selection  draft/queued/parsing/parsed/ai_processing/done/error
user_id         Many2one → res.users
parse_result_id One2one  → uav.parse.result
ai_conclusion   Text
error_message   Text
create_date     Datetime (auto)
```

**`uav.parse.result`**
```
id                Integer  PK
mission_id        Many2one → uav.mission  (required, ondelete=cascade)
total_distance    Float    metres
max_h_speed       Float    m/s  (from GPS)
max_v_speed       Float    m/s  (from IMU trapz)
max_acceleration  Float    m/s²
max_altitude_gain Float    metres
flight_duration   Float    seconds
gps_count         Integer
imu_count         Integer
gps_sample_rate   Float    Hz
imu_sample_rate   Float    Hz
gps_points        Text     JSON  [{t, lat, lng, alt, spd}, …]
enu_points        Text     JSON  [{east, north, up}, …]
imu_data          Text     JSON  {times, vel_z, acc_magnitude}
```

### XML-RPC API (used by services)
```
URL:     http://odoo:8069
Methods: common.authenticate, object.execute_kw
Models:  uav.mission (read, write)
         uav.parse.result (create, read)
         ir.attachment (read)
```

---

## 3. Parser Worker

### Libraries

| Library | Version | Purpose |
|---|---|---|
| `pymavlink` | 2.4.x | Parse ArduPilot binary `.BIN` log files |
| `numpy` | 1.26.x | Array ops, trapz integration, statistics |
| `pika` | 1.3.2 | RabbitMQ AMQP consumer |
| `psycopg2-binary` | 2.9.x | Direct PG reads (fallback) |
| `python-dotenv` | 1.0.x | Environment config |

### Message format consumed (`uav.parse` queue)
```json
{
  "mission_id": 42,
  "attachment_id": 17
}
```

### Message format produced (`uav.ai` queue)
```json
{
  "mission_id": 42,
  "parse_result_id": 5
}
```

### Algorithms implemented (see spec.md §6 for full detail)

| Algorithm | File | Function |
|---|---|---|
| Haversine | `parser/metrics.py` | `haversine(lat1, lon1, lat2, lon2) → float` |
| Trapezoidal integration | `parser/metrics.py` | `trapz_velocity(acc, time) → np.ndarray` |
| WGS-84 → ENU | `parser/metrics.py` | `wgs84_to_enu(lat, lon, alt, lat0, lon0, alt0) → tuple` |
| Metric summary | `parser/metrics.py` | `compute_metrics(gps_df, imu_df) → dict` |
| Binary log parse | `parser/bin_parser.py` | `parse_bin(path) → (gps_df, imu_df)` |

### GPS message fields used
```
TimeUS  → timestamp (µs)
I       → receiver index (filter: == 0)
Status  → fix type (filter: >= 3)
Lat     → latitude (degrees × 1e-7 internally, returned as float degrees)
Lng     → longitude
Alt     → altitude MSL (metres)
Spd     → ground speed (m/s)
```

### IMU message fields used
```
TimeUS  → timestamp (µs)
I       → sensor index (filter: == 0)
AccX    → body-frame X acceleration (m/s²)
AccY    → body-frame Y acceleration (m/s²)
AccZ    → body-frame Z acceleration (m/s², ~−9.81 at rest)
```

---

## 4. AI Worker

### Model

| Item | Detail |
|---|---|
| Base model | `Qwen/Qwen2.5-1.5B-Instruct` (HuggingFace) |
| Size | ~3 GB (float32 on CPU) |
| Context length | 32 768 tokens |
| Reason for choice | Best quality/size ratio for CPU inference; strong instruction following; easy HF integration |

### Libraries

| Library | Version | Purpose |
|---|---|---|
| `transformers` | 4.45.x | Model loading + inference |
| `torch` | 2.3.x | CPU tensor ops |
| `peft` | 0.11.x | LoRA fine-tuning adapter |
| `trl` | 0.9.x | `SFTTrainer` for supervised fine-tuning |
| `datasets` | 2.20.x | Load `training_data.jsonl` |
| `accelerate` | 0.30.x | Training loop utilities |
| `pika` | 1.3.2 | RabbitMQ consumer |

### Fine-tuning config

| Parameter | Value | Reason |
|---|---|---|
| Method | LoRA (PEFT) | Trains only adapter weights (~0.5% of params), base model stays frozen |
| LoRA rank (r) | 8 | Good balance: expressiveness vs. size |
| LoRA alpha | 16 | Standard 2× rank scaling |
| Target modules | `q_proj`, `v_proj` | Attention layers — most impactful for instruction following |
| Dropout | 0.05 | Light regularisation for small dataset |
| Epochs | 3 | Sufficient for 50–100 examples |
| Batch size | 1 (grad accum 4) | CPU memory constraint |
| Max seq length | 512 | Prompt + conclusion fits comfortably |
| Dataset | `ai/training_data.jsonl` | Synthetic metric → conclusion pairs |
| Adapter output | `ai/lora_adapter/` | Auto-loaded at inference if present |

### Training data format (`training_data.jsonl`)
```jsonl
{"prompt": "Mission: test_flight_01\nDuration: 52.2 s\n...", "completion": "The flight lasted 52 seconds..."}
```

### Inference behaviour
- If `lora_adapter/` directory exists → load base + merge adapter
- Else → use base model directly (zero-shot, still good quality)
- Generation: `do_sample=False` (greedy) for reproducible reports
- Max new tokens: 512

---

## 5. 3D Viewer

### Libraries

| Library | Version | Purpose |
|---|---|---|
| `dash` | 2.17.x | Web app framework (Flask-based) |
| `plotly` | 5.22.x | Interactive 3D scatter / line chart |
| `psycopg2-binary` | 2.9.x | Direct PostgreSQL reads |
| `pandas` | 2.2.x | JSON → DataFrame for chart data |
| `dash-bootstrap-components` | 1.6.x | UI layout / cards |

### Visualisation spec

| Feature | Implementation |
|---|---|
| 3D trajectory | `go.Scatter3d(x=east, y=north, z=up, mode='lines+markers')` |
| Colour by speed | `marker.color=speed`, `colorscale='Viridis'` |
| Colour by time | toggle via Dash `RadioItems` |
| Hover data | timestamp, lat, lng, alt, speed |
| Metrics panel | Dash `dbc.Card` grid alongside the plot |
| Coordinate axes | East (m), North (m), Up (m) from ENU origin |
| Start/End markers | Distinct colour markers for first and last GPS point |
| Auto-refresh | Polling `/uav/api/mission/<id>` if status ≠ done |

---

## 6. Message Broker — RabbitMQ

| Item | Detail |
|---|---|
| Image | `rabbitmq:3.13-management` |
| Client lib | `pika 1.3.2` |
| Delivery mode | `PERSISTENT` (survives broker restart) |
| Prefetch count | 1 (one job at a time per worker) |
| Error strategy | NACK + no-requeue on exception → mission status = error |

---

## 7. Database — PostgreSQL 15

### Tables owned by Odoo ORM

| Table | Owner | Access |
|---|---|---|
| `uav_mission` | Odoo ORM | Odoo + Parser/AI via XML-RPC |
| `uav_parse_result` | Odoo ORM | Odoo + Viewer via direct PG |
| `ir_attachment` | Odoo core | Parser via XML-RPC read |

### Direct PG access (3D Viewer only)

The Viewer connects read-only to PostgreSQL to query `uav_parse_result.enu_points` and
`uav_parse_result.gps_points` (stored as JSON text). All writes go through Odoo XML-RPC only.

---

## 8. Infrastructure & Networking

### Docker networks
| Network | Services |
|---|---|
| `backend` (dev) | All containers |
| `backend-prod` | All prod containers |

### Docker Compose file layout
```
odoo/docker_compose/
├── db/           PostgreSQL + monitoring exporters
├── odoo/         Odoo 18 + Nginx + Promtail + Loki
├── pgadmin/      PgAdmin 4
├── adminer/      Adminer
├── rabbitmq/     RabbitMQ 3.13        ← new
├── parser/       Parser Worker        ← new
├── ai/           AI Worker            ← new
└── viewer/       3D Viewer (Dash)     ← new
```

### Environment variables (added to .env / env.example)
```bash
# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Odoo XML-RPC (used by services)
ODOO_URL=http://odoo:8069
ODOO_DB=postgres
ODOO_USER=admin
ODOO_PASSWORD=admin

# 3D Viewer
VIEWER_URL=http://localhost:8050

# AI model
HF_MODEL_NAME=Qwen/Qwen2.5-1.5B-Instruct
HF_CACHE_DIR=/app/model_cache
LORA_ADAPTER_PATH=/app/lora_adapter
```

---

## 9. Code Quality & Conventions

| Tool | Purpose | Config |
|---|---|---|
| `black` | Formatter | line-length 100 |
| `ruff` | Linter (replaces flake8) | pyproject.toml |
| `isort` | Import sorting | profile = black |
| `pylint-odoo` | Odoo-specific lint | .pre-commit.yaml |
| `mypy` | Type checking (services only) | strict = false |
| Python type hints | All function signatures in services | — |
| Odoo conventions | OCA coding guidelines for addon | — |

---

## 10. Why This Stack

| Decision | Alternative considered | Reason for choice |
|---|---|---|
| Odoo 18 | Django, FastAPI | Already running, auth/UI/storage built-in |
| pymavlink | dronekit, custom parser | Official ArduPilot library, handles all message types |
| Qwen2.5-1.5B | Phi-3.5-mini, TinyLlama, Mistral-7B | Best quality/size for CPU; fine-tune friendly; HF native |
| PEFT LoRA | Full fine-tune, QLoRA | CPU-compatible, tiny adapter, fast training |
| Dash + Plotly | Three.js, Streamlit | Python-native, Plotly 3D is production-grade, Dash for routing |
| RabbitMQ | Celery+Redis, direct HTTP | Already in requirements (pika installed); decouples UI from parsing |
| numpy trapz | scipy.integrate | Standard lib, shows manual implementation clearly for judges |
