# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Lexora** is a language-learning MVP platform for English, Greek, and Ukrainian. The primary codebase is under `odoo/`.

## Commands

All commands are run from `odoo/` and require a `.env` file (copy from `env.example`).

### Start / Stop
```bash
make up-all                          # Start db, Odoo, PgAdmin, Adminer (dev)
make up-all-no-cache                 # Same but rebuild images first
make up-all-without-monitoring-prod  # Production startup (no monitoring stack)
make down-all                        # Stop all services
make down-all-volumes                # Stop and delete volumes
```

### Odoo Management (exec inside container)
```bash
make migrations    # makemigrations 
make migrate       # migrate
make superuser     # createsuperuser
make collectstatic
make test          # Run tests
```

### Monitoring Stack (Elasticsearch + Kibana + APM)
```bash
make up-monitoring       # Start elastic/kibana/apm
make down-monitoring
make check-apm           # Check APM config
make test-apm            # Send test event to APM
```

### Logs
```bash
make logs-odoo
make logs-db
make logs-nginx
make logs-elastic
```

### Restore a DB backup
```bash
make load-backup FILE=your_backup_file.dump
```

## Architecture

### Service topology

```
Nginx (port 5433)
  └── Odoo 18 (port 8069)
        ├── PostgreSQL 15 (port 5435) — all business data
        ├── Redis — session cache, realtime
        ├── Elasticsearch — dashboards, trending words, analytics
        └── RabbitMQ — async bridge to FastAPI microservices
              ├── Translation Service (Argos Translate)
              ├── LLM Service (Qwen3 8B — synonyms, antonyms, sentences)
              └── Anki Import Service
```

Monitoring (optional): Prometheus → Grafana (port 3003), Loki → Promtail, cAdvisor.

### Docker Compose layout

Each service has its own compose file under `odoo/docker_compose/<service>/`. Dev files are `docker-compose.yml`; prod files are `docker-compose-prod.yml`. There are two Docker networks: `backend` (dev) and `backend-prod` (prod).

### Odoo addons (`src/addons/`)

| Addon | Purpose |
|---|---|
| `password_security` | Password policies, expiration, history, TOTP |
| `base_search_fuzzy` | Fuzzy search via PostgreSQL trigram extension |
| `web_notify` | Real-time user notifications |
| `website_require_login` | Force login on website pages |
| `website_menu_by_user_status` | Show/hide menu items by user role |

These follow OCA (Odoo Community Association) conventions. New custom addons go in `src/addons/`.

### Key Odoo modules planned (not yet implemented)

Per README architecture diagrams:
- `lexora_word` — word/phrase model, translations, enrichment
- `lexora_user` — user roles (Free / Premium / Admin)
- `lexora_chat` — real-time chat for practice
- `lexora_dashboard` — Elasticsearch-backed analytics views
- `lexora_anki` — Anki import via RabbitMQ

### Dev requirements (`requirements/dev-requirements.txt`)

`black`, `flake8`, `isort`, `ruff`, `bandit`, `pylint`, `pylint-odoo`, `mypy`, `yamllint`.

## Ports Reference

| Service | Port |
|---|---|
| App (Nginx → Odoo) | 5433 |
| PostgreSQL | 5435 |
| PgAdmin | 5050 |
| Grafana | 3003 |
| Loki | 3100 |
| Kibana | 5601 |
