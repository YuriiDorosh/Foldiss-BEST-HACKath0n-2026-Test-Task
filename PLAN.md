# Foldiss UAV — Implementation Plan

> Monorepo. 5 top-level services. 42 files total (34 create, 5 modify, 3 infra).

---

## Monorepo Structure

```
Foldiss-BEST-HACKath0n-2026-Test-Task/   ← repo root
├── odoo/               Odoo 18 + foldiss_uav addon     (existing, extend)
├── parser/             Parser Worker — Python service   (create)
├── ai/                 AI Worker — Python service        (create)
├── frontend/           3D Viewer — React + Plotly.js     (create)
├── docker-compose.yml  Root orchestration                (create)
├── Makefile            Root make targets                 (create)
├── spec.md             ✓ done
├── tech-stack.md       ✓ done
└── PLAN.md             ✓ this file
```

RabbitMQ and PostgreSQL are shared infrastructure — defined in the root `docker-compose.yml`.

---

## Dependency Order

```
Phase 0 — Root infra (docker-compose, Makefile, .env, RabbitMQ)
    ↓
Phase 1 — Odoo addon foldiss_uav  (defines DB schema + API endpoints)
    ↓
Phase 2 — Parser Worker           (algorithms: haversine, trapz, ENU — 60% of grade)
    ↓
Phase 3 — Frontend                (3D viewer calling Odoo API)
    ↓
Phase 4 — AI Worker               (conclusion generation — 15% of grade)
```

---

## Phase 0 — Root Infrastructure
> Creates the monorepo skeleton every other service depends on.

### Step 0.1 — Root `.env` (modify `odoo/.env`, create root `.env`)

The root `.env` is shared by all docker-compose files. Copy `odoo/.env` to root and append:

```env
# PostgreSQL (existing)
POSTGRES_DB=postgres
POSTGRES_USER=odoo
POSTGRES_PASSWORD=<keep existing value>
NGINX_PORT=5433

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Odoo XML-RPC — used by parser + AI workers
ODOO_URL=http://odoo:8069
ODOO_DB=postgres
ODOO_USER=admin
ODOO_PASSWORD=admin

# Frontend
VITE_ODOO_URL=http://localhost:5433

# AI model
HF_MODEL_NAME=Qwen/Qwen2.5-1.5B-Instruct
HF_CACHE_DIR=/app/model_cache
LORA_ADAPTER_PATH=/app/lora_adapter
```

⚠️ `ODOO_USER/PASSWORD` = Odoo app admin credentials, NOT PostgreSQL.
⚠️ Also append the new vars to `odoo/.env` so the Odoo Makefile still works.

---

### Step 0.2 — Root `docker-compose.yml`
**File:** `docker-compose.yml` (create at repo root)

```yaml
version: '3.8'

services:
  # ── Infrastructure ──────────────────────────────────
  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: rabbitmq
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - backend

  # ── Services ────────────────────────────────────────
  parser:
    build:
      context: ./parser
    container_name: parser
    restart: unless-stopped
    env_file: .env
    depends_on:
      - rabbitmq
    networks:
      - backend

  ai_worker:
    build:
      context: ./ai
    container_name: ai_worker
    restart: unless-stopped
    env_file: .env
    volumes:
      - ai_model_cache:/app/model_cache
      - ai_lora_adapter:/app/lora_adapter
    depends_on:
      - rabbitmq
    networks:
      - backend

  frontend:
    build:
      context: ./frontend
    container_name: frontend
    restart: unless-stopped
    ports:
      - "3000:80"
    networks:
      - backend

volumes:
  rabbitmq_data:
  ai_model_cache:
  ai_lora_adapter:

networks:
  backend:
    external: true
```

⚠️ Odoo + PostgreSQL are still managed by `odoo/Makefile` (existing setup — don't change it).
⚠️ `backend` network must be created first: `docker network create backend`.

---

### Step 0.3 — Root `Makefile`
**File:** `Makefile` (create at repo root)

```makefile
DC = docker compose
ENV = --env-file .env
NETWORK = backend

check-network:
	@docker network ls | grep -q $(NETWORK) || docker network create $(NETWORK)

# Odoo (delegates to existing Makefile)
up-odoo:
	$(MAKE) -C odoo up-all

down-odoo:
	$(MAKE) -C odoo down-all

# New services
up-services: check-network
	$(DC) $(ENV) up -d

up-services-build: check-network
	$(DC) $(ENV) up -d --build

down-services:
	$(DC) down

# Full stack
up-all: check-network
	$(MAKE) -C odoo up-all
	$(DC) $(ENV) up -d

down-all:
	$(MAKE) -C odoo down-all
	$(DC) down

# Logs
logs-parser:
	docker logs -f parser

logs-ai:
	docker logs -f ai_worker

logs-frontend:
	docker logs -f frontend

logs-rabbitmq:
	docker logs -f rabbitmq
```

---

### Step 0.4 — Update `odoo/requirements/base-requirements.txt`
**File:** `odoo/requirements/base-requirements.txt` (modify)

Add:
```
pymavlink==2.4.41
```

---

## Phase 1 — Odoo Addon `foldiss_uav`
> Central hub. Defines DB schema + exposes HTTP API that frontend and workers use.

### Files to create (10 files):

```
odoo/src/addons/foldiss_uav/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── uav_mission.py
│   └── uav_parse_result.py
├── security/
│   └── ir.model.access.csv
├── views/
│   ├── uav_mission_views.xml
│   └── menus.xml
└── controllers/
    ├── __init__.py
    └── main.py
```

---

### Step 1.1 — `__init__.py`
```python
from . import controllers, models
```

---

### Step 1.2 — `__manifest__.py`
```python
{
    "name": "Foldiss UAV Flight Analysis",
    "summary": "Parse ArduPilot .BIN logs, compute metrics, 3D trajectory, AI analysis",
    "version": "18.0.1.0.0",
    "category": "Operations",
    "author": "Foldiss",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/ir.model.access.csv",  # must be first
        "views/uav_mission_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
```

---

### Step 1.3 — `models/__init__.py`
```python
from . import uav_mission
from . import uav_parse_result
```

---

### Step 1.4 — `models/uav_mission.py`

Key details:
- `_inherit = ["mail.thread"]` — chatter + status tracking
- `log_file = fields.Binary(attachment=True)` — stores via `ir.attachment`
- Status flow: `draft → queued → parsing → parsed → ai_processing → done / error`
- Related display fields pulling from parse_result:
  ```python
  result_total_distance = fields.Float(related="parse_result_id.total_distance", readonly=True)
  result_max_h_speed    = fields.Float(related="parse_result_id.max_h_speed", readonly=True)
  # ... all metrics
  ```
- `action_start_parsing()`:
  1. Validate file + `.bin` extension
  2. Find attachment: `env['ir.attachment'].search([('res_model','=','uav.mission'), ('res_field','=','log_file'), ('res_id','=',self.id)], limit=1)`
  3. Publish `{"mission_id": self.id, "attachment_id": att.id}` → `uav.parse` queue
  4. `self.status = 'queued'`
  5. Catch pika errors → `status = 'error'`
- `action_open_viewer()` → `ir.actions.act_url` to `http://localhost:3000/mission/<id>`
- `_publish_to_queue(queue, payload)` — pika BlockingConnection, timeout=5s, durable, delivery_mode=2

---

### Step 1.5 — `models/uav_parse_result.py`

```
mission_id        Many2one → uav.mission   ondelete=cascade
total_distance    Float    metres
max_h_speed       Float    m/s (GPS)
max_v_speed       Float    m/s (IMU trapz)
max_acceleration  Float    m/s²
max_altitude_gain Float    metres
flight_duration   Float    seconds
gps_count         Integer
imu_count         Integer
gps_sample_rate   Float    Hz
imu_sample_rate   Float    Hz
gps_points        Text     JSON: [{t,lat,lng,alt,spd}, ...]
enu_points        Text     JSON: [{east,north,up}, ...]
imu_data          Text     JSON: {times, vel_z, acc_magnitude}
```

---

### Step 1.6 — `security/ir.model.access.csv`
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_uav_mission_user,uav.mission user,model_uav_mission,base.group_user,1,1,1,1
access_uav_parse_result_user,uav.parse.result user,model_uav_parse_result,base.group_user,1,1,1,0
```

---

### Step 1.7 — `views/uav_mission_views.xml`

Form view structure:
- `<header>`: statusbar + "Start Parsing" (visible: `status == 'draft'`) + "Open 3D Viewer" (visible: `status == 'done'`)
- File upload: `<field name="log_file" filename="log_filename"/>`
- Metrics group with related fields (all readonly)
- Notebook: "Metrics" page + "AI Conclusion" page
- `<chatter/>` at bottom
- Odoo 18 syntax: `invisible="status != 'draft'"` (not `attrs=`)

List view:
- Status with `widget="badge"` + `decoration-success`, `decoration-danger`

Action: `ir.actions.act_window`, `view_mode="list,form"`

---

### Step 1.8 — `views/menus.xml`
```xml
<menuitem id="uav_menu_root" name="UAV Flights"/>
<menuitem id="uav_menu_missions" name="Missions"
          parent="uav_menu_root" action="uav_mission_action" sequence="10"/>
```

---

### Step 1.9 — `controllers/__init__.py`
```python
from . import main
```

---

### Step 1.10 — `controllers/main.py`

Three endpoints:

**1. `POST /uav/webhook`** — `auth="none"`, `csrf=False`, `type="json"`
Called by parser/AI workers to update mission status.
```
body: {mission_id, status, error_message?, parse_result_id?}
→ mission.sudo().write(vals)
→ returns {success: true}
```

**2. `GET /uav/api/mission/<int:id>`** — `auth="none"`, `type="json"`
Frontend polling endpoint (status check).
```
→ {id, name, status, ai_conclusion}
```

**3. `GET /uav/api/mission/<int:id>/trajectory`** — `auth="none"`, `type="json"`
Frontend data endpoint (full trajectory + metrics for 3D plot).
```
→ {
    id, name, status, ai_conclusion,
    total_distance, max_h_speed, max_v_speed,
    max_acceleration, max_altitude_gain, flight_duration,
    gps_count, imu_count,
    gps_points: [{t,lat,lng,alt,spd}, ...],
    enu_points: [{east,north,up}, ...]
  }
```

⚠️ All endpoints use `sudo()` because `auth="none"`.
⚠️ Add `Access-Control-Allow-Origin: *` response header for CORS (frontend on port 3000).

---

### ✅ Phase 1 Verification
```bash
cd odoo && make up-all
# Odoo → Apps → install "Foldiss UAV Flight Analysis"
# UAV Flights menu appears
# Create mission → upload 00000001.BIN → Start Parsing
# Expect "RabbitMQ not available" error → mission status = error (graceful)
# curl http://localhost:5433/uav/api/mission/1/trajectory → JSON response
```

---

## Phase 2 — Parser Worker
> Highest-value component. All 3 mandatory algorithms live here.
> Build bottom-up: pure functions → Odoo client → consumer → Docker.

### Files to create (8 files):

```
parser/
├── parser/
│   ├── __init__.py
│   ├── bin_parser.py       ← pymavlink parsing
│   ├── metrics.py          ← haversine + trapz + WGS84→ENU  ★ 20% of grade
│   └── odoo_client.py      ← XML-RPC wrapper
├── main.py                 ← RabbitMQ consumer
├── requirements.txt
└── Dockerfile
```

---

### Step 2.1 — `parser/metrics.py` ★

**`haversine(lat1, lon1, lat2, lon2) -> float`** (metres)
```python
import math
R = 6_371_000.0
phi1, phi2 = math.radians(lat1), math.radians(lat2)
dphi    = math.radians(lat2 - lat1)
dlambda = math.radians(lon2 - lon1)
a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

**`trapz_velocity(acc_z, time_s) -> np.ndarray`**
```python
import numpy as np
acc_z_debiased = acc_z - np.mean(acc_z)   # remove ~9.81 gravity bias
vel_z = np.zeros(len(time_s))
for i in range(1, len(time_s)):            # explicit loop — judges see the algorithm
    dt = time_s[i] - time_s[i - 1]
    vel_z[i] = vel_z[i-1] + 0.5 * (acc_z_debiased[i-1] + acc_z_debiased[i]) * dt
return vel_z
```

**`wgs84_to_enu(lat, lon, alt, lat0, lon0, alt0) -> tuple[float,float,float]`**
```python
R = 6_378_137.0   # WGS-84 semi-major axis
east  = R * math.radians(lon - lon0) * math.cos(math.radians(lat0))
north = R * math.radians(lat - lat0)
up    = alt - alt0
return east, north, up
```

**`compute_all_metrics(gps, imu) -> dict`**
```
total_distance    ← sum haversine(consecutive GPS pairs)
max_h_speed       ← max(rec['Spd'])   from GPS field directly
max_v_speed       ← max(|vel_z|)      from trapz_velocity(AccZ, t)
max_acceleration  ← max(‖acc‖ - 9.81) from IMU (magnitude minus gravity)
max_altitude_gain ← max(Alt) - min(Alt)
flight_duration   ← (last_TimeUS - first_TimeUS) / 1e6
gps_sample_rate   ← len(gps) / flight_duration
imu_sample_rate   ← len(imu) / imu_duration
gps_points        ← [{t, lat, lng, alt, spd}, ...]
enu_points        ← [{east, north, up}, ...]  ← wgs84_to_enu per GPS point
imu_data          ← {times, vel_z, acc_magnitude}  lists
```
⚠️ Assert `len(gps_points) == len(enu_points)` before returning.
⚠️ Add docstring explaining each formula — judges read this code.

---

### Step 2.2 — `parser/bin_parser.py`
```python
from pymavlink import mavutil

def parse_bin(path: str) -> tuple[list[dict], list[dict]]:
    mlog = mavutil.mavlink_connection(path)
    gps, imu = [], []
    while True:
        msg = mlog.recv_match(type=['GPS', 'IMU'])
        if msg is None:
            break
        d = msg.to_dict()
        if msg.get_type() == 'GPS':
            if d.get('I', 1) == 0 and d.get('Status', 0) >= 3:
                gps.append({k: d[k] for k in ('TimeUS','Lat','Lng','Alt','Spd')})
        elif msg.get_type() == 'IMU':
            if d.get('I', 1) == 0:
                imu.append({k: d[k] for k in ('TimeUS','AccX','AccY','AccZ')})
    return gps, imu
```

---

### Step 2.3 — `parser/odoo_client.py`
```python
import base64, xmlrpc.client

class OdooClient:
    def __init__(self, url, db, user, password):
        self.db, self.password = db, password
        common       = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.models  = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        self.uid     = common.authenticate(db, user, password, {})

    def execute(self, model, method, *args, **kw):
        return self.models.execute_kw(self.db, self.uid, self.password,
                                      model, method, list(args), kw)

    def read_attachment(self, att_id: int) -> bytes:
        r = self.execute("ir.attachment", "read", [att_id], fields=["datas"])
        return base64.b64decode(r[0]["datas"])

    def update_mission(self, mid: int, vals: dict):
        self.execute("uav.mission", "write", [mid], vals)

    def create_parse_result(self, vals: dict) -> int:
        return self.execute("uav.parse.result", "create", vals)
```

---

### Step 2.4 — `parser/__init__.py`
```python
from .bin_parser import parse_bin
from .metrics import compute_all_metrics
from .odoo_client import OdooClient
```

---

### Step 2.5 — `parser/main.py`
```
Startup:
  - Retry OdooClient connect (5s sleep, 12 attempts) — Odoo may not be ready
  - Retry pika connect (5s sleep, 12 attempts) — RabbitMQ may not be ready
  - channel.basic_qos(prefetch_count=1)
  - channel.basic_consume(queue='uav.parse', on_message_callback=callback)

callback(ch, method, props, body):
  data = json.loads(body)
  mission_id, attachment_id = data['mission_id'], data['attachment_id']
  try:
    odoo.update_mission(mission_id, {status: 'parsing'})
    raw = odoo.read_attachment(attachment_id)
    write to /tmp/<mission_id>.bin
    gps, imu = parse_bin(tmp_path)
    metrics = compute_all_metrics(gps, imu)
    result_id = odoo.create_parse_result({
        mission_id: mission_id,
        **scalar_metrics,
        gps_points: json.dumps(metrics['gps_points']),
        enu_points: json.dumps(metrics['enu_points']),
        imu_data:   json.dumps(metrics['imu_data']),
    })
    odoo.update_mission(mission_id, {status:'parsed', parse_result_id:result_id})
    publish {mission_id, parse_result_id} → uav.ai queue
    ch.basic_ack(delivery_tag=method.delivery_tag)
  except Exception as e:
    odoo.update_mission(mission_id, {status:'error', error_message:str(e)})
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
```

⚠️ `pika.ConnectionParameters(heartbeat=600)` on all connections.
⚠️ Scalar metrics = everything except `gps_points`, `enu_points`, `imu_data`.

---

### Step 2.6 — `parser/requirements.txt`
```
pymavlink==2.4.41
numpy==1.26.4
pika==1.3.2
python-dotenv==1.0.1
```

---

### Step 2.7 — `parser/Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY parser/ ./parser/
CMD ["python", "main.py"]
```

---

### ✅ Phase 2 Verification
```bash
docker compose up -d rabbitmq parser
docker logs -f parser   # → "Waiting for messages on uav.parse"
# Odoo → Start Parsing on mission with 00000001.BIN
# parser logs → "Parsed 262 GPS, 2628 IMU | duration=52.2s | dist=~2847m"
# Mission status → parsed, metrics populated
```

---

## Phase 3 — Frontend (React + Plotly.js)
> Separate SPA. Calls Odoo API for data. 3D trajectory visualization.

### Files to create (9 files):

```
frontend/
├── src/
│   ├── api/
│   │   └── odoo.js          ← fetch wrapper for Odoo endpoints
│   ├── components/
│   │   ├── Trajectory3D.jsx ← Plotly 3D scatter chart
│   │   ├── MetricsPanel.jsx ← stats cards
│   │   └── AiConclusion.jsx ← AI text panel
│   ├── pages/
│   │   └── MissionPage.jsx  ← route /mission/:id
│   ├── App.jsx
│   └── main.jsx
├── index.html
├── package.json
├── vite.config.js
└── Dockerfile
```

---

### Step 3.1 — `frontend/package.json`
```json
{
  "name": "foldiss-uav-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.23.0",
    "plotly.js": "^2.32.0",
    "react-plotly.js": "^2.6.0",
    "bootstrap": "^5.3.3"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.3.0"
  }
}
```

---

### Step 3.2 — `frontend/vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/uav': 'http://localhost:5433',  // proxy Odoo API calls in dev
    }
  }
})
```

---

### Step 3.3 — `frontend/src/api/odoo.js`
```js
const BASE = import.meta.env.VITE_ODOO_URL || ''

export async function getMissionTrajectory(id) {
  const r = await fetch(`${BASE}/uav/api/mission/${id}/trajectory`, {
    method: 'POST',   // Odoo json type routes use POST
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
  })
  const data = await r.json()
  return data.result
}

export async function getMissionStatus(id) {
  const r = await fetch(`${BASE}/uav/api/mission/${id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
  })
  const data = await r.json()
  return data.result
}
```

---

### Step 3.4 — `frontend/src/components/Trajectory3D.jsx`
```jsx
import Plot from 'react-plotly.js'

export default function Trajectory3D({ enuPoints, gpsPoints }) {
  const east  = enuPoints.map(p => p.east)
  const north = enuPoints.map(p => p.north)
  const up    = enuPoints.map(p => p.up)
  const speed = gpsPoints.map(p => p.spd)

  const trace = {
    type: 'scatter3d', mode: 'lines+markers',
    x: east, y: north, z: up,
    marker: { size: 3, color: speed, colorscale: 'Viridis',
              colorbar: { title: 'Speed (m/s)' }, opacity: 0.85 },
    line:   { color: 'rgba(150,150,150,0.3)', width: 2 },
    hovertemplate: 'E: %{x:.1f}m  N: %{y:.1f}m  Up: %{z:.1f}m<br>Speed: %{marker.color:.1f} m/s<extra></extra>',
  }

  // Start / end markers
  const startMarker = {
    type: 'scatter3d', mode: 'markers', name: 'Start',
    x: [east[0]], y: [north[0]], z: [up[0]],
    marker: { size: 9, color: 'lime', symbol: 'diamond' },
  }
  const endMarker = {
    type: 'scatter3d', mode: 'markers', name: 'End',
    x: [east.at(-1)], y: [north.at(-1)], z: [up.at(-1)],
    marker: { size: 9, color: 'red', symbol: 'diamond' },
  }

  return (
    <Plot
      data={[trace, startMarker, endMarker]}
      layout={{
        scene: { xaxis: { title: 'East (m)' },
                 yaxis: { title: 'North (m)' },
                 zaxis: { title: 'Up (m)' } },
        template: 'plotly_dark',
        margin: { l: 0, r: 0, t: 30, b: 0 },
        height: 650,
      }}
      style={{ width: '100%' }}
      config={{ displaylogo: false }}
    />
  )
}
```

---

### Step 3.5 — `frontend/src/components/MetricsPanel.jsx`
```jsx
export default function MetricsPanel({ data }) {
  const metrics = [
    ['Total Distance',   `${data.total_distance?.toFixed(0)} m`],
    ['Max Speed (GPS)',  `${data.max_h_speed?.toFixed(2)} m/s`],
    ['Max V-Speed',      `${data.max_v_speed?.toFixed(2)} m/s`],
    ['Max Accel',        `${data.max_acceleration?.toFixed(2)} m/s²`],
    ['Altitude Gain',    `${data.max_altitude_gain?.toFixed(1)} m`],
    ['Duration',         `${data.flight_duration?.toFixed(1)} s`],
    ['GPS Points',       data.gps_count],
    ['IMU Samples',      data.imu_count],
  ]
  return (
    <div className="row g-2 mb-3">
      {metrics.map(([label, val]) => (
        <div key={label} className="col-6 col-md-3">
          <div className="card bg-dark text-white h-100">
            <div className="card-body py-2">
              <small className="text-muted">{label}</small>
              <div className="fw-bold fs-5">{val}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
```

---

### Step 3.6 — `frontend/src/components/AiConclusion.jsx`
```jsx
export default function AiConclusion({ text }) {
  if (!text) return null
  return (
    <div className="card bg-dark text-white mt-3">
      <div className="card-header">AI Flight Analysis</div>
      <div className="card-body">
        <p className="mb-0" style={{ whiteSpace: 'pre-wrap' }}>{text}</p>
      </div>
    </div>
  )
}
```

---

### Step 3.7 — `frontend/src/pages/MissionPage.jsx`
```jsx
import { useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getMissionTrajectory, getMissionStatus } from '../api/odoo'
import Trajectory3D from '../components/Trajectory3D'
import MetricsPanel from '../components/MetricsPanel'
import AiConclusion from '../components/AiConclusion'

const TERMINAL = ['done', 'error']

export default function MissionPage() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let timer
    async function load() {
      try {
        const d = await getMissionTrajectory(id)
        setData(d)
        if (!TERMINAL.includes(d?.status)) {
          timer = setTimeout(load, 3000)   // poll until done
        }
      } catch (e) { setError(e.message) }
    }
    load()
    return () => clearTimeout(timer)
  }, [id])

  if (error) return <div className="text-danger p-4">{error}</div>
  if (!data)  return <div className="text-white p-4">Loading...</div>

  const { enu_points, gps_points, name, status } = data
  const ready = enu_points && gps_points && enu_points.length > 0

  return (
    <div className="container-fluid p-4">
      <h2 className="text-white mb-1">{name}</h2>
      <span className="badge bg-secondary mb-3">{status}</span>
      <MetricsPanel data={data} />
      {ready
        ? <Trajectory3D enuPoints={enu_points} gpsPoints={gps_points} />
        : <div className="text-muted">Parsing in progress...</div>
      }
      <AiConclusion text={data.ai_conclusion} />
    </div>
  )
}
```

---

### Step 3.8 — `frontend/src/App.jsx`
```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import 'bootstrap/dist/css/bootstrap.min.css'
import MissionPage from './pages/MissionPage'

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ background: '#111', minHeight: '100vh' }}>
        <Routes>
          <Route path="/mission/:id" element={<MissionPage />} />
          <Route path="/" element={<div className="text-white p-4">Foldiss UAV Platform</div>} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
```

---

### Step 3.9 — `frontend/Dockerfile`
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

`nginx.conf` (simple SPA config):
```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
}
```

---

### ✅ Phase 3 Verification
```bash
# Dev mode (fastest):
cd frontend && npm install && npm run dev
# Visit http://localhost:5173/mission/1

# Or Docker:
docker compose up -d frontend
# Visit http://localhost:3000/mission/1
# 3D plot renders with Viridis coloring + start/end markers
# Metrics cards show correct values
```

---

## Phase 4 — AI Worker
> Lower priority (15% of grade). Build last. CPU inference ~30-60s per request.

### Files to create (10 files):

```
ai/
├── ai/
│   ├── __init__.py
│   ├── model.py           ← Qwen2.5-1.5B load + LoRA merge + generate
│   ├── prompt.py          ← prompt builder
│   ├── odoo_client.py     ← XML-RPC (copy from parser, add read_parse_result)
│   ├── training_data.jsonl ← 15-20 synthetic examples
│   └── finetune.py        ← LoRA fine-tuning script (run manually)
├── main.py                ← RabbitMQ consumer
├── requirements.txt
└── Dockerfile
```

---

### Step 4.1 — `ai/prompt.py`
```python
SYSTEM = "You are a UAV flight data analyst. Write a concise technical report (5-8 sentences). Identify anomalies, performance highlights, and safety concerns."

def build_prompt(m: dict) -> str:
    return (
        f"Mission: {m.get('name','Unknown')}\n"
        f"Duration: {m['flight_duration']:.1f} s\n"
        f"Total distance: {m['total_distance']:.0f} m\n"
        f"Max horizontal speed (GPS): {m['max_h_speed']:.2f} m/s\n"
        f"Max vertical speed (IMU trapz): {m['max_v_speed']:.2f} m/s\n"
        f"Max acceleration: {m['max_acceleration']:.2f} m/s2\n"
        f"Max altitude gain: {m['max_altitude_gain']:.1f} m\n"
        f"GPS fix points: {m['gps_count']}\n"
        f"IMU samples: {m['imu_count']}\n\n"
        "Provide your analysis:"
    )
```

---

### Step 4.2 — `ai/model.py`
```python
import os
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

def load_model():
    name      = os.environ.get("HF_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
    cache_dir = os.environ.get("HF_CACHE_DIR", "/app/model_cache")
    lora_path = os.environ.get("LORA_ADAPTER_PATH", "/app/lora_adapter")

    tokenizer = AutoTokenizer.from_pretrained(name, cache_dir=cache_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(name, cache_dir=cache_dir,
                                                  trust_remote_code=True,
                                                  torch_dtype="float32", device_map="cpu")
    if os.path.isdir(lora_path) and os.listdir(lora_path):
        model = PeftModel.from_pretrained(model, lora_path).merge_and_unload()

    return model, tokenizer

def generate(model, tokenizer, system: str, user: str) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user",   "content": user}]
    text   = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    out    = model.generate(**inputs, max_new_tokens=512, do_sample=False,
                            pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
```

⚠️ Model loaded ONCE at startup — never per-request.
⚠️ `trust_remote_code=True` required for Qwen.

---

### Step 4.3 — `ai/odoo_client.py`
Same as `parser/odoo_client.py` + one extra method:
```python
def read_parse_result(self, result_id: int) -> dict:
    fields = ['mission_id','total_distance','max_h_speed','max_v_speed',
              'max_acceleration','max_altitude_gain','flight_duration','gps_count','imu_count']
    r = self.execute("uav.parse.result", "read", [result_id], fields=fields)
    return r[0] if r else {}

def read_mission_name(self, mission_id: int) -> str:
    r = self.execute("uav.mission", "read", [mission_id], fields=["name"])
    return r[0]["name"] if r else "Unknown"
```

---

### Step 4.4-4.5 — `ai/__init__.py` + `ai/training_data.jsonl`

`__init__.py`: standard imports.

`training_data.jsonl`: 15-20 examples covering:
- Normal fixed-wing flight
- Short test hop (23s, low GPS count)
- High-acceleration anomaly (>15 m/s²)
- Large altitude variation (>500m gain)
- Low GPS fix count (<50 points)
- Long endurance flight (>120s)

Format per line:
```json
{"prompt": "Mission: sim_01\nDuration: 52.2 s\n...\nProvide your analysis:", "completion": "This flight..."}
```

---

### Step 4.6 — `ai/finetune.py` (run manually, not in Docker)
```python
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

lora_cfg = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                      target_modules=["q_proj","v_proj"],
                      task_type=TaskType.CAUSAL_LM)
# Load base → apply LoRA → SFTTrainer → save to ./lora_adapter/
# SFTConfig: epochs=3, per_device_train_batch_size=1,
#            gradient_accumulation_steps=4, max_seq_length=512
```

Output: `ai/lora_adapter/` → mount into Docker volume `ai_lora_adapter`.

---

### Step 4.7 — `ai/main.py`
```
Startup (with retry loop):
  - Connect OdooClient
  - Load model (may take 2-5 min on CPU — log progress)
  - Connect pika with heartbeat=600
  - consume uav.ai queue

callback:
  1. metrics = odoo.read_parse_result(parse_result_id)
  2. metrics["name"] = odoo.read_mission_name(mission_id)
  3. odoo.update_mission(mission_id, {status: "ai_processing"})
  4. conclusion = generate(model, tokenizer, SYSTEM, build_prompt(metrics))
  5. odoo.update_mission(mission_id, {ai_conclusion: conclusion, status: "done"})
  6. ack
```

⚠️ `heartbeat=600` — CPU inference takes 30-60s, default heartbeat (60s) will disconnect.

---

### Step 4.8-4.10 — `ai/requirements.txt`, `Dockerfile`

**requirements.txt:**
```
transformers>=4.45.0
peft>=0.11.0
trl>=0.9.0
datasets>=2.20.0
accelerate>=0.30.0
pika==1.3.2
python-dotenv==1.0.1
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Install CPU-only torch first (avoids 2GB+ CUDA download)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY ai/ ./ai/
CMD ["python", "main.py"]
```

---

### ✅ Phase 4 Verification
```bash
docker compose up -d ai_worker
docker logs -f ai_worker   # wait for "Model loaded. Listening on uav.ai..."
# Run full mission parse → watch ai_worker consume uav.ai queue
# Mission in Odoo: status = done, ai_conclusion populated
# Frontend /mission/<id>: AI Analysis panel appears below 3D plot
```

---

## Complete File List (42 files)

### Phase 0 — Infrastructure (5 files)
| # | Action | Path |
|---|--------|------|
| 1 | CREATE | `.env` (root) |
| 2 | MODIFY | `odoo/.env` |
| 3 | CREATE | `docker-compose.yml` (root) |
| 4 | CREATE | `Makefile` (root) |
| 5 | MODIFY | `odoo/requirements/base-requirements.txt` |

### Phase 1 — Odoo Addon (10 files)
| # | Action | Path |
|---|--------|------|
| 6  | CREATE | `odoo/src/addons/foldiss_uav/__init__.py` |
| 7  | CREATE | `odoo/src/addons/foldiss_uav/__manifest__.py` |
| 8  | CREATE | `odoo/src/addons/foldiss_uav/models/__init__.py` |
| 9  | CREATE | `odoo/src/addons/foldiss_uav/models/uav_mission.py` |
| 10 | CREATE | `odoo/src/addons/foldiss_uav/models/uav_parse_result.py` |
| 11 | CREATE | `odoo/src/addons/foldiss_uav/security/ir.model.access.csv` |
| 12 | CREATE | `odoo/src/addons/foldiss_uav/views/uav_mission_views.xml` |
| 13 | CREATE | `odoo/src/addons/foldiss_uav/views/menus.xml` |
| 14 | CREATE | `odoo/src/addons/foldiss_uav/controllers/__init__.py` |
| 15 | CREATE | `odoo/src/addons/foldiss_uav/controllers/main.py` |

### Phase 2 — Parser Worker (8 files)
| # | Action | Path |
|---|--------|------|
| 16 | CREATE | `parser/parser/__init__.py` |
| 17 | CREATE | `parser/parser/metrics.py` |
| 18 | CREATE | `parser/parser/bin_parser.py` |
| 19 | CREATE | `parser/parser/odoo_client.py` |
| 20 | CREATE | `parser/main.py` |
| 21 | CREATE | `parser/requirements.txt` |
| 22 | CREATE | `parser/Dockerfile` |
| 23 | MODIFY | `docker-compose.yml` (parser service already included) |

### Phase 3 — Frontend (9 files)
| # | Action | Path |
|---|--------|------|
| 24 | CREATE | `frontend/package.json` |
| 25 | CREATE | `frontend/vite.config.js` |
| 26 | CREATE | `frontend/index.html` |
| 27 | CREATE | `frontend/src/api/odoo.js` |
| 28 | CREATE | `frontend/src/components/Trajectory3D.jsx` |
| 29 | CREATE | `frontend/src/components/MetricsPanel.jsx` |
| 30 | CREATE | `frontend/src/components/AiConclusion.jsx` |
| 31 | CREATE | `frontend/src/pages/MissionPage.jsx` |
| 32 | CREATE | `frontend/src/App.jsx` |
| 33 | CREATE | `frontend/src/main.jsx` |
| 34 | CREATE | `frontend/Dockerfile` |
| 35 | CREATE | `frontend/nginx.conf` |

### Phase 4 — AI Worker (10 files)
| # | Action | Path |
|---|--------|------|
| 36 | CREATE | `ai/ai/__init__.py` |
| 37 | CREATE | `ai/ai/prompt.py` |
| 38 | CREATE | `ai/ai/model.py` |
| 39 | CREATE | `ai/ai/odoo_client.py` |
| 40 | CREATE | `ai/ai/training_data.jsonl` |
| 41 | CREATE | `ai/ai/finetune.py` |
| 42 | CREATE | `ai/main.py` |
| 43 | CREATE | `ai/requirements.txt` |
| 44 | CREATE | `ai/Dockerfile` |

---

## Risk Register

| Risk | Mitigation |
|---|---|
| RabbitMQ not ready at worker startup | Retry loop: 12 attempts × 5s sleep |
| Odoo not ready at worker startup | Same retry loop for XML-RPC connect |
| pika timeout during AI inference (60s default) | `heartbeat=600` on all connections |
| AI model 3GB re-downloads on restart | Named Docker volume `ai_model_cache` |
| Odoo Binary attachment not found | Search by `res_model + res_field + res_id` |
| `gps_points` ≠ `enu_points` length | Assert in `compute_all_metrics` before return |
| numpy cumtrapz API changed in v2 | Implement trapz manually with for loop |
| CORS error (frontend port 3000 → Odoo 5433) | Vite proxy in dev; CORS header in Odoo controller |
| Odoo admin user not created | Must init Odoo DB first before starting workers |
