DC      = docker compose
ENV     = --env-file .env
NETWORK = backend

# ─────────────────────────────────────────────────────────────────────────────
.PHONY: check-network \
        up-all up-all-build down-all \
        up-services up-services-build down-services \
        up-odoo down-odoo \
        up-rabbitmq down-rabbitmq logs-rabbitmq \
        up-parser up-parser-build down-parser logs-parser \
        up-ai up-ai-build down-ai logs-ai \
        up-frontend up-frontend-build down-frontend logs-frontend \
        logs-all help \
        ultra init-odoo download-model

# ─────────────────────────────────────────────────────────────────────────────
# Network
# ─────────────────────────────────────────────────────────────────────────────
check-network:
	@docker network ls | grep -q $(NETWORK) \
		&& echo "Network '$(NETWORK)' already exists." \
		|| (echo "Creating network '$(NETWORK)'..." && docker network create $(NETWORK))

# ─────────────────────────────────────────────────────────────────────────────
# Odoo stack (delegates to odoo/Makefile)
# ─────────────────────────────────────────────────────────────────────────────
up-odoo: check-network
	$(MAKE) -C odoo up-all

down-odoo:
	$(MAKE) -C odoo down-all

# ─────────────────────────────────────────────────────────────────────────────
# New services (RabbitMQ + Parser + AI + Frontend)
# ─────────────────────────────────────────────────────────────────────────────
up-services: check-network
	$(DC) $(ENV) up -d

up-services-build: check-network
	$(DC) $(ENV) up -d --build

down-services:
	$(DC) $(ENV) down

# ── Individual services ──────────────────────────────────────────────────────
up-rabbitmq: check-network
	$(DC) $(ENV) up -d rabbitmq

down-rabbitmq:
	$(DC) $(ENV) stop rabbitmq

logs-rabbitmq:
	docker logs -f rabbitmq

up-parser: check-network
	$(DC) $(ENV) up -d parser

up-parser-build: check-network
	$(DC) $(ENV) up -d --build parser

down-parser:
	$(DC) $(ENV) stop parser

logs-parser:
	docker logs -f parser

up-ai: check-network
	$(DC) $(ENV) up -d ai_worker

up-ai-build: check-network
	$(DC) $(ENV) up -d --build ai_worker

down-ai:
	$(DC) $(ENV) stop ai_worker

logs-ai:
	docker logs -f ai_worker

up-frontend: check-network
	$(DC) $(ENV) up -d frontend

up-frontend-build: check-network
	$(DC) $(ENV) up -d --build frontend

down-frontend:
	$(DC) $(ENV) stop frontend

logs-frontend:
	docker logs -f frontend

# ─────────────────────────────────────────────────────────────────────────────
# Full stack
# ─────────────────────────────────────────────────────────────────────────────
up-all: check-network
	@echo ">>> Starting Odoo stack..."
	$(MAKE) -C odoo up-all
	@echo ">>> Starting RabbitMQ + services..."
	$(DC) $(ENV) up -d
	@echo ""
	@echo "✓ Full stack is up:"
	@echo "  Odoo        → http://localhost:5433"
	@echo "  Frontend    → http://localhost:3000"
	@echo "  RabbitMQ UI → http://localhost:15672"
	@echo "  PgAdmin     → http://localhost:5050"

up-all-build: check-network
	$(MAKE) -C odoo up-all-no-cache
	$(DC) $(ENV) up -d --build

down-all:
	$(DC) $(ENV) down
	$(MAKE) -C odoo down-all

# ─────────────────────────────────────────────────────────────────────────────
# Logs
# ─────────────────────────────────────────────────────────────────────────────
logs-all:
	$(DC) $(ENV) logs -f

# ─────────────────────────────────────────────────────────────────────────────
# ULTRA — full cold start from scratch
# ─────────────────────────────────────────────────────────────────────────────
ultra:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════╗"
	@echo "║           ULTRA — full cold-start from scratch           ║"
	@echo "╚══════════════════════════════════════════════════════════╝"
	@echo ""

	@echo ">>> [1/7] Creating artifacts directories..."
	@mkdir -p artifacts/models artifacts/lora

	@echo ">>> [2/7] Ensuring Docker network exists..."
	@$(MAKE) check-network

	@echo ">>> [3/7] Tearing down all existing containers + volumes..."
	@$(DC) $(ENV) down --volumes --remove-orphans 2>/dev/null || true
	@$(MAKE) -C odoo down-all-volumes 2>/dev/null || true

	@echo ">>> [4/7] Building all images from scratch (no cache)..."
	@$(DC) $(ENV) build --no-cache

	@echo ">>> [5/7] Starting Odoo stack (DB + addon init, ~3-5 min)..."
	@$(MAKE) -C odoo up-all-no-cache

	@echo ">>> [6/7] Starting RabbitMQ + Parser + AI + Frontend..."
	@$(DC) $(ENV) up -d

	@echo ">>> [7/7] Waiting for Odoo and verifying foldiss_uav addon..."
	@$(MAKE) init-odoo

	@if [ -d "artifacts/models/hub" ] && [ "$$(ls -A artifacts/models/hub 2>/dev/null)" ]; then \
		echo "  AI model  → found in artifacts/models/ (offline mode ON)"; \
	else \
		echo ""; \
		echo "  WARNING: AI model not found in artifacts/models/"; \
		echo "           Run: make download-model   (needs internet, ~3 GB)"; \
	fi
	@echo ""

# ── Bootstrap Odoo DB + install foldiss_uav addon ────────────────────────────
init-odoo:
	@echo ">>> Initialising Odoo (waiting for HTTP + installing foldiss_uav)..."
	@ODOO_EXTERNAL_URL=http://localhost:5433 \
	 ODOO_DB=$(shell grep '^ODOO_DB' .env | cut -d= -f2 | tr -d ' ') \
	 ODOO_USER=$(shell grep '^ODOO_USER' .env | cut -d= -f2 | tr -d ' ') \
	 ODOO_PASSWORD=$(shell grep '^ODOO_PASSWORD' .env | cut -d= -f2 | tr -d ' ') \
	 python3 scripts/init_odoo.py

# ── Download model into artifacts/ (one-time, needs internet) ─────────────────
download-model:
	@echo ">>> Downloading Qwen2.5-1.5B-Instruct into artifacts/models/ ..."
	@mkdir -p artifacts/models
	@pip3 install --quiet huggingface-hub
	@echo ">>> Using HF_TOKEN: $$(grep '^HF_TOKEN' .env | cut -d= -f2 | tr -d ' ' | cut -c1-10)..."
	@HF_TOKEN=$$(grep '^HF_TOKEN' .env | cut -d= -f2 | tr -d ' ') python3 -c "\
from huggingface_hub import snapshot_download; \
import os; \
snapshot_download('Qwen/Qwen2.5-1.5B-Instruct', \
    cache_dir='artifacts/models/hub', \
    token=os.environ.get('HF_TOKEN') or None, \
    max_workers=8, \
    ignore_patterns=['*.bin','*.pt']); \
print('Done.')"
	@echo "Model saved to artifacts/models/"

# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Foldiss UAV — Monorepo Makefile"
	@echo "================================"
	@echo ""
	@echo "Cold start:"
	@echo "  make ultra             Full rebuild from scratch (wipes volumes, no-cache)"
	@echo "  make init-odoo         Wait for Odoo + install foldiss_uav + print creds"
	@echo "  make download-model    Download Qwen model into artifacts/models/ (once)"
	@echo ""
	@echo "Full stack:"
	@echo "  make up-all            Start everything (Odoo + services)"
	@echo "  make down-all          Stop everything"
	@echo ""
	@echo "Odoo:"
	@echo "  make up-odoo           Start Odoo stack (delegates to odoo/Makefile)"
	@echo "  make down-odoo         Stop Odoo stack"
	@echo ""
	@echo "New services:"
	@echo "  make up-services       Start RabbitMQ + Parser + AI + Frontend"
	@echo "  make up-rabbitmq       Start only RabbitMQ"
	@echo "  make up-parser         Start only Parser Worker"
	@echo "  make up-parser-build   Rebuild + start Parser Worker"
	@echo "  make up-ai             Start only AI Worker"
	@echo "  make up-ai-build       Rebuild + start AI Worker"
	@echo "  make up-frontend       Start only Frontend"
	@echo "  make up-frontend-build Rebuild + start Frontend"
	@echo ""
	@echo "Logs:"
	@echo "  make logs-parser       Follow Parser logs"
	@echo "  make logs-ai           Follow AI Worker logs"
	@echo "  make logs-frontend     Follow Frontend logs"
	@echo "  make logs-rabbitmq     Follow RabbitMQ logs"
	@echo "  make logs-all          Follow all service logs"
	@echo ""
