from __future__ import annotations
import os
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "stats.sqlite3"
META_PATH = DATA_DIR / "meta.json"

def _conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL;")
    return c

def init_db():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            filename TEXT PRIMARY KEY,
            count INTEGER NOT NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS uniques (
            day TEXT NOT NULL,
            visitor_hash TEXT NOT NULL,
            PRIMARY KEY(day, visitor_hash)
        )
        """)
        con.execute("INSERT OR IGNORE INTO counters(key,value) VALUES ('pageviews',0)")
        con.execute("INSERT OR IGNORE INTO counters(key,value) VALUES ('downloads_total',0)")

def inc_counter(key: str, delta: int = 1):
    with _conn() as con:
        con.execute("UPDATE counters SET value = value + ? WHERE key = ?", (delta, key))

def inc_download(filename: str, delta: int = 1):
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO downloads(filename,count) VALUES (?,0)", (filename,))
        con.execute("UPDATE downloads SET count = count + ? WHERE filename = ?", (delta, filename))
        con.execute("UPDATE counters SET value = value + ? WHERE key = 'downloads_total'", (delta,))

def get_stats() -> Dict[str, Any]:
    with _conn() as con:
        counters = dict(con.execute("SELECT key,value FROM counters").fetchall())
        downloads = dict(con.execute("SELECT filename,count FROM downloads").fetchall())
        uniques_today = con.execute(
            "SELECT COUNT(*) FROM uniques WHERE day = ?",
            (datetime.now().strftime("%Y-%m-%d"),)
        ).fetchone()[0]
    return {
        "counters": counters,
        "downloads": downloads,
        "uniques_today": uniques_today,
    }

def mark_unique(visitor_id: str):
    """
    visitor_id: string (bv. ip + user-agent). We hash it, store hash only.
    """
    day = datetime.now().strftime("%Y-%m-%d")
    h = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:32]
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO uniques(day, visitor_hash) VALUES (?,?)", (day, h))
