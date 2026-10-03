#!/bin/bash
# Build all AeroTwin images LOCALLY and push to GCP Artifact Registry.
# Run this from the repo root on your local machine (not on the VM).
#
# Usage: bash build-and-push.sh
#
set -euo pipefail

REGISTRY="us-central1-docker.pkg.dev/aerotwin-510405/aerotwin"
TAG="${IMAGE_TAG:-latest}"

echo "=== Authenticating Docker with Artifact Registry ==="
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

echo "=== Building images locally ==="
docker compose \
  -f infra/docker/docker-compose.prod.yml \
  --env-file infra/docker/.env.prod \
  build \
  --no-cache

echo "=== Tagging and pushing backend ==="
docker tag aerotwin-backend:latest "$REGISTRY/aerotwin-backend:$TAG"
docker push "$REGISTRY/aerotwin-backend:$TAG"

echo "=== Tagging and pushing frontend ==="
docker tag aerotwin-frontend:latest "$REGISTRY/aerotwin-frontend:$TAG"
docker push "$REGISTRY/aerotwin-frontend:$TAG"

echo "=== Tagging and pushing simulator ==="
docker tag aerotwin-simulator:latest "$REGISTRY/aerotwin-simulator:$TAG"
docker push "$REGISTRY/aerotwin-simulator:$TAG"

echo ""
echo "=== All images pushed! ==="
echo "Registry: $REGISTRY"
echo "Tag: $TAG"
echo ""
echo "Now run deploy-from-registry.sh to deploy to the VM."
