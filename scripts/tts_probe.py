"""Find which text features make Timbre return errors. Prints status per variant (few credits)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402

s = get_settings()
BASE = "கலைஞர் மகளிர் உரிமைத் தொகை திட்டத்தில் தகுதியான குடும்பத் தலைவிகளுக்கு மாதம்"
VARIANTS = {
    "A plain tamil": BASE + " ஆயிரம் ரூபாய் வழங்கப்படுகிறது.",
    "B digits 1,000": BASE + " 1,000 ரூபாய் வழங்கப்படுகிறது.",
    "C digits 1000": BASE + " 1000 ரூபாய் வழங்கப்படுகிறது.",
    "D url": "pmkisan.gov.in இல் நிலையைப் பார்க்கலாம்.",
    "E quotes": 'இணையதளத்தில் "Know Your Status" பகுதியில் பார்க்கலாம்.',
    "F english word": "eKYC முடிக்காதது ஒரு காரணம்.",
    "G date": "இந்தத் திட்டம் 15 செப்டம்பர் 2023 அன்று தொடங்கப்பட்டது.",
    "H long 240": (BASE + " ஆயிரம் ரூபாய் நேரடியாக வங்கிக் கணக்கில் வழங்கப்படுகிறது. ") * 2,
}
PROFILES = {
    "mp3": {"sample_rate": 24000, "num_channels": 1, "sample_width": 2, "container": "mp3", "bitrate": "64k"},
    "wav": {"sample_rate": 24000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
}
with httpx.Client(timeout=60) as c:
    for prof, cfg in PROFILES.items():
        for name, text in VARIANTS.items():
            for voice in (["Trisha"] if name != "A plain tamil" else ["Trisha", "Vedika"]):
                r = c.post(f"{s.gnani_base_url}/api/v1/tts/inference",
                           headers={"X-API-Key-ID": s.gnani_api_key},
                           json={"text": text, "voice": voice, "model": s.tts_model, "language": "ta-IN",
                                 "speed": 1.0, "audio_config": cfg})
                body = r.text[:160].replace("\n", " ") if r.status_code != 200 else f"{len(r.content)} bytes"
                print(f"{prof:4} {voice:7} {name:16} -> {r.status_code}  {body}", flush=True)
                time.sleep(2.5)
