"""Script-based language & code-mix detection for routing replies and TTS voices."""
from __future__ import annotations

import re

RANGES = {
    "ta-IN": (0x0B80, 0x0BFF), "hi-IN": (0x0900, 0x097F), "te-IN": (0x0C00, 0x0C7F),
    "kn-IN": (0x0C80, 0x0CFF), "ml-IN": (0x0D00, 0x0D7F), "bn-IN": (0x0980, 0x09FF),
    "gu-IN": (0x0A80, 0x0AFF), "pa-IN": (0x0A00, 0x0A7F),
}
LANG_NAMES = {"ta-IN": "Tamil", "en-IN": "English", "hi-IN": "Hindi", "te-IN": "Telugu", "kn-IN": "Kannada",
              "ml-IN": "Malayalam", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "mr-IN": "Marathi"}

# Common romanised Tamil words -> lets us spot Tanglish typed in Latin script
TANGLISH_HINTS = {
    "enna", "yenna", "epdi", "eppadi", "evvalavu", "evlo", "evalo", "panam", "kaasu", "venum", "venuma", "vendum",
    "irukku", "irukka", "illa", "illai", "sollunga", "theriyuma", "eppo", "enga", "naan", "naanga", "unga", "ungalukku",
    "kedaikum", "kidaikkum", "kedaikuma", "thittam", "varala", "vandhuchu", "pannanum", "pannalama", "panradhu",
    "panrathu", "aana", "aagala", "kulla", "ku", "la", "ah", "dhaan", "thaan", "romba", "konjam", "yaarukku",
    "ponnungalukku", "pasanga", "vaanga", "podanum", "edhu", "ethu", "appo", "ippo", "seri", "sari",
}
WEAK_HINTS = {"ku", "la", "ah", "seri", "sari", "enga", "unga", "aana"}  # also common in English/names


def detect(text: str) -> dict:
    letters = [c for c in text if c.isalpha() or 0x0900 <= ord(c) <= 0x0DFF]
    if not letters:
        return {"language": "en-IN", "code_mixed": False, "ratio": {}}
    counts = {k: 0 for k in RANGES}
    latin = 0
    for c in letters:
        o = ord(c)
        if c.isascii():
            latin += 1
            continue
        for k, (lo, hi) in RANGES.items():
            if lo <= o <= hi:
                counts[k] += 1
                break
    total = len(letters)
    best = max(counts, key=counts.get)
    native_ratio = counts[best] / total
    latin_ratio = latin / total
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    if native_ratio >= 0.2:
        lang = best
        mixed = latin_ratio >= 0.1
    elif len(tokens & (TANGLISH_HINTS - WEAK_HINTS)) >= 1 or len(tokens & WEAK_HINTS) >= 2:
        lang, mixed = "ta-IN", True  # romanised Tamil
    else:
        lang, mixed = "en-IN", False
    return {"language": lang, "code_mixed": mixed,
            "ratio": {"native": round(native_ratio, 2), "latin": round(latin_ratio, 2)}}
