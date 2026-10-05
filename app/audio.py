"""Audio front-end for noisy telephony.

1. ffmpeg decode of any container (webm/ogg from browsers, 8 kHz phone WAV, mp3...)
2. Clean-up chain tuned for phone audio:
   highpass 80 Hz (hum/rumble) -> lowpass 7.5 kHz -> afftdn spectral denoise
   -> dynaudnorm (lift quiet callers) -> resample 16 kHz mono s16
3. Quality metrics (duration, estimated SNR, clipping) for analytics + routing
4. Silence-aware segmentation into <=28 s chunks for Prisma REST
"""
from __future__ import annotations

import asyncio
import io
import shutil
import wave
from dataclasses import dataclass

import numpy as np

from app.core.errors import BadRequest

SR = 16000
FILTER_CHAIN = "highpass=f=80,lowpass=f=7500,afftdn=nf=-25:tn=1,dynaudnorm=f=150:g=15"


@dataclass
class AudioInfo:
    duration_s: float
    snr_db: float
    clipping_ratio: float
    noisy: bool


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def normalize(raw: bytes, denoise: bool = True) -> np.ndarray:
    """Decode + clean any audio into 16 kHz mono int16 samples."""
    if not raw:
        raise BadRequest("Empty audio")
    if not ffmpeg_available():
        return _decode_wav_fallback(raw)
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0"]
    if denoise:
        args += ["-af", FILTER_CHAIN]
    args += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"]
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate(raw)
    if proc.returncode != 0 or not out:
        raise BadRequest("Could not decode audio", details={"ffmpeg": err.decode(errors="ignore")[:300]})
    return np.frombuffer(out, dtype=np.int16)


def _decode_wav_fallback(raw: bytes) -> np.ndarray:
    try:
        with wave.open(io.BytesIO(raw)) as w:
            frames = w.readframes(w.getnframes())
            pcm = np.frombuffer(frames, dtype=np.int16)
            if w.getnchannels() > 1:
                pcm = pcm.reshape(-1, w.getnchannels()).mean(axis=1).astype(np.int16)
            if w.getframerate() != SR:
                idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * SR / w.getframerate()))
                pcm = np.interp(idx, np.arange(len(pcm)), pcm).astype(np.int16)
            return pcm
    except wave.Error as exc:
        raise BadRequest("Only WAV supported when ffmpeg is unavailable") from exc


def analyze(pcm: np.ndarray) -> AudioInfo:
    dur = len(pcm) / SR
    if len(pcm) < SR // 10:
        return AudioInfo(dur, 0.0, 0.0, True)
    x = pcm.astype(np.float32) / 32768.0
    frame = SR // 50  # 20 ms
    n = len(x) // frame
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    noise = np.percentile(rms, 10)
    speech = np.percentile(rms, 90)
    snr = float(20 * np.log10(speech / max(noise, 1e-6)))
    clip = float(np.mean(np.abs(x) > 0.99))
    return AudioInfo(round(dur, 2), round(snr, 1), round(clip, 4), snr < 15)


def segment(pcm: np.ndarray, max_s: int = 28, search_s: float = 8.0) -> list[np.ndarray]:
    """Split at the quietest 20 ms frame inside the last `search_s` seconds of each window,
    so we never cut a word in half."""
    max_len = max_s * SR
    out, start = [], 0
    while len(pcm) - start > max_len:
        win_start = start + max_len - int(search_s * SR)
        window = pcm[win_start : start + max_len].astype(np.float32)
        frame = SR // 50
        n = len(window) // frame
        energy = (window[: n * frame].reshape(n, frame) ** 2).mean(axis=1)
        cut = win_start + int(np.argmin(energy)) * frame
        out.append(pcm[start:cut])
        start = cut
    out.append(pcm[start:])
    return [s for s in out if len(s) > SR // 4]


def to_wav(pcm: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


def simulate_phone_line(pcm: np.ndarray, snr_db: float = 10.0, seed: int = 7) -> np.ndarray:
    """Degrade clean audio the way a cheap phone call does: 8 kHz narrowband,
    G.711 mu-law companding, background noise at a target SNR. Used for the demo's
    'phone-line mode' and for the noise robustness benchmark (scripts/eval_noise.py)."""
    rng = np.random.default_rng(seed)
    x = pcm.astype(np.float32) / 32768.0
    # narrowband: crude 3.4 kHz low-pass (moving average) then 16k->8k->16k
    k = np.ones(3, dtype=np.float32) / 3
    x = np.convolve(x, k, mode="same")[::2]
    # mu-law round trip (mu=255)
    mu = 255.0
    y = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    y = np.round(y * 127) / 127
    x = np.sign(y) * (np.power(1 + mu, np.abs(y)) - 1) / mu
    x = np.repeat(x, 2)[: len(pcm)]
    # pink-ish noise (integrated white noise, high-passed) at target SNR
    white = rng.standard_normal(len(x)).astype(np.float32)
    pink = np.convolve(white, np.ones(8, dtype=np.float32) / 8, mode="same")
    sig_p = np.mean(x**2) + 1e-12
    noise_p = np.mean(pink**2) + 1e-12
    x = x + pink * np.sqrt(sig_p / (noise_p * 10 ** (snr_db / 10)))
    return np.clip(x * 32768, -32768, 32767).astype(np.int16)
