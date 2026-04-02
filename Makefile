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
        logs-all help

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
# Help
# ─────────────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Foldiss UAV — Monorepo Makefile"
	@echo "================================"
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
