"""Hybrid retriever tuned for Tamil / Tanglish / English.

Tamil is agglutinative ("திட்டத்தில்", "திட்டத்திற்கு", "திட்டம்" are one word), so plain
word BM25 misses a lot. We fuse two rankers with Reciprocal Rank Fusion:
  * BM25 over word tokens (exact terms, numbers, scheme names)
  * TF-IDF cosine over character 3-5 grams (robust to suffixes, STT spelling drift)
Pure Python + numpy: no GPU, no vector DB, runs on a 1 vCPU box.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

WORD_RE = re.compile(r"[\w஀-௿ऀ-ॿ]+", re.UNICODE)
BIAS_WORD_RE = re.compile(r"[A-Za-z\u0B80-\u0BFF\u0900-\u097F]+")
FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    text: str
    source_url: str
    meta: dict = field(default_factory=dict)

    @property
    def body(self) -> str:
        """Passage text without the retrieval-only prefix line (title | aliases | questions)."""
        return self.text.partition("\n")[2].strip()


@dataclass
class Hit:
    chunk: Chunk
    score: float


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def char_ngrams(text: str, lo: int = 3, hi: int = 5) -> list[str]:
    grams: list[str] = []
    for w in words(text):
        w = f" {w} "
        for n in range(lo, hi + 1):
            grams += [w[i : i + n] for i in range(max(1, len(w) - n + 1))]
    return grams


def parse_markdown(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    m = FRONT_RE.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    return meta, raw


def chunk_document(doc_id: str, meta: dict, body: str, max_chars: int = 900) -> list[Chunk]:
    """Split on headings, then pack paragraphs up to max_chars. Each chunk is
    prefixed with the doc title + aliases so retrieval works in either script."""
    title = meta.get("title", doc_id)
    prefix = f"{title} | {meta.get('aliases', '')}"
    sections = re.split(r"\n(?=#{1,3} )", body.strip())
    chunks: list[Chunk] = []
    for sec in sections:
        heading = sec.splitlines()[0].lstrip("# ").strip() if sec.startswith("#") else ""
        buf = ""
        for para in [p.strip() for p in sec.split("\n\n") if p.strip()]:
            if len(buf) + len(para) > max_chars and buf:
                chunks.append(_mk(doc_id, len(chunks), title, heading, prefix, buf, meta))
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append(_mk(doc_id, len(chunks), title, heading, prefix, buf, meta))
    # FAQ-style phrasings ("how much money?") route short spoken questions to the summary chunk
    if chunks and meta.get("questions"):
        first = chunks[0]
        head, _, rest = first.text.partition("\n")
        first.text = f"{head} | {meta['questions']}\n{rest}"
    return chunks


def _mk(doc_id, i, title, heading, prefix, text, meta) -> Chunk:
    heading = re.sub(r"\s*\([^)]*\)\s*$", "", heading)  # "(பணம் வரல, …)" synonyms are for search, not display
    return Chunk(f"{doc_id}#{i}", doc_id, f"{title} — {heading}" if heading else title,
                 f"{prefix}\n{text.strip()}", meta.get("source_url", ""), meta)


class HybridIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.chunks: list[Chunk] = []
        self.docs: dict[str, dict] = {}
        self._lock = threading.RLock()

    # ---------- build ----------
    def load_dir(self, kb_dir: Path) -> int:
        chunks, docs = [], {}
        for path in sorted(kb_dir.glob("**/*.md")):
            if path.name.lower() == "readme.md":
                continue
            meta, body = parse_markdown(path)
            doc_id = path.stem
            docs[doc_id] = {**meta, "path": str(path), "chars": len(body)}
            chunks += chunk_document(doc_id, meta, body)
        self.build(chunks, docs)
        return len(chunks)

    def build(self, chunks: list[Chunk], docs: dict | None = None) -> None:
        tok = [words(c.text) for c in chunks]
        grams = [Counter(char_ngrams(c.text)) for c in chunks]
        df_w: Counter = Counter(t for ts in tok for t in set(ts))
        df_g: Counter = Counter(g for gs in grams for g in gs)
        n = max(1, len(chunks))
        idf_g = {g: math.log((1 + n) / (1 + d)) + 1 for g, d in df_g.items()}
        vocab = {g: i for i, g in enumerate(idf_g)}
        mat = np.zeros((len(chunks), len(vocab)), dtype=np.float32)
        for r, gs in enumerate(grams):
            for g, c in gs.items():
                mat[r, vocab[g]] = (1 + math.log(c)) * idf_g[g]
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        mat /= np.maximum(norms, 1e-9)
        with self._lock:
            self.chunks, self.docs = chunks, docs or {}
            self._tok = [Counter(t) for t in tok]
            self._len = np.array([len(t) for t in tok], dtype=np.float32)
            self._avg = float(self._len.mean()) if len(chunks) else 1.0
            self._idf_w = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df_w.items()}
            self._vocab, self._idf_g, self._mat = vocab, idf_g, mat

    # ---------- query ----------
    def _bm25(self, q: list[str]) -> np.ndarray:
        scores = np.zeros(len(self.chunks), dtype=np.float32)
        for t in set(q):
            idf = self._idf_w.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self._tok):
                f = tf.get(t, 0)
                if f:
                    scores[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self._len[i] / self._avg))
        return scores

    def _cosine(self, query: str) -> np.ndarray:
        v = np.zeros(len(self._vocab), dtype=np.float32)
        for g, c in Counter(char_ngrams(query)).items():
            j = self._vocab.get(g)
            if j is not None:
                v[j] = (1 + math.log(c)) * self._idf_g[g]
        nv = np.linalg.norm(v)
        if nv == 0:
            return np.zeros(len(self.chunks), dtype=np.float32)
        return self._mat @ (v / nv)

    def search(self, query: str, k: int = 4, min_score: float = 0.0) -> list[Hit]:
        with self._lock:
            if not self.chunks:
                return []
            bm = self._bm25(words(query))
            cos = self._cosine(query)
            rrf = np.zeros(len(self.chunks), dtype=np.float32)
            for arr in (bm, cos):
                order = np.argsort(-arr)
                for rank, i in enumerate(order[:50]):
                    if arr[i] > 0:
                        rrf[i] += 1.0 / (60 + rank)
            order = np.argsort(-rrf)[:k]
            # confidence gate uses the semantic signal (bounded 0..1)
            return [Hit(self.chunks[i], float(cos[i])) for i in order if rrf[i] > 0 and cos[i] >= min_score]

    def vocabulary_for_bias(self, limit: int = 100) -> list[str]:
        """Scheme names / aliases -> Prisma word boosting (single alphabetic words only)."""
        out: list[str] = []
        seen: set[str] = set()
        for d in self.docs.values():
            for w in re.split(r"[,\s|]+", d.get("aliases", "")):
                if BIAS_WORD_RE.fullmatch(w) and len(w) > 2 and w.lower() not in seen:
                    seen.add(w.lower())
                    out.append(w)
        return out[:limit]
