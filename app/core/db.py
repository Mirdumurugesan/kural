"""SQLite persistence (WAL mode). Swap DB_PATH for a mounted volume in prod;
the schema is plain SQL so moving to Postgres is a driver change."""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, channel TEXT, language TEXT, created_at REAL, caller_hash TEXT
);
CREATE TABLE IF NOT EXISTS turns (
  id TEXT PRIMARY KEY, session_id TEXT, created_at REAL, channel TEXT,
  language TEXT, transcript TEXT, answer TEXT, sources TEXT, confidence REAL,
  escalated INTEGER, audio_seconds REAL, snr_db REAL, noisy INTEGER,
  stt_ms INTEGER, rag_ms INTEGER, llm_ms INTEGER, tts_ms INTEGER, total_ms INTEGER,
  llm_model TEXT, fallback INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS ix_turns_created ON turns(created_at);
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY, turn_id TEXT, rating INTEGER, comment TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, kind TEXT, units REAL, credits REAL
);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, turn_id TEXT, session_id TEXT, reason TEXT, status TEXT, created_at REAL
);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ---- sessions / turns ----
    def ensure_session(self, session_id: str | None, channel: str, language: str, caller_hash: str = "") -> str:
        sid = session_id or uuid.uuid4().hex
        self._exec("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?,?)", (sid, channel, language, time.time(), caller_hash))
        return sid

    def history(self, session_id: str, limit: int = 4) -> list[dict]:
        rows = self.q("SELECT transcript, answer FROM turns WHERE session_id=? AND error IS NULL "
                      "ORDER BY created_at DESC LIMIT ?", (session_id, limit))
        return list(reversed(rows))

    def add_turn(self, **t) -> str:
        tid = t.pop("id", None) or uuid.uuid4().hex
        t["sources"] = json.dumps(t.get("sources", []), ensure_ascii=False)
        cols = ["id", "created_at"] + list(t)
        self._exec(f"INSERT INTO turns ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                   (tid, time.time(), *t.values()))
        return tid

    def add_feedback(self, turn_id: str, rating: int, comment: str = "") -> None:
        self._exec("INSERT INTO feedback VALUES (?,?,?,?,?)", (uuid.uuid4().hex, turn_id, rating, comment, time.time()))

    def add_ticket(self, turn_id: str, session_id: str, reason: str) -> str:
        tid = "TKT-" + uuid.uuid4().hex[:8].upper()
        self._exec("INSERT INTO tickets VALUES (?,?,?,?,?,?)", (tid, turn_id, session_id, reason, "open", time.time()))
        return tid

    # ---- credits ----
    def add_usage(self, kind: str, units: float, credits: float) -> None:
        self._exec("INSERT INTO usage (created_at, kind, units, credits) VALUES (?,?,?,?)", (time.time(), kind, units, credits))

    def credits_used(self) -> float:
        return float(self.q("SELECT COALESCE(SUM(credits),0) c FROM usage")[0]["c"])

    # ---- analytics ----
    def analytics(self, since_s: float = 7 * 86400) -> dict:
        since = time.time() - since_s
        tot = self.q("""SELECT COUNT(*) n, AVG(total_ms) avg_ms, AVG(stt_ms) stt, AVG(llm_ms) llm, AVG(tts_ms) tts,
                     AVG(confidence) conf, SUM(escalated) esc, SUM(noisy) noisy, SUM(fallback) fb,
                     SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) errors, AVG(snr_db) snr
                     FROM turns WHERE created_at>?""", (since,))[0]
        p95 = self.q("SELECT total_ms FROM turns WHERE created_at>? AND total_ms IS NOT NULL ORDER BY total_ms", (since,))
        lat = [r["total_ms"] for r in p95]
        by_lang = self.q("SELECT language, COUNT(*) n FROM turns WHERE created_at>? GROUP BY language ORDER BY n DESC", (since,))
        by_chan = self.q("SELECT channel, COUNT(*) n FROM turns WHERE created_at>? GROUP BY channel", (since,))
        fb = self.q("SELECT AVG(rating) avg, COUNT(*) n FROM feedback WHERE created_at>?", (since,))[0]
        daily = self.q("""SELECT date(created_at,'unixepoch') d, COUNT(*) n FROM turns WHERE created_at>?
                       GROUP BY d ORDER BY d""", (since,))
        top_docs: dict[str, int] = {}
        for r in self.q("SELECT sources FROM turns WHERE created_at>?", (since,)):
            for s in json.loads(r["sources"] or "[]"):
                top_docs[s.get("doc_id", "?")] = top_docs.get(s.get("doc_id", "?"), 0) + 1
        unanswered = self.q("""SELECT transcript, created_at FROM turns WHERE created_at>? AND escalated=1
                           ORDER BY created_at DESC LIMIT 20""", (since,))
        return {
            "turns": tot["n"], "avg_latency_ms": _r(tot["avg_ms"]),
            "p95_latency_ms": lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)] if lat else None,
            "avg_stage_ms": {"stt": _r(tot["stt"]), "llm": _r(tot["llm"]), "tts": _r(tot["tts"])},
            "avg_confidence": _r(tot["conf"], 3), "escalations": tot["esc"] or 0,
            "noisy_calls": tot["noisy"] or 0, "avg_snr_db": _r(tot["snr"], 1),
            "llm_fallbacks": tot["fb"] or 0, "errors": tot["errors"] or 0,
            "by_language": by_lang, "by_channel": by_chan, "daily": daily,
            "feedback": {"avg": _r(fb["avg"], 2), "n": fb["n"]},
            "top_documents": sorted(top_docs.items(), key=lambda x: -x[1])[:10],
            "knowledge_gaps": unanswered,
            "open_tickets": self.q("SELECT COUNT(*) n FROM tickets WHERE status='open'")[0]["n"],
        }


def _r(v, nd=0):
    return None if v is None else round(v, nd) if nd else int(v)
