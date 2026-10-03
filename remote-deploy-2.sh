#!/bin/bash
set -euo pipefail
sed -i "s/git pull --ff-only/# git pull --ff-only/" /opt/aerotwin/infra/gcp/deploy.sh
cd /opt/aerotwin
bash infra/gcp/deploy.sh