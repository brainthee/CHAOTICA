# Splitting the runtime daemons (planned / future work)

!!! note "Status: not yet implemented"
    This page captures a **future** refactor. Today the production image is a
    self-contained monolith (see below). This is deliberate — AWS Elastic Beanstalk
    runs CHAOTICA as a **single container** — but it is not ideal. Use this as the
    working brief when we pick the work up.

## Where we are today

The image runs **supervisord** as its `CMD`, which manages three long-lived processes
in one container:

| Process | Role |
| --- | --- |
| `gunicorn` (uvicorn ASGI worker) | Serves HTTP **and** the scheduler's `/ws/` WebSockets |
| `redis-server` | Backs the Channels layer and the Django cache |
| `cron` | Runs `manage.py runcrons` (django_cron) every minute for scheduled tasks |

This is required on Elastic Beanstalk because the platform is single-container
(`Dockerrun.aws.json`, `AWSEBDockerrunVersion: 1`) with only external RDS (MySQL),
S3/CloudFront (static), SES (email) and the ALB (TLS). There is **no ElastiCache**, so
Redis has to live inside the container. See
[AWS Elastic Beanstalk](aws_beanstalk.md).

`docker-compose` takes a different shape: the `web` service **overrides** the command
with a bare `gunicorn`, and Redis / Nginx / MariaDB are separate services.

## Why split it

- **Non-root policy** — supervisord runs as root to manage `cron`, so the container
  can't set a default non-root user (a Docker Scout policy failure). A single gunicorn
  process can run as `chaotica`.
- **One process per container** — cleaner restarts, scaling and observability.
- **No in-container Redis** — a shared, managed cache/Channels layer survives container
  restarts and can be shared across instances.

## Target architecture

1. **Redis → AWS ElastiCache.**
    - Add an ElastiCache (Redis) resource in Terraform
      (`/data/projects/CAS/chaotica_deployment`).
    - Point the Channels layer at it via the existing `CHANNELS_REDIS_URL` env var
      (already env-driven, `settings.py`).
    - **Fix the hardcoded cache LOCATION** — `CACHES` in `app/chaotica/settings.py`
      (~line 676) is pinned to `redis://127.0.0.1:6379/1` and is **not**
      env-overridable. Make it read an env var (e.g. `CACHE_REDIS_URL`) so it can point
      at ElastiCache. Today it silently fails against any non-localhost Redis and only
      survives because `django_redis` is configured with `IGNORE_EXCEPTIONS=True`.
    - Drop the in-container `redis-server` (Dockerfile apt package + the
      `[program:redis-server]` block in `supervisord.conf` + the `USE_REDIS` readiness
      probe in `entrypoint.sh`).

2. **cron / `runcrons` → external scheduler.**
    - On EB: an `.ebextensions`/`.platform` cron hook, or a separate scheduled
      invocation, instead of in-container `cron`.
    - Long term consider replacing django_cron with **Celery beat** (the Celery app
      already exists at `chaotica/celery.py` but is currently vestigial/unused) plus a
      dedicated worker container where the topology allows it.

3. **Drop supervisord → single process.**
    - With Redis and cron externalised, `CMD` becomes a bare
      `gunicorn ... chaotica.asgi:application` and the image can set `USER chaotica`.
    - Remove `supervisor` (from `requirements.txt`), `supervisor-stdout`, the
      `supervisord.conf`, and the `cron`/`sudo` apt packages that only existed to
      support the monolith.

## docker-compose parity (important)

`docker-compose` support must be kept. When the split happens, also fix the two latent
compose gaps that exist today:

- The `web` command override bypasses supervisord, so **`runcrons` never runs** under
  compose — add a dedicated scheduler service (or Celery beat) in the compose file.
- The hardcoded cache `LOCATION` means the compose `web` container's cache points at
  `127.0.0.1` instead of the compose `redis` service — fixed by the env-driven
  `CACHES` change above.

## Rough sequencing

1. Env-ify the cache `LOCATION` (safe, standalone; unblocks everything else).
2. Provision ElastiCache in Terraform; wire `CHANNELS_REDIS_URL` + the new cache env var.
3. Move `runcrons` to an external scheduler; verify scheduled tasks still fire.
4. Remove in-container `redis-server`, drop supervisord, set `USER chaotica`, single CMD.
5. Update `docker-compose.yml` for parity (scheduler service, external redis).
