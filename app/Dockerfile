# syntax=docker/dockerfile:1

##############################################################################
# Stage 1 — builder: compile wheels into an isolated virtualenv.
# The build toolchain (compilers, -dev headers, git) lives ONLY in this stage
# and is discarded, so it never bloats the runtime image.
##############################################################################
FROM debian:12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update --fix-missing \
 && apt-get install -y --no-install-recommends \
      build-essential gcc git \
      python3 python3-dev python3-venv \
      pkg-config default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/*

# Build into a self-contained venv so it can be copied wholesale into the runtime stage.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# pin to v24 because of https://github.com/pypa/pip/issues/13015
RUN pip install --upgrade pip==24.0

# Install runtime dependencies only (dev tooling lives in requirements-dev.txt and is
# intentionally not installed into the image).
COPY requirements.txt ./
RUN pip install -r requirements.txt \
 && pip install git+https://github.com/coderanger/supervisor-stdout.git

##############################################################################
# Stage 2 — runtime: slim image with only what is needed to RUN the app.
##############################################################################
FROM debian:12-slim
LABEL maintainer="Adrian Lewis <brainthee@gmail.com>"

ARG UID=1005
ARG GID=1005

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=. \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PORT=8000 \
    USE_REDIS=true \
    RUN_COLLECTSTATIC=true \
    PATH="/opt/venv/bin:$PATH"

EXPOSE ${PORT}
WORKDIR /app

# Runtime-only system dependencies (build toolchain stays in the builder stage):
#   python3             - interpreter the copied venv runs against
#   redis-server        - in-container Channels/cache backend (EB is single-container)
#   cron                - runs django_cron `runcrons`
#   mariadb-client      - libmariadb3 for mysqlclient + mysqldump for django-dbbackup
#   sudo                - entrypoint drops privileges to the chaotica user
#   curl/ca-certificates- entrypoint downloads the RDS CA + GeoIP DB over TLS
#   netcat-openbsd      - entrypoint's optional Postgres readiness wait
#   procps/tzdata       - `ps` for diagnostics, timezone data for the TZ env var
RUN apt-get update --fix-missing \
 && apt-get install -y --no-install-recommends \
      python3 ca-certificates curl tzdata sudo \
      redis-server cron mariadb-client netcat-openbsd procps \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man

# Copy the pre-built virtualenv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Setup user
RUN groupadd -g "${GID}" chaotica \
 && useradd --create-home --no-log-init -u "${UID}" -g "${GID}" chaotica

# Supervisor + cron config
COPY --chown=root:root --chmod=644 ./.docker/config/cron/crontab.txt /crontab.txt
COPY --chown=root:root --chmod=644 ./.docker/config/supervisord/supervisord.conf /etc/

# copy entrypoint.sh
COPY --chown=root:root --chmod=755 ./entrypoint.sh /app/entrypoint.sh

# copy project
COPY --chown=chaotica:chaotica --chmod=755 . .

# COPY --chown sets ownership of copied files but leaves the /app directory itself
# root-owned. Make /app writable by the runtime user (collectstatic -> staticfiles,
# cron log, sqlite db, etc.) and pre-create the static/media dirs (excluded via
# .dockerignore).
RUN mkdir -p /app/staticfiles /app/mediafiles \
 && chown chaotica:chaotica /app /app/staticfiles /app/mediafiles

# run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
