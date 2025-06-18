# pull official base image
FROM ubuntu:24.04
LABEL maintainer="Adrian Lewis <brainthee@gmail.com>"

ARG UID=1000
ARG GID=1000

# set environment variables
ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONPATH .
ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
# set default port for gunicorn
ENV PORT=8000
EXPOSE ${PORT}

# set work directory
WORKDIR /app

# install sys dependencies
RUN apt-get update --fix-missing
RUN apt-get upgrade -y
RUN apt-get install -y build-essential git procps gcc sudo cron
RUN apt-get install -y python3 python3-dev python3-setuptools
RUN apt-get install -y python3-pip python3-virtualenv
RUN apt-get install -y clamav-daemon
RUN apt-get install -y default-libmysqlclient-dev pkg-config libpq-dev mariadb-client
RUN apt-get install -y nginx supervisor

# Cleanup
RUN rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man
RUN apt-get clean

# Stop some services
RUN service supervisor stop
RUN service cron stop

# Setup user
RUN groupadd -g "${GID}" chaotica
RUN useradd --create-home --no-log-init -u "${UID}" -g "${GID}" chaotica
RUN chown chaotica:chaotica -R /app

# install dependencies
COPY --chown=chaotica:chaotica requirements*.txt ./

# pin to v24 because of https://github.com/pypa/pip/issues/13015
RUN pip3 install --upgrade pip==24.0 
RUN pip3 install -r requirements.txt
RUN pip3 install git+https://github.com/coderanger/supervisor-stdout.git

# Setup CRON
COPY ./crontab.txt /crontab.txt

# Copy supervisor conf
COPY ./supervisord.conf /etc/

# copy entrypoint.sh
COPY ./entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

# copy project
COPY --chown=chaotica:chaotica . .

# run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]