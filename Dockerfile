FROM tiangolo/uvicorn-gunicorn:python3.7-alpine3.8

LABEL maintainer=

COPY ./app /app

RUN pip install -r /app/requirements.txt