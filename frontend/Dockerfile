# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first (layer-cache friendly)
COPY package.json ./
RUN npm install

# Copy source and build
COPY . .

# VITE_ODOO_URL is injected at build time via docker-compose build-arg
ARG VITE_ODOO_URL=http://localhost:8069
ENV VITE_ODOO_URL=${VITE_ODOO_URL}

RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
