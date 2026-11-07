# Light image: api, relay, janitor, migrate, cli (~150 MB). No ML dependencies.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements/core.txt requirements/core.txt
RUN pip install -r requirements/core.txt

COPY db ./db
COPY sma3ni ./sma3ni
# Pre-create the volume mount point owned by the app user (Docker copies ownership to new volumes).
RUN mkdir -p /data/audio && chown -R app:app /data

USER app
