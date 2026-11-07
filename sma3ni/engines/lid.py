"""Language / dialect identification with Morocco-MTNRA-Labs/LIDstral-Arabic (fastText + MLP, CPU, ~ms)."""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class LidResult:
    label: str
    confidence: float


class FakeLidEngine:
    def identify(self, text: str) -> LidResult:
        return LidResult("ary", 0.99)


class LidstralEngine:
    def __init__(self, model_id: str, revision: str | None) -> None:
        from huggingface_hub import snapshot_download

        # Files were fetched by the `models` job; workers run offline on an internal network.
        path = snapshot_download(model_id, revision=revision, local_files_only=True)
        # The model ships its own loader (classify.py) and pickled calibration: this is code
        # from the model repo, so pin LID_REVISION to a reviewed commit in production.
        if path not in sys.path:
            sys.path.insert(0, path)
        from classify import ArabicLID  # type: ignore[import-not-found]

        self.model = ArabicLID(path).load()

    def identify(self, text: str) -> LidResult:
        out = self.model.predict([text.replace("\n", " ")])
        first = out[0] if isinstance(out, (list, tuple)) else out
        return LidResult(str(first["label"]), float(first.get("confidence", 0.0)))


def build_lid_engine(settings):
    if settings.lid_engine == "fake":
        return FakeLidEngine()
    if settings.lid_engine == "lidstral":
        return LidstralEngine(settings.lid_model_id, settings.lid_revision)
    raise RuntimeError(f"unknown LID_ENGINE {settings.lid_engine!r}")
