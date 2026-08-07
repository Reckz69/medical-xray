#!/usr/bin/env bash
# Denoise X — generate production secrets (Sprint 4E, ADR-014).
#
#   ./generate-secrets.sh
#
# Creates .env from .env.example, replacing every __generate__ placeholder
# with a freshly generated credential (openssl rand). Refuses to overwrite an
# existing .env. Prints the generated values ONCE; store them in your password
# manager and lock the file down (chmod 600 is applied).
#
# Secrets are unique per deployment and never committed. Rotation is a manual,
# documented procedure — see docs/engineering/secret-rotation.md.
set -euo pipefail

cd "$(dirname "$0")"

SRC=".env.example"
DST=".env"

if [ -e "$DST" ]; then
  echo "error: $DST already exists — refusing to overwrite." >&2
  echo "if you must regenerate, delete it first (you will lose access to the current credentials)." >&2
  exit 1
fi

if [ ! -f "$SRC" ]; then
  echo "error: $SRC not found next to this script." >&2
  exit 1
fi

gen_alnum() { openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32; }
gen_hex()   { openssl rand -hex 32; }

POSTGRES_PASSWORD="$(gen_alnum)"
RABBITMQ_PASS="$(gen_alnum)"
MINIO_ROOT_USER="denoise-$(openssl rand -hex 4)"
MINIO_ROOT_PASSWORD="$(gen_alnum)"
JWT_SECRET="$(gen_hex)"
GRAFANA_ADMIN_PASSWORD="$(gen_alnum)"

sed \
  -e "s|^POSTGRES_PASSWORD=__generate__$|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" \
  -e "s|^RABBITMQ_PASS=__generate__$|RABBITMQ_PASS=${RABBITMQ_PASS}|" \
  -e "s|^MINIO_ROOT_USER=__generate__$|MINIO_ROOT_USER=${MINIO_ROOT_USER}|" \
  -e "s|^MINIO_ROOT_PASSWORD=__generate__$|MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}|" \
  -e "s|^JWT_SECRET=__generate__$|JWT_SECRET=${JWT_SECRET}|" \
  -e "s|^GRAFANA_ADMIN_PASSWORD=__generate__$|GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}|" \
  -e "s|^S3_ACCESS_KEY=__generate__$|S3_ACCESS_KEY=${MINIO_ROOT_USER}|" \
  -e "s|^S3_SECRET_KEY=__generate__$|S3_SECRET_KEY=${MINIO_ROOT_PASSWORD}|" \
  "$SRC" > "$DST"

chmod 600 "$DST"

cat <<EOF
Generated $DST with unique credentials (chmod 600). SAVE THESE ONCE:

  POSTGRES_PASSWORD      = ${POSTGRES_PASSWORD}
  RABBITMQ_PASS          = ${RABBITMQ_PASS}
  MINIO_ROOT_USER        = ${MINIO_ROOT_USER}
  MINIO_ROOT_PASSWORD    = ${MINIO_ROOT_PASSWORD}
  JWT_SECRET             = ${JWT_SECRET}
  GRAFANA_ADMIN_PASSWORD = ${GRAFANA_ADMIN_PASSWORD}

Before starting the stack, pick LOCAL or CLOUD in the runtime-configuration
section of $DST (see .env.example). Then: docker compose up -d
EOF
