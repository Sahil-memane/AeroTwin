#!/usr/bin/env bash
# Create/update an MQTT edge user:  infra/gcp/mqtt-user.sh edge-01   (prompts for the password)
set -euo pipefail
cd "$(dirname "$0")/../docker"
USER_NAME="${1:?usage: mqtt-user.sh <username>}"
FLAG=""; [ -s mosquitto.passwd ] || FLAG="-c"
[ -f mosquitto.passwd ] || : > mosquitto.passwd
docker run --rm -it -v "$PWD:/w" eclipse-mosquitto:2.0.20 mosquitto_passwd $FLAG /w/mosquitto.passwd "$USER_NAME"
chmod 644 mosquitto.passwd   # readable by the broker user inside the container; keep the host dir private
