#!/usr/bin/env bash
# One-time GCP provisioning (run from your workstation with gcloud authenticated).
#   PROJECT_ID=my-proj ZONE=asia-south1-a ./provision.sh
# Creates: static IP, firewall rules (80/443 only), a Compute Engine VM with Docker, and a daily disk snapshot schedule.
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
ZONE="${ZONE:-asia-south1-a}"
REGION="${ZONE%-*}"
VM="${VM:-aerotwin-prod}"
MACHINE="${MACHINE:-e2-standard-2}"   # 2 vCPU / 8 GB (~USD 1.6/day). e2-medium (4 GB) is the cheaper floor; e2-standard-4 for heavy replays. [NEEDS VERIFICATION under your load]
DISK_GB="${DISK_GB:-50}"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable compute.googleapis.com

gcloud compute addresses create "$VM-ip" --region "$REGION" 2>/dev/null || true
IP=$(gcloud compute addresses describe "$VM-ip" --region "$REGION" --format='value(address)')

gcloud compute firewall-rules create aerotwin-web --allow tcp:80,tcp:443 --target-tags aerotwin --direction INGRESS 2>/dev/null || true
# SSH via IAP only (no public port 22)
gcloud compute firewall-rules create aerotwin-iap-ssh --allow tcp:22 --source-ranges 35.235.240.0/20 --target-tags aerotwin 2>/dev/null || true

gcloud compute instances create "$VM" \
  --zone "$ZONE" --machine-type "$MACHINE" --address "$IP" --tags aerotwin \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size "${DISK_GB}GB" --boot-disk-type pd-balanced --boot-disk-device-name "$VM" \
  --metadata-from-file startup-script="$(dirname "$0")/startup.sh" \
  --scopes cloud-platform 2>/dev/null || echo "VM already exists"

gcloud compute resource-policies create snapshot-schedule "$VM-daily" --region "$REGION" \
  --max-retention-days 14 --daily-schedule --start-time 21:00 2>/dev/null || true
gcloud compute disks add-resource-policies "$VM" --zone "$ZONE" --resource-policies "$VM-daily" 2>/dev/null || true

echo
echo "Static IP: $IP"
echo "1) Create a DNS A record:  <your domain> -> $IP   (Caddy cannot issue the certificate until this resolves)"
echo "2) gcloud compute ssh $VM --zone $ZONE --tunnel-through-iap"
echo "3) On the VM:  sudo -iu deploy; cd /opt/aerotwin && ./infra/gcp/deploy.sh   (see docs/GCP_DEPLOYMENT.md)"
