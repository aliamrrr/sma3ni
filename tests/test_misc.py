from sma3ni.audio_sniff import sniff_audio
from sma3ni.ids import is_tracking_code, new_tracking_code


def test_tracking_codes_are_valid_and_unique():
    codes = {new_tracking_code() for _ in range(2000)}
    assert len(codes) == 2000
    assert all(is_tracking_code(c) for c in codes)
    assert not is_tracking_code("SM-00000-11111")
    assert not is_tracking_code("SM-ABCDE-FGHIJ'; DROP TABLE")


def test_sniff_audio():
    assert sniff_audio(b"OggS\x00\x02" + b"\x00" * 10) == "ogg"
    assert sniff_audio(b"RIFF\x24\x00\x00\x00WAVEfmt ") == "wav"
    assert sniff_audio(b"ID3\x04\x00") == "mp3"
    assert sniff_audio(b"\x00\x00\x00\x20ftypM4A ") == "m4a"
    assert sniff_audio(b"\x1aE\xdf\xa3\x9f") == "webm"
    assert sniff_audio(b"#!AMR\n") == "amr"
    assert sniff_audio(b"<?php system($_GET[0]);") is None
    assert sniff_audio(b"%PDF-1.7") is None
