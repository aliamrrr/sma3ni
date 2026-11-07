"""Speech-to-text engines.

VoxtralEngine runs Morocco-MTNRA-Labs/Voxtral-Mini-4B-Realtime-Arabic with
Transformers, offline (whole voice note at once, no streaming). ASR_DEVICE=cuda
on a GPU instance (AWS g6/g5), cpu otherwise.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass

from ..errors import PermanentError

SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class Transcript:
    text: str
    audio_seconds: float | None
    model: str


def decode_audio(data: bytes, max_seconds: int, sample_rate: int = SAMPLE_RATE):
    """Any container (ogg/opus, m4a, mp3, webm, amr...) -> mono float32 PCM via ffmpeg."""
    import numpy as np

    # m4a needs a seekable input, so go through a tmpfs file rather than a pipe.
    with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".audio") as tmp:
        tmp.write(data)
        tmp.flush()
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", tmp.name,
               "-t", str(max_seconds + 1), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        except subprocess.TimeoutExpired as exc:
            raise PermanentError("audio decoding timed out") from exc
    if proc.returncode != 0:
        raise PermanentError("audio could not be decoded")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    seconds = len(audio) / sample_rate
    if seconds > max_seconds:
        raise PermanentError(f"audio longer than {max_seconds}s")
    if seconds < 0.5:
        raise PermanentError("audio shorter than 0.5s")
    return audio


class FakeAsrEngine:
    """Development engine: no model, no ffmpeg. Lets you run the whole pipeline on a laptop."""

    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, data: bytes) -> Transcript:
        return Transcript(self.text, None, "fake")


class VoxtralEngine:
    def __init__(self, model_id: str, revision: str | None, dtype: str, threads: int, max_seconds: int,
                 device: str = "cpu") -> None:
        import torch
        from transformers import AutoProcessor, VoxtralRealtimeForConditionalGeneration

        if device.startswith("cuda") and not torch.cuda.is_available():
            # Fail loudly: silently falling back to CPU would make a GPU deployment 10-50x slower.
            raise RuntimeError("ASR_DEVICE=cuda but no GPU is visible (driver, nvidia-container-toolkit, "
                               "or the CUDA image/compose override missing?)")
        torch.set_num_threads(threads)
        self.torch = torch
        self.model_id = model_id
        self.max_seconds = max_seconds
        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision)
        self.model = VoxtralRealtimeForConditionalGeneration.from_pretrained(
            model_id, revision=revision, dtype=getattr(torch, dtype),
        ).to(device).eval()
        self.sample_rate = self.processor.feature_extractor.sampling_rate

    def transcribe(self, data: bytes) -> Transcript:
        audio = decode_audio(data, self.max_seconds, self.sample_rate)
        inputs = self.processor(audio, return_tensors="pt")
        inputs = inputs.to(self.model.device, dtype=self.model.dtype)
        with self.torch.inference_mode():
            outputs = self.model.generate(**inputs, do_sample=False)
        text = self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
        return Transcript(text.strip(), round(len(audio) / self.sample_rate, 2), self.model_id)


def build_asr_engine(settings):
    if settings.asr_engine == "fake":
        return FakeAsrEngine(settings.fake_transcript)
    if settings.asr_engine == "voxtral":
        return VoxtralEngine(settings.asr_model_id, settings.asr_revision, settings.asr_dtype,
                             settings.asr_threads, settings.max_audio_seconds, settings.asr_device)
    raise RuntimeError(f"unknown ASR_ENGINE {settings.asr_engine!r}")
