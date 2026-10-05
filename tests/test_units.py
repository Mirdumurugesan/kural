import numpy as np

from app import audio as A
from app.core.security import redact
from app.lang import detect
from app.rag.store import HybridIndex
from app.config import ROOT


def test_detect_scripts():
    assert detect("பிஎம் கிசான் பணம்")["language"] == "ta-IN"
    assert detect("PM Kisan pannam varala, enna pannanum")["language"] == "ta-IN"  # romanised Tanglish
    t = detect("PM Kisan scheme-ல எவ்வளவு money கிடைக்கும்")
    assert t["language"] == "ta-IN" and t["code_mixed"]
    assert detect("How much is PM Kisan?")["language"] == "en-IN"
    assert detect("पीएम किसान")["language"] == "hi-IN"


def test_redact_variants():
    text, found = redact("PAN ABCDE1234F, mail a@b.com, +91 98765 43210, acct 123456789012345")
    assert "ABCDE1234F" not in text and "a@b.com" not in text and "98765" not in text
    assert {"PAN", "EMAIL", "PHONE", "ACCOUNT"} <= set(found)
    assert redact("6,000 rupees in 3 instalments")[1] == []  # amounts are not PII


def test_segmentation_respects_limit_and_cuts_in_silence():
    sr = A.SR
    speech = (np.sin(np.arange(sr * 23) / 5) * 8000).astype(np.int16)
    gap = np.zeros(sr // 2, dtype=np.int16)
    pcm = np.concatenate([speech, gap, speech, gap, speech])  # ~70 s
    segs = A.segment(pcm, max_s=28)
    assert all(len(s) <= 28 * sr for s in segs)
    assert abs(sum(len(s) for s in segs) - len(pcm)) < sr  # nothing lost
    # first cut should land inside the silent gap (23.0 - 23.5 s)
    assert 23 * sr <= len(segs[0]) <= int(23.5 * sr) + 320


def test_analyze_flags_noise():
    rng = np.random.default_rng(0)
    clean = np.concatenate([np.zeros(8000), np.sin(np.arange(32000) / 4) * 10000]).astype(np.int16)
    noisy = A.simulate_phone_line(clean, snr_db=0)
    assert A.analyze(clean).snr_db > A.analyze(noisy).snr_db
    assert A.analyze(noisy).noisy


def test_retrieval_quality_on_kb():
    idx = HybridIndex(); idx.load_dir(ROOT / "kb")
    cases = {
        "பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்": "pm-kisan",
        "மகளிர் உரிமைத் தொகை தகுதி": "kmut",
        "மருத்துவக் காப்பீடு அட்டை": "pmjay-cmchis",
        "crop insurance premium rabi": "pmfby",
        "kisan credit card interest rate": "kcc",
        "கல்லூரி மாணவிகளுக்கு மாதம் 1000 ரூபாய்": "pudhumai-penn-tamil-pudhalvan",
    }
    for q, doc in cases.items():
        hits = idx.search(q, k=3, min_score=0.10)
        assert hits and hits[0].chunk.doc_id == doc, (q, [h.chunk.doc_id for h in hits])
    assert idx.search("bitcoin price today", min_score=0.10) == []
