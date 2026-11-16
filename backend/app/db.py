"""Tiny data layer with two interchangeable backends.

* SupabaseDB — PostgREST over HTTPS (production, shared by Render + GitHub worker)
* LocalDB    — SQLite JSON documents (laptop / demo, zero setup)

Only the handful of operations the app needs are implemented, with identical
semantics on both backends.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from . import config

TABLES = ("episodes", "events", "settings", "topics", "trends", "characters", "feedback")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class BaseDB:
    kind = "base"

    def insert(self, table: str, row: dict) -> dict: ...
    def update(self, table: str, id: str, patch: dict) -> dict: ...
    def get(self, table: str, id: str) -> dict | None: ...
    def delete(self, table: str, id: str) -> None: ...
    def query(self, table: str, eq: dict | None = None, in_: dict | None = None,
              lte: dict | None = None, gte: dict | None = None,
              order: str = "created_at", desc: bool = True, limit: int = 200) -> list[dict]: ...

    def claim(self, table: str, id: str, from_status: list[str], patch: dict) -> dict | None:
        """Atomically move a row out of one of `from_status`. None if someone else got it."""
        ...

    # settings are rows {id: key, value: any}
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.get("settings", key)
        return default if row is None else row.get("value", default)

    def set_setting(self, key: str, value: Any) -> None:
        if self.get("settings", key) is None:
            self.insert("settings", {"id": key, "value": value})
        else:
            self.update("settings", key, {"value": value})

    def prune(self) -> None:
        """Keep the database small: activity events older than 30 days are dropped."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        for t in self.query("events", lte={"created_at": (now - timedelta(days=30)).isoformat(timespec="seconds")}, limit=1000):
            self.delete("events", t["id"])

    def log(self, msg: str, level: str = "info", episode_id: str | None = None) -> None:
        try:
            self.insert("events", {"level": level, "msg": msg[:2000], "episode_id": episode_id})
        except Exception:  # logging must never break the pipeline
            pass
        print(f"[{level}] {episode_id or '-'} {msg}", flush=True)


class LocalDB(BaseDB):
    kind = "sqlite"

    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        for t in TABLES:
            self.conn.execute(
                f"CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, created_at TEXT, doc TEXT)")
        self.conn.commit()

    def _row(self, doc: str) -> dict:
        return json.loads(doc)

    def insert(self, table, row):
        row = dict(row)
        row.setdefault("id", new_id())
        row.setdefault("created_at", now_iso())
        if table != "settings":
            row.setdefault("updated_at", row["created_at"])
        with self._lock:
            self.conn.execute(f"INSERT INTO {table} (id, created_at, doc) VALUES (?,?,?)",
                              (row["id"], row["created_at"], json.dumps(row)))
            self.conn.commit()
        return row

    def get(self, table, id):
        with self._lock:
            cur = self.conn.execute(f"SELECT doc FROM {table} WHERE id=?", (id,))
            r = cur.fetchone()
        return self._row(r[0]) if r else None

    def update(self, table, id, patch):
        with self._lock:
            cur = self.conn.execute(f"SELECT doc FROM {table} WHERE id=?", (id,))
            r = cur.fetchone()
            if not r:
                raise KeyError(f"{table}/{id} not found")
            row = self._row(r[0])
            row.update(patch)
            if table != "settings":
                row["updated_at"] = now_iso()
            self.conn.execute(f"UPDATE {table} SET doc=? WHERE id=?", (json.dumps(row), id))
            self.conn.commit()
        return row

    def delete(self, table, id):
        with self._lock:
            self.conn.execute(f"DELETE FROM {table} WHERE id=?", (id,))
            self.conn.commit()

    def claim(self, table, id, from_status, patch):
        with self._lock:
            r = self.conn.execute(f"SELECT doc FROM {table} WHERE id=?", (id,)).fetchone()
            if not r:
                return None
            row = self._row(r[0])
            if row.get("status") not in from_status:
                return None
            row.update(patch)
            row["updated_at"] = now_iso()
            self.conn.execute(f"UPDATE {table} SET doc=? WHERE id=?", (json.dumps(row), id))
            self.conn.commit()
            return row

    def query(self, table, eq=None, in_=None, lte=None, gte=None,
              order="created_at", desc=True, limit=200):
        with self._lock:
            rows = [self._row(r[0]) for r in self.conn.execute(f"SELECT doc FROM {table}")]
        def ok(r):
            for k, v in (eq or {}).items():
                if r.get(k) != v:
                    return False
            for k, vs in (in_ or {}).items():
                if r.get(k) not in vs:
                    return False
            for k, v in (lte or {}).items():
                if r.get(k) is None or str(r.get(k)) > str(v):
                    return False
            for k, v in (gte or {}).items():
                if r.get(k) is None or str(r.get(k)) < str(v):
                    return False
            return True
        rows = [r for r in rows if ok(r)]
        rows.sort(key=lambda r: (r.get(order) is None, str(r.get(order) or "")), reverse=desc)
        return rows[:limit]


# Real columns of each Supabase table (docs/supabase.sql; tests/test_supabase_db.py keeps them in sync).
# Any other field is stored in the table's `extra` jsonb column and merged back on read, so new fields
# never need a schema migration.
COLUMNS: dict[str, frozenset[str]] = {
    "episodes": frozenset(('id', 'created_at', 'updated_at', 'kind', 'status', 'category', 'topic', 'age_band', 'language', 'minutes', 'duration', 'variant', 'why', 'angle', 'source', 'editions', 'progress', 'error', 'script', 'critic', 'safety', 'meta', 'video_url', 'thumb_url', 'timeline', 'song_regions', 'qa', 'engines', 'rendered_at', 'publish_at', 'published_at', 'youtube', 'stats', 'parent_id', 'edition_of', 'art_style', 'animation', 'ai_budget_usd', 'ai_video', 'rendered_style')),
    "events": frozenset(('id', 'created_at', 'updated_at', 'level', 'msg', 'episode_id')),
    "settings": frozenset(('id', 'created_at', 'updated_at', 'value')),
    "topics": frozenset(('id', 'created_at', 'updated_at', 'topic', 'category', 'episode_id')),
    "trends": frozenset(('id', 'created_at', 'updated_at', 'topic', 'category', 'age_band', 'score', 'used', 'why', 'angle', 'episode_id')),
    "characters": frozenset(('id', 'created_at', 'updated_at', 'tier', 'name', 'kind', 'species', 'gender', 'age', 'colors', 'outfit', 'skin', 'hair', 'hair_color', 'personality', 'look', 'catchphrase', 'voice', 'pitch', 'origin', 'episodes')),
    "feedback": frozenset(('id', 'created_at', 'updated_at', 'episode_id', 'enjoyed', 'style', 'animation', 'voices', 'learning', 'change', 'request', 'age_band', 'role')),
}


def _split(table: str, row: dict) -> tuple[dict, dict]:
    cols = COLUMNS.get(table)
    if cols is None:
        return dict(row), {}
    return {k: v for k, v in row.items() if k in cols}, {k: v for k, v in row.items() if k not in cols}


def _flatten(row: dict) -> dict:
    row = dict(row)
    extra = row.pop("extra", None) or {}
    return {**extra, **row} if isinstance(extra, dict) else row


class SupabaseDB(BaseDB):
    kind = "supabase"

    def __init__(self, url: str, key: str):
        self.base = f"{url}/rest/v1"
        self.client = httpx.Client(timeout=30, headers={
            **config.supabase_headers(key),
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        })

    def _check(self, r: httpx.Response):
        if r.status_code >= 400:
            if "PGRST205" in r.text or "PGRST204" in r.text:
                raise RuntimeError("Supabase is missing CartoonForge's tables or columns: open Supabase → SQL Editor, "
                                   "paste docs/supabase.sql from the repo and click Run (safe to run again). "
                                   f"Details: {r.text[:200]}")
            raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else []

    def _rows(self, r: httpx.Response) -> list[dict]:
        return [_flatten(x) for x in self._check(r)]

    def _body(self, table: str, row: dict, old_extra: dict | None = None) -> dict:
        cols, extra = _split(table, row)
        if table in COLUMNS and (extra or old_extra):
            cols["extra"] = {**(old_extra or {}), **extra}
        return cols

    def insert(self, table, row):
        row = dict(row)
        row.setdefault("id", new_id())
        out = self._rows(self.client.post(f"{self.base}/{table}", json=self._body(table, row)))
        return out[0] if out else row

    def get(self, table, id):
        out = self._rows(self.client.get(f"{self.base}/{table}", params={"id": f"eq.{id}"}))
        return out[0] if out else None

    def update(self, table, id, patch):
        patch = dict(patch)
        if table in ("episodes", "topics"):
            patch["updated_at"] = now_iso()
        old_extra = None
        if _split(table, patch)[1]:                          # extra fields: merge with what is stored
            cur = self._check(self.client.get(f"{self.base}/{table}", params={"id": f"eq.{id}", "select": "extra"}))
            if not cur:
                raise KeyError(f"{table}/{id} not found")
            old_extra = cur[0].get("extra") or {}
        out = self._rows(self.client.patch(f"{self.base}/{table}", params={"id": f"eq.{id}"},
                                           json=self._body(table, patch, old_extra)))
        if not out:
            raise KeyError(f"{table}/{id} not found")
        return out[0]

    def delete(self, table, id):
        self._check(self.client.delete(f"{self.base}/{table}", params={"id": f"eq.{id}"}))

    def claim(self, table, id, from_status, patch):
        patch = {**patch, "updated_at": now_iso()}
        params = {"id": f"eq.{id}", "status": "in.(" + ",".join(from_status) + ")"}
        old_extra = None
        if _split(table, patch)[1]:
            cur = self._check(self.client.get(f"{self.base}/{table}", params={"id": f"eq.{id}", "select": "extra"}))
            old_extra = (cur[0].get("extra") or {}) if cur else {}
        out = self._rows(self.client.patch(f"{self.base}/{table}", params=params,
                                           json=self._body(table, patch, old_extra)))
        return out[0] if out else None

    def query(self, table, eq=None, in_=None, lte=None, gte=None,
              order="created_at", desc=True, limit=200):
        params: list[tuple[str, str]] = []
        for k, v in (eq or {}).items():
            params.append((k, f"eq.{str(v).lower() if isinstance(v, bool) else v}"))
        for k, vs in (in_ or {}).items():
            params.append((k, "in.(" + ",".join(f'"{x}"' for x in vs) + ")"))
        for k, v in (lte or {}).items():
            params.append((k, f"lte.{v}"))
        for k, v in (gte or {}).items():
            params.append((k, f"gte.{v}"))
        params.append(("order", f"{order}.{'desc' if desc else 'asc'}.nullslast"))
        params.append(("limit", str(limit)))
        return self._rows(self.client.get(f"{self.base}/{table}", params=params))


_db: BaseDB | None = None


def get_db() -> BaseDB:
    global _db
    if _db is None:
        if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
            _db = SupabaseDB(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        else:
            path = config.DATA_DIR / "cartoonforge.db"
            legacy = config.DATA_DIR / "kidsmith.db"  # name used before the CartoonForge rename
            if not path.exists() and legacy.exists():
                legacy.rename(path)
            _db = LocalDB(str(path))
    return _db
