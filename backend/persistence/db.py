# -*- coding: utf-8 -*-
"""基于 SQLite 的持久化层（stdlib sqlite3，零外部依赖）。

将传输请求与统计快照落盘，使数据在重启后可保留。请求以 id 为主键 upsert，避免重复行。
"""
import json
import sqlite3
import threading
import time


class SqliteRepository:
    def __init__(self, path=":memory:"):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS requests (
                       id TEXT PRIMARY KEY,
                       data_type TEXT,
                       status TEXT,
                       source TEXT,
                       priority INTEGER,
                       submit_time REAL,
                       complete_time REAL,
                       payload TEXT
                   )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS stats_snapshots (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       ts REAL,
                       payload TEXT
                   )"""
            )

    def save_request(self, req: dict):
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO requests (id, data_type, status, source, priority, submit_time, complete_time, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       status=excluded.status, complete_time=excluded.complete_time, payload=excluded.payload""",
                (
                    req.get("id"), req.get("data_type"), req.get("status"), req.get("source"),
                    req.get("priority"), req.get("submit_time"), req.get("complete_time"),
                    json.dumps(req, ensure_ascii=False),
                ),
            )

    def load_requests(self):
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM requests ORDER BY submit_time").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def count_requests(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) AS c FROM requests").fetchone()["c"]

    def save_stats_snapshot(self, stats: dict):
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO stats_snapshots (ts, payload) VALUES (?, ?)",
                (time.time(), json.dumps(stats, ensure_ascii=False)),
            )

    def load_latest_stats(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM stats_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def close(self):
        self._conn.close()
