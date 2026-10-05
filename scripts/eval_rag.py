"""Offline retrieval benchmark (no credits). Tamil script, romanised Tanglish, code-mixed, English.
Run:  python scripts/eval_rag.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import ROOT  # noqa: E402
from app.rag.store import HybridIndex  # noqa: E402

CASES = [
    # (question, expected doc, style)
    ("பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்", "pm-kisan", "tamil"),
    ("கிசான் பணம் வரவில்லை என்ன செய்வது", "pm-kisan", "tamil"),
    ("PM Kisan panam varala enna pannanum", "pm-kisan", "tanglish-roman"),
    ("PM Kisan eKYC எப்படி பண்றது", "pm-kisan", "code-mixed"),
    ("How much does PM-KISAN pay per year", "pm-kisan", "english"),
    ("மகளிர் உரிமைத் தொகை யாருக்கு கிடைக்கும்", "kmut", "tamil"),
    ("magalir urimai thogai reject aana appeal pannalama", "kmut", "tanglish-roman"),
    ("Magalir urimai thogai income limit எவ்வளவு", "kmut", "code-mixed"),
    ("மருத்துவக் காப்பீடு அட்டை எங்கே வாங்குவது", "pmjay-cmchis", "tamil"),
    ("hospital la free treatment evvalavu varaikkum", "pmjay-cmchis", "tanglish-roman"),
    ("CMCHIS helpline number", "pmjay-cmchis", "english"),
    ("பயிர் காப்பீடு பிரீமியம் எவ்வளவு", "pmfby", "tamil"),
    ("crop damage aana evlo neram kulla report pannanum", "pmfby", "tanglish-roman"),
    ("crop insurance premium for rabi", "pmfby", "english"),
    ("கல்லூரி மாணவிகளுக்கு மாதம் 1000 ரூபாய் திட்டம்", "pudhumai-penn-tamil-pudhalvan", "tamil"),
    ("Pudhumai Penn scheme ku epdi apply panradhu", "pudhumai-penn-tamil-pudhalvan", "tanglish-roman"),
    ("Tamil Pudhalvan scheme for boys", "pudhumai-penn-tamil-pudhalvan", "english"),
    ("கிசான் கடன் அட்டை வட்டி எவ்வளவு", "kcc", "tamil"),
    ("KCC loan ku collateral venuma", "kcc", "tanglish-roman"),
    ("Kisan credit card interest rate", "kcc", "english"),
]
NEGATIVE = ["bitcoin price today", "IPL score enna", "நாளை மழை வருமா"]


def main() -> int:
    idx = HybridIndex()
    idx.load_dir(ROOT / "kb")
    top1 = top3 = 0
    by_style: dict[str, list[int]] = {}
    print(f"{'style':15} {'hit@1':5} question")
    for q, doc, style in CASES:
        hits = idx.search(q, k=3, min_score=0.10)
        ids = [h.chunk.doc_id for h in hits]
        h1, h3 = int(bool(ids) and ids[0] == doc), int(doc in ids)
        top1 += h1; top3 += h3
        by_style.setdefault(style, []).append(h1)
        print(f"{style:15} {'✓' if h1 else ('~' if h3 else '✗'):5} {q}")
    neg_ok = sum(1 for q in NEGATIVE if not idx.search(q, k=3, min_score=0.10))
    n = len(CASES)
    print(f"\nTop-1 accuracy: {top1}/{n} = {top1 / n:.0%}   Top-3: {top3}/{n} = {top3 / n:.0%}")
    for s, v in by_style.items():
        print(f"  {s:15} top-1 {sum(v)}/{len(v)}")
    print(f"Out-of-scope correctly rejected: {neg_ok}/{len(NEGATIVE)}")
    return 0 if top3 / n >= 0.85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
