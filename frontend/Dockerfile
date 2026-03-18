# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# No build-time env vars needed — API calls use relative URLs proxied by nginx (Docker)
# or a CloudFront behavior for /api/* pointing to the ALB (prod).
RUN npm run build

# ── Stage 2: serve via nginx ──────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
