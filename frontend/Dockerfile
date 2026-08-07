# Denoise X — frontend image (Sprint 4E).
#
# Multi-stage build using Next.js `output: "standalone"` (next.config.ts):
#   .next/standalone  → traced runtime + server.js
#   .next/static      → client assets
#   public/           → static files
#
# `NEXT_PUBLIC_API_URL` is a build-time ARG (Next inlines NEXT_PUBLIC_* into the
# bundle at build). It defaults to https://api.<SITE_DOMAIN> via the compose
# `build.args` wiring, so the value comes from .env — no code changes between
# environments (docs/engineering/deployment.md, "Runtime configuration").
#
# Node 22 (Next 16 requires >= 20.9).
FROM node:22-alpine AS base
WORKDIR /app

# Install dependencies (cached separately from the source copy).
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

# Build the application.
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# Production runtime — only the traced standalone output.
FROM base AS runner
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
