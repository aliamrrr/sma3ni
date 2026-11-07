# ML image: asr-worker, nlp-worker, models job.
#   CPU (default) : docker compose build                       -> PyTorch CPU wheels (~1.5 GB)
#   GPU (AWS)     : TORCH_INDEX=https://download.pytorch.org/whl/cu128 (set by docker-compose.aws.yml)
# The CUDA wheels ship their own CUDA runtime; the host only needs the NVIDIA driver and
# nvidia-container-toolkit (both preinstalled on the AWS Deep Learning Base AMI).
FROM python:3.12-slim-bookworm

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements/ requirements/
RUN pip install --index-url "${TORCH_INDEX}" torch \
 && pip install -r requirements/ml.txt

COPY db ./db
COPY sma3ni ./sma3ni
RUN mkdir -p /data/audio /models && chown -R app:app /data /models

USER app
