#!/usr/bin/env bash
# Run ON the VM from the repo root (/opt/aerotwin): pulls the latest code, builds and (re)starts the stack.
# First run: create infra/docker/.env.prod (from .env.prod.example) and infra/docker/mosquitto.passwd first.
set -euo pipefail
cd "$(dirname "$0")/../.."
C="infra/docker"
[ -f "$C/.env.prod" ] || { echo "Missing $C/.env.prod (copy .env.prod.example and fill it in)"; exit 1; }
[ -f "$C/mosquitto.passwd" ] || { echo "Missing $C/mosquitto.passwd — run infra/gcp/mqtt-user.sh <user>"; exit 1; }
git pull --ff-only
docker compose --env-file "$C/.env.prod" -f "$C/docker-compose.prod.yml" up -d --build
docker compose --env-file "$C/.env.prod" -f "$C/docker-compose.prod.yml" ps
echo "Backend migrates the DB on start. Check:  curl -fsS https://\$(grep ^DOMAIN= $C/.env.prod | cut -d= -f2)/healthz"
