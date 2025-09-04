# pull official base image
FROM debian:12
LABEL maintainer="Adrian Lewis <brainthee@gmail.com>"

ARG UID=1005
ARG GID=1005

# set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PORT=8000
ENV USE_REDIS=true
EXPOSE ${PORT}

# set work directory
WORKDIR /app

# install sys dependencies
RUN apt-get update --fix-missing \
&& apt-get install -y build-essential git procps gcc sudo cron curl python3 python3-dev python3-setuptools python3-pip python3-virtualenv clamav-daemon default-libmysqlclient-dev pkg-config libpq-dev mariadb-client nginx supervisor redis

RUN apt-get upgrade -y

# ClamAV stuff
RUN mkdir -p /var/log/clamav /var/lib/clamav /var/run/clamav \
    && chown -R root:root /var/log/clamav /var/lib/clamav /var/run/clamav \
    && chmod 755 /var/log/clamav /var/lib/clamav /var/run/clamav
# Copy ClamAV confs
COPY --chown=root:root --chmod=644 ./.docker/config/clamav/*.conf /etc/clamav/
# Pre-update defs
RUN freshclam --config-file=/etc/clamav/freshclam.conf

# Cleanup
RUN rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man /var/cache/apt/archives/* \
&& apt-get clean

# Stop some services
RUN service supervisor stop \
&& service cron stop

# Setup user
RUN groupadd -g "${GID}" chaotica \
&& useradd --create-home --no-log-init -u "${UID}" -g "${GID}" chaotica \
&& chown root:root -R /app

# install dependencies
COPY --chown=root:root --chmod=755 requirements*.txt ./

# pin to v24 because of https://github.com/pypa/pip/issues/13015
RUN pip3 install --break-system-packages --upgrade pip==24.0 \
&& pip3 install --break-system-packages -r requirements.txt \
&& pip3 install --break-system-packages git+https://github.com/coderanger/supervisor-stdout.git

# Setup CRON
COPY --chown=root:root --chmod=755 ./.docker/config/cron/crontab.txt /crontab.txt
# Copy supervisor conf
COPY --chown=root:root --chmod=755 ./.docker/config/supervisord/supervisord.conf /etc/

# copy entrypoint.sh
COPY --chown=root:root --chmod=755 ./entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

# copy project
COPY --chown=root:root --chmod=755 . .

# run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]