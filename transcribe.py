"""
V20: local Whisper transcription. Loads the model once at import time
(like retrieval.py does with sentence-transformers) since loading it per
request would be far too slow.

Requires ffmpeg on the system PATH -- Whisper shells out to it to decode
audio. On Windows: download an ffmpeg build, add its /bin folder to PATH,
restart the terminal.
"""

import os
import tempfile
import whisper
from config import WHISPER_MODEL

_model = whisper.load_model(WHISPER_MODEL)


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".wav") -> str:
    """Writes audio to a temp file (Whisper/ffmpeg need a real file path,
    not an in-memory buffer) and returns the transcribed text."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        result = _model.transcribe(path)
        return result["text"].strip()
    finally:
        os.unlink(path)