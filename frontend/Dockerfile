# frontend/Dockerfile
#
# Build targets:
#   deps        — install Node dependencies (shared cache layer)
#   development — dev server with hot-reload
#   builder     — production Next.js build (standalone output)
#   production  — minimal runtime image, non-root user

FROM node:20-alpine AS base
WORKDIR /app

# ── Dependencies ───────────────────────────────────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

# ── Development ────────────────────────────────────────────────────────────────
FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["npm", "run", "dev"]

# ── Builder ────────────────────────────────────────────────────────────────────
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Injected at image build time so Next.js can inline NEXT_PUBLIC_* at compile time
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ── Production ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup -S stocklens && adduser -S stocklens -G stocklens

# Standalone output bundles only the minimal server; no full node_modules needed
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static     ./.next/static
COPY --from=builder /app/public           ./public

RUN chown -R stocklens:stocklens /app
USER stocklens

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
