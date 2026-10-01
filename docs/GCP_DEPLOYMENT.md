# AeroTwin — Docker & GCP deployment

Target: **one Compute Engine VM running `docker-compose.prod.yml`**. Caddy terminates HTTPS and is the only public entry; TimescaleDB, Redis, Mosquitto and the backend stay on a private Docker network.

## Why a single VM (and not Cloud Run / GKE / Cloud SQL)

| Option | Verdict | Reason |
|---|---|---|
| Cloud SQL for PostgreSQL | ✗ | The first migration runs `CREATE EXTENSION timescaledb` + `create_hypertable`. Cloud SQL doesn't offer TimescaleDB. (Alternatives: Timescale Cloud, or self-host as here.) |
| Cloud Run / multi-replica GKE | ✗ for the backend | The backend must run **exactly one replica**: model windows, fault state machine, alert cooldowns and the WebSocket manager are in-process memory. It also runs a long-lived MQTT client thread. |
| Single GCE VM + Docker Compose | ✓ | Matches those constraints, lowest cost/complexity. Persistent SSD, daily snapshots, IAP-only SSH. |

Sizing: `e2-standard-4` (4 vCPU / 16 GB) recommended; `e2-standard-2` (8 GB) is the floor — the backend loads TensorFlow, XGBoost, LightGBM and scikit-learn. **[NEEDS VERIFICATION]** under your real telemetry load. Replays of large missions (≈95k readings) are CPU-heavy and slow live ingestion while they run.

## What you need to provide

1. **GCP project** with billing enabled, and a user with `Compute Admin` + `IAP-secured Tunnel User` (or Owner).
2. **A domain name** and access to its DNS (one A record → the VM's static IP). HTTPS certificates are issued automatically by Let's Encrypt via Caddy; ports 80/443 must be reachable.
3. **Secrets** (generate; never commit): `POSTGRES_PASSWORD`, `JWT_SECRET` (≥32 chars), `EDGE_API_KEY` (≥16 chars). `ENVIRONMENT=production` makes the app refuse weak values.
4. **Email** for Let's Encrypt notices (`ACME_EMAIL`).
5. **Git access for the VM** to pull this repo (deploy key or HTTPS token), *or* copy the repo with `gcloud compute scp`.
6. **First admin user** — there is no self-registration; you create users with `create_user.py` (below). Decide the email/role and a ≥12-char password.
7. **Optional:** `GEMINI_API_KEY` or `GROQ_API_KEY` (Copilot degrades gracefully without); an off-host backup bucket (`gsutil`).
8. **Decisions for you:**
   - How real engines send telemetry: HTTPS REST with `EDGE_API_KEY` (works out of the box through Caddy) or MQTT on 8883 (needs a TLS certificate mounted into Mosquitto — not wired by default; see below).
   - Whether the seeded demo data/demo simulator should exist in production (recommended: no).
9. **Cost:** e2-standard-4 + 100 GB SSD + static IP is roughly USD 120–140/month **[NEEDS VERIFICATION]** against current GCP pricing for your region.

## Deploy steps

```bash
# 0. Workstation (gcloud authenticated)
PROJECT_ID=<project> ZONE=asia-south1-a ./infra/gcp/provision.sh
#    -> creates static IP, firewall (80/443, SSH via IAP only), VM with Docker, daily snapshots.
#    Point your DNS A record at the printed IP.

# 1. On the VM
gcloud compute ssh aerotwin-prod --zone <zone> --tunnel-through-iap
sudo -iu deploy
git clone <repo-url> /opt/aerotwin && cd /opt/aerotwin      # or scp the repo

# 2. Configuration
cp infra/docker/.env.prod.example infra/docker/.env.prod    # fill every REQUIRED value
#    openssl rand -hex 32   # JWT_SECRET;   openssl rand -hex 24 # POSTGRES_PASSWORD;  openssl rand -hex 16 # EDGE_API_KEY
infra/gcp/mqtt-user.sh edge-01                              # creates infra/docker/mosquitto.passwd (prompts for a password)

# 3. Launch (first build downloads ~1.5 GB of ML wheels; 10–20 min)
./infra/gcp/deploy.sh

# 4. Create the first admin (password prompted, never on the command line)
docker compose --env-file infra/docker/.env.prod -f infra/docker/docker-compose.prod.yml \
    exec backend python create_user.py you@company.com admin

# 5. Verify
curl -fsS https://<domain>/healthz
```

Open `https://<domain>` and sign in. Data only appears once an engine is registered and telemetry arrives.

## Sending telemetry in production

- **REST (recommended):** edge agents POST to `https://<domain>/api/v1/telemetry/ingest` with the `X-Edge-Api-Key` header set to `EDGE_API_KEY` (see `edge/README.md`). TLS is handled by Caddy.
- **MQTT:** the backend consumes `aerotwin/telemetry/+` from the internal broker. Mosquitto's external listener (8883) is username/password-protected and bound to `127.0.0.1` by default. To accept remote devices: mount a certificate into the `mqtt` service, uncomment `certfile/keyfile` in `mosquitto.prod.conf`, set `MQTT_EDGE_BIND=0.0.0.0`, open tcp:8883 in the firewall. **Never expose it without TLS.** The backend's own connection to the broker is internal and anonymous (it has no MQTT credential setting).

## Operations

| Task | How |
|---|---|
| Update | `git pull` then `./infra/gcp/deploy.sh` (migrations run on backend start) |
| Logs | `docker compose --env-file infra/docker/.env.prod -f infra/docker/docker-compose.prod.yml logs -f backend` |
| Backup | `infra/gcp/backup.sh` (cron daily; copy to a bucket with `gsutil cp`); disk snapshots run daily, 14-day retention |
| Restore | `docker compose … exec -T db pg_restore -U aerotwin -d aerotwin --clean < dump` |
| Restart | `docker compose … restart backend` (RUL needs 30 and Fault 80 fresh readings before reporting again) |

## Local dry run of the production stack

```bash
cp infra/docker/.env.prod.example infra/docker/.env.prod   # DOMAIN=localhost, any secrets >= the minimum lengths
touch infra/docker/mosquitto.passwd
docker compose --env-file infra/docker/.env.prod -f infra/docker/docker-compose.prod.yml up -d --build
# https://localhost (Caddy's local CA — accept the warning); create a user as above
```

## Security checklist before go-live

- [ ] Secrets set and unique; `.env.prod` and `mosquitto.passwd` are git-ignored (they are) and `chmod 600`.
- [ ] The dev seeded account `admin@aerotwin-dev.com` does not exist in the production database (fresh DB — it doesn't); the login page no longer prefills it in production builds.
- [ ] Only 80/443 open in the firewall; SSH through IAP.
- [ ] Demo `simulator` service is **not** in `docker-compose.prod.yml` (it isn't).
- [ ] Backups tested with one restore.
- [ ] Known limits in `docs/DEPLOYMENT.md` (single replica, model quality on piston data) acknowledged.

## Low-cost plan for the GCP free trial (about USD 300 / 90 days)

Approximate costs (US-style list prices, **[NEEDS VERIFICATION]** in the pricing calculator for your region):

| Setup | Per day | 60 days |
|---|---|---|
| e2-medium (4 GB) + 50 GB balanced disk + static IP | ~USD 1.1 | ~USD 65 |
| **e2-standard-2 (8 GB) + 50 GB balanced disk + static IP (default)** | **~USD 1.9** | **~USD 115** |
| e2-standard-4 (16 GB) + same storage | ~USD 3.7 | ~USD 220 |
| VM stopped (disk + IP only) | ~USD 0.45 | — |

Plan: provision the default, set budget alerts (billing -> Budgets: 50 / 100 / 150 USD), stop the VM when nobody needs it, and delete the VM, disk, IP and snapshots at the end. The trial credit expires at 90 days; do not upgrade the billing account unless you intend to keep paying.
