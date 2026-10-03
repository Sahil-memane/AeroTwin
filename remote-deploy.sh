#!/bin/bash
set -euxo pipefail

# Convert all scripts to Unix line endings
find /opt/aerotwin -type f -name "*.sh" -exec dos2unix {} +

# Run MQTT password setup in batch mode to avoid interactive prompt
cd /opt/aerotwin/infra/docker
touch mosquitto.passwd
docker run --rm -v "$PWD:/w" eclipse-mosquitto:2.0.20 mosquitto_passwd -b -c /w/mosquitto.passwd admin password123
chmod 644 mosquitto.passwd

# Deploy
cd /opt/aerotwin
bash infra/gcp/deploy.sh