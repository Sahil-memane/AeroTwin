#!/bin/bash
# Deploy AeroTwin on the GCP VM by pulling pre-built images from Artifact Registry.
# Run this from your local machine.
#
set -euo pipefail

REGISTRY="us-central1-docker.pkg.dev/aerotwin-510405/aerotwin"
VM="aerotwin-prod"
ZONE="us-central1-a"
PROJECT="aerotwin-510405"

echo "=== Granting VM access to Artifact Registry ==="
# Get the VM's service account
SA=$(gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT" \
  --format="value(serviceAccounts[0].email)")
echo "VM Service Account: $SA"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$SA" \
  --role="roles/artifactregistry.reader" \
  --quiet

echo "=== Copying files to VM ==="
cd "$(dirname "$0")"

# Create deploy archive
zip -r /tmp/aerotwin-deploy.zip infra/docker/ -x "*.pyc" -x "__pycache__" -x "*.env"
gcloud compute scp /tmp/aerotwin-deploy.zip "$VM":/tmp/aerotwin-deploy.zip \
  --zone="$ZONE" --project="$PROJECT" --tunnel-through-iap

# Copy .env.prod
gcloud compute scp infra/docker/.env.prod "$VM":/tmp/aerotwin.env.prod \
  --zone="$ZONE" --project="$PROJECT" --tunnel-through-iap

echo "=== Setting up and starting stack on VM ==="
gcloud compute ssh "$VM" --zone="$ZONE" --project="$PROJECT" --tunnel-through-iap --command="
  set -euo pipefail

  # Install deps
  which unzip || sudo apt-get install -y unzip

  # Extract files
  sudo mkdir -p /opt/aerotwin/infra/docker
  sudo unzip -o /tmp/aerotwin-deploy.zip 'infra/docker/*' -d /opt/aerotwin/
  sudo cp /tmp/aerotwin.env.prod /opt/aerotwin/infra/docker/.env.prod

  # Authenticate Docker to Artifact Registry using VM's service account
  sudo gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

  # Setup MQTT password file
  cd /opt/aerotwin/infra/docker
  sudo touch mosquitto.passwd
  sudo docker run --rm -v \"\$PWD:/w\" eclipse-mosquitto:2.0.20 \
    mosquitto_passwd -b -c /w/mosquitto.passwd admin password123
  sudo chmod 644 mosquitto.passwd

  # Pull images and start stack
  export REGISTRY='$REGISTRY'
  sudo REGISTRY='$REGISTRY' docker compose \
    --env-file /opt/aerotwin/infra/docker/.env.prod \
    -f /opt/aerotwin/infra/docker/docker-compose.vm.yml \
    pull

  sudo REGISTRY='$REGISTRY' docker compose \
    --env-file /opt/aerotwin/infra/docker/.env.prod \
    -f /opt/aerotwin/infra/docker/docker-compose.vm.yml \
    up -d

  echo 'Stack started!'
  sudo docker compose \
    --env-file /opt/aerotwin/infra/docker/.env.prod \
    -f /opt/aerotwin/infra/docker/docker-compose.vm.yml \
    ps
"
echo ""
echo "=== Deployment complete! ==="
echo "Visit: https://aerotwin-clutchx.duckdns.org"
