"""Local text-to-speech via Piper (https://github.com/OHF-Voice/piper1-gpl) —
free, fully local, no per-call API cost. The one place any current or future
TTS caller (today: the /speak Discord command; later: the planned /join
live-voice-channel command, see BACKLOG.md) calls through.

This is deliberately just "text in, WAV bytes out" — no hardware, no
STT, no wake word. See sunny-vault/docs/architecture/tts-piper.md for how
this differs from the full Sonic/Piper voice-io.md pipeline, which is gated
on physical Clock hardware that doesn't exist yet.
"""

import io
import logging
import subprocess
import sys
import wave
from pathlib import Path
from typing import Optional

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_voice = None
_voice_path: Optional[Path] = None


def _ensure_voice_downloaded(voice_name: str, voices_dir: Path) -> Path:
    """Downloads the voice model if it isn't already on disk. Skips the
    download entirely if the .onnx file already exists — piper.download_voices
    also does its own skip-if-present check, but checking here first avoids
    even spawning the subprocess on the common case."""
    onnx_path = voices_dir / f"{voice_name}.onnx"
    if onnx_path.exists():
        return onnx_path

    voices_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading Piper voice '{voice_name}' to {voices_dir} (one-time, ~60MB)...")
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", voice_name, "--download-dir", str(voices_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    if not onnx_path.exists():
        raise RuntimeError(f"Piper voice download reported success but {onnx_path} is missing")
    return onnx_path


def _get_voice():
    """Lazily loads and caches the PiperVoice for the process lifetime —
    loading is real cost (~1s to read the ONNX model and start an
    onnxruntime session), synthesis itself is fast, so this is worth
    caching rather than reloading per call."""
    global _voice, _voice_path

    settings = get_settings()
    onnx_path = _ensure_voice_downloaded(settings.piper_voice, settings.piper_voices_dir)

    if _voice is None or _voice_path != onnx_path:
        from piper import PiperVoice

        logger.info(f"Loading Piper voice from {onnx_path}")
        _voice = PiperVoice.load(str(onnx_path))
        _voice_path = onnx_path

    return _voice


def synthesize_wav_bytes(text: str) -> bytes:
    """Synthesizes `text` to WAV audio bytes. Blocking (model load, on-disk
    I/O, CPU-bound inference) — callers on an event loop should run this via
    asyncio.to_thread, same as llm_client._call_claude_sync. Raises on
    failure (no network for a first-time model download, corrupt model,
    etc.) — callers are responsible for turning that into an honest
    user-facing message, matching this app's fail-loud-to-the-caller
    contract rather than swallowing errors here."""
    voice = _get_voice()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buf.getvalue()


def is_voice_downloaded() -> bool:
    """Status check only — no network call, no model load. Used by
    setup_guides.py to report connection status without side effects."""
    settings = get_settings()
    return (settings.piper_voices_dir / f"{settings.piper_voice}.onnx").exists()
