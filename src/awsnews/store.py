"""既読管理。同じ記事を二度流さないための最小限の台帳。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    url          TEXT NOT NULL,
    agent_key    TEXT NOT NULL,
    title        TEXT NOT NULL,
    score        INTEGER,
    notified     INTEGER NOT NULL DEFAULT 0,
    seen_at      TEXT NOT NULL,
    PRIMARY KEY (url, agent_key)
);
CREATE INDEX IF NOT EXISTS idx_seen_agent ON seen (agent_key, seen_at);
"""


class SeenStore:
    """URL × エージェントの単位で処理済みを記録する。

    同じ URL でも担当エージェントが違えば別扱いにする（将来 1 記事を
    複数エージェントが違う観点で扱う余地を残すため）。
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def filter_unseen(self, agent_key: str, urls: list[str]) -> set[str]:
        """まだ処理していない URL の集合を返す。"""
        if not urls:
            return set()
        with self._connect() as conn:
            placeholders = ",".join("?" * len(urls))
            rows = conn.execute(
                f"SELECT url FROM seen WHERE agent_key = ? AND url IN ({placeholders})",
                [agent_key, *urls],
            ).fetchall()
        return set(urls) - {r[0] for r in rows}

    def mark(self, agent_key: str, url: str, title: str, score: int | None,
             notified: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO seen (url, agent_key, title, score, notified, seen_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (url, agent_key, title, score, int(notified),
                 datetime.now(timezone.utc).isoformat()),
            )

    def stats(self) -> list[tuple[str, int, int]]:
        """(エージェント, 処理済み件数, 通知済み件数) の一覧。"""
        with self._connect() as conn:
            return conn.execute(
                "SELECT agent_key, COUNT(*), SUM(notified) FROM seen GROUP BY agent_key"
            ).fetchall()
