FROM python:3.12-slim

WORKDIR /app

COPY app /app/app
COPY config /config

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pyyaml

CMD ["python", "-m", "app.main"]
