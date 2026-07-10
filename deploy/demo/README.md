# Demo deployment (demo.chaotica.app)

Self-contained deployment for the public demo. The entire app runs from the
published `brainthee/chaotica:latest` image — there is **no source checkout on
the demo host**. This directory is everything the box needs.

## Layout

| File | Purpose |
|------|---------|
| `docker-compose.yml` | web (gunicorn/WSGI) + MariaDB + nginx. Every service is `restart: unless-stopped`. |
| `nginx.conf` | Reverse proxy + `/static/` and `/media/` serving. |
| `refresh_demo_data.sh` | Nightly wipe-and-reseed. Run from cron. |

## Host setup

```bash
sudo mkdir -p /opt/chaotica-demo
# copy this directory's contents to /opt/chaotica-demo
cd /opt/chaotica-demo
docker compose up -d --wait
```

Nightly refresh via the `adrian` crontab:

```cron
0 2 * * * cd /opt/chaotica-demo && ./refresh_demo_data.sh >> /var/log/chaotica-demo-refresh.log 2>&1
```

Log rotation lives at `/etc/logrotate.d/chaotica-demo-refresh` (weekly, keep 8,
`copytruncate`).

## Resilience

- **Reboot / crash recovery:** `restart: unless-stopped` on every service plus
  the Docker daemon being enabled on boot (`systemctl enable docker`) means the
  stack comes back on its own. No systemd unit is required. The MariaDB volume
  (`chaotica-demo_mariadb_data`) persists across reboots, so data survives.
- **Startup ordering:** `db` has a healthcheck and `web` waits for it via
  `depends_on: condition: service_healthy`; the refresh script uses
  `docker compose up -d --wait` instead of a fixed `sleep`.

## What the refresh script does

1. `docker compose pull --quiet` — grab the latest published image.
2. `docker compose up -d --wait` — (re)start, waiting for health.
3. `docker image prune -f` — reclaim layers from the replaced image so the disk
   can't silently fill (this had previously filled the 30 GB disk to 100%).
4. `migrate` → `flush` → enable maintenance mode → `collectstatic` → ensure
   superuser → `generate_demo_data --force ...` → clear cache → disable
   maintenance mode.

`flush` deletes rows but keeps the schema, so the volume is reused; migrations
are only ever applied incrementally on top of it. An `EXIT` trap guarantees the
site is never left stuck in maintenance mode or down: on any failure it brings
the stack back up and clears maintenance mode.

## Credentials

- Superuser: `admin@demo.chaotica.app` / `DemoAdmin123!`
- Generated demo users: password `DemoUser123!` (passed via `--password`).

## Secrets / .env

- `SECRET_KEY` and DB passwords in `docker-compose.yml` are throwaway demo values.
- The real `MAXMIND_LICENSE_KEY` is **not** committed. Copy `.env.example` to
  `.env` on the host and set it there (`.env` is gitignored). Blank is fine —
  the container just skips the GeoIP database download.

## Notes

- `generate_demo_data` requires `--force` because the demo runs `DEBUG=0`; the
  flag is the command's guard against running against a real database.
- `deploy/demo/patches/` is a temporary demo-data tuning override, not a bug
  shim — see `patches/README.md`.
