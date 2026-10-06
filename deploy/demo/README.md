# Demo deployment (demo.chaotica.app)

The public demo runs the **published production image** (`brainthee/chaotica:latest`)
with its stock entrypoint and process model (supervisord → gunicorn/uvicorn ASGI,
redis, cron). The only differences from production are environment variables.
Everything is provisioned with Ansible onto a plain Ubuntu 24.04 VM.

Hard requirements and how they're met:

| Requirement | How |
|---|---|
| Dummy generated data | `generate_demo_data` (runtime dependency `Faker` is in `requirements.txt`) |
| Full nightly reset | `reset_demo.sh` destroys the stack **and all volumes**, migrates a brand-new DB, reseeds |
| Pre-set login | `DEMO_ENV`/`DEMO_USER`/`DEMO_PASS` pre-fill the login page; the reset (re)creates that superuser via `--admin-email`/`--admin-password` and verifies it |

## Layout

| Path | Purpose |
|------|---------|
| `docker-compose.yml` | web (prod image, stock CMD) + MariaDB + nginx. All config via `.env`. |
| `nginx.conf` | Proxy (incl. `/ws/` WebSockets), static/media, maintenance page. Re-resolves `web` via Docker DNS. |
| `reset_demo.sh` | Nightly full rebuild. Run by the `chaotica-demo-reset` systemd timer. |
| `maintenance/` | Maintenance page served while the reset runs (`maintenance/on` flag, gitignored). |
| `ansible/` | Playbook + roles: `common` (updates, TZ, journald cap), `docker` (Docker CE + compose, log rotation), `chaotica_demo` (stack files, `.env`, reset timer, first build). |

## Deploy

```bash
cd deploy/demo/ansible
ansible-galaxy collection install -r requirements.yml
ansible-playbook site.yml        # add -K if sudo needs a password
```

Target host and SSH user are in `inventory.ini`; all tunables (domain, creds,
reset time, seed sizes, image tag) are in `group_vars/all.yml`. The secrets there
are deliberately throwaway — the demo only ever holds generated data.

The first run builds and seeds the database by starting the reset service, so a
fresh VM is fully usable when the playbook finishes. Re-running the playbook is
idempotent and applies config changes to the running stack without wiping it.

TLS terminates upstream at Nginx Proxy Manager, which forwards to `:80` on the
host. **Enable "Websockets Support" on the NPM proxy host**, or the scheduler's
live updates fall back to polling.

## Nightly reset

`chaotica-demo-reset.timer` fires at `demo_reset_time` (default 02:00 host time,
`Europe/London`). The same value feeds `DEMO_RESET_TIME`, so the login banner's
"resets in…" countdown is accurate. The reset:

1. pulls the latest images;
2. switches nginx to the maintenance page;
3. `docker compose down --volumes` — database, media and static are destroyed;
4. starts web on an empty MariaDB and waits for its healthcheck (the entrypoint
   runs `migrate` from scratch before gunicorn starts — this is the slow part);
5. `generate_demo_data --force … --admin-email … --admin-password …`;
6. verifies the advertised login, removes the maintenance page, smoke-tests the
   login page through nginx, prunes superseded images.

If any step fails the maintenance page is **left up** (an empty database would
expose the fresh-install setup wizard) and the unit is marked failed.

```bash
systemctl list-timers chaotica-demo-reset.timer   # next run
journalctl -u chaotica-demo-reset -n 100          # last run's log
sudo systemctl start chaotica-demo-reset          # reset now
```

## Credentials

- Pre-set login (superuser): `admin@demo.chaotica.app` / `DemoAdmin123!`
- Generated users (`first.last@demo.chaotica.app`): `DemoUser123!`

## Notes

- `generate_demo_data` requires `--force` because the demo runs `DEBUG=0`.
- Image changes reach the demo only after they are pushed to GitHub `main`
  (CI publishes `brainthee/chaotica:latest`); the next reset pulls them.
