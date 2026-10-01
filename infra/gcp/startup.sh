#!/usr/bin/env bash
# VM bootstrap (runs as root on first boot): Docker Engine + compose plugin, a 'deploy' user, /opt/aerotwin.
set -euo pipefail
if ! command -v docker >/dev/null; then
  apt-get update && apt-get install -y ca-certificates curl git gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
  apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash -G docker deploy
mkdir -p /opt/aerotwin && chown deploy:deploy /opt/aerotwin
# Keep container logs bounded
cat > /etc/docker/daemon.json <<'J'
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
J
systemctl restart docker
# 2 GB swap: absorbs the ML model-load spike on small VMs
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo "/swapfile none swap sw 0 0" >> /etc/fstab; fi
