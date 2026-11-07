"""Identify audio containers from magic bytes. Client-sent Content-Type is never trusted."""
from __future__ import annotations

MEDIA_TYPES = {
    "ogg": "audio/ogg",     # WhatsApp voice notes (Opus)
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",   # browser MediaRecorder
    "flac": "audio/flac",
    "amr": "audio/amr",     # older phones / call centres
}


def sniff_audio(head: bytes) -> str | None:
    if head.startswith(b"OggS"):
        return "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"#!AMR"):
        return "amr"
    return None
