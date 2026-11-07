"""One-shot job: download model weights into the shared HF cache volume.

Runs on a network with internet access; the workers themselves run on an
internal network with HF_HUB_OFFLINE=1. If Hugging Face is unreachable but the
cache is already populated, it succeeds, so a HF outage never blocks a restart.
"""
from __future__ import annotations

import logging
import sys

from huggingface_hub import snapshot_download

from .config import get_settings
from .logs import setup_logging

log = logging.getLogger("sma3ni.models")


def fetch(repo_id: str, revision: str | None, token: str | None, ignore: list[str] | None = None) -> None:
    try:
        path = snapshot_download(repo_id, revision=revision, token=token, ignore_patterns=ignore)
        log.info("ready: %s -> %s", repo_id, path)
    except Exception as exc:  # noqa: BLE001
        log.warning("download failed for %s (%s), checking local cache", repo_id, type(exc).__name__)
        snapshot_download(repo_id, revision=revision, local_files_only=True, ignore_patterns=ignore)
        log.info("using cached %s", repo_id)


def main() -> int:
    s = get_settings()
    setup_logging(s.log_level)
    if s.asr_engine == "voxtral":
        # consolidated.safetensors duplicates the weights in Mistral's native format (vLLM); Transformers
        # only needs model.safetensors. Skipping it saves ~9 GB.
        fetch(s.asr_model_id, s.asr_revision, s.hf_token, ignore=["consolidated.safetensors", "assets/*"])
    if s.lid_engine == "lidstral":
        fetch(s.lid_model_id, s.lid_revision, s.hf_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
