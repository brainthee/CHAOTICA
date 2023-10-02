# pull official base image
FROM python:3-alpine

EXPOSE 8000

# Set lang
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install db dependencies
RUN apk update \
    && apk add postgresql-dev gcc g++ python3-dev libffi-dev musl-dev pkgconfig mariadb-dev mariadb-connector-c-dev libmagic

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
