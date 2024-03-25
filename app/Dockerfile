# pull official base image
FROM python:3.11-slim-bookworm
LABEL maintainer="Adrian Lewis <brainthee@gmail.com>"

EXPOSE 8000

# Set lang
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# set work directory
WORKDIR /app

# set environment variables
ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install sys dependencies
RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev pkg-config libpq-dev \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# copy entrypoint.sh
COPY ./entrypoint.sh .
RUN sed -i 's/\r$//g' /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# copy project
COPY . .

# run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["python3", "manage.py", "runserver", "--insecure", "0.0.0.0:8000"]
