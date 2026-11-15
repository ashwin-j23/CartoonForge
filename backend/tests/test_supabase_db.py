"""Supabase adapter: fields without a column go to `extra` and come back flat; schema and code agree."""
import json
import re
from pathlib import Path

import httpx
import pytest

from app import db as dbmod

SQL = Path(__file__).resolve().parents[2] / "docs" / "supabase.sql"


def test_columns_match_supabase_sql():
    sql = SQL.read_text()
    found = {}
    for m in re.finditer(r"create table if not exists (\w+) \((.*?)\n\);", sql, re.S):
        found[m.group(1)] = {l.strip().split()[0] for l in m.group(2).split("\n")
                             if l.strip() and not l.strip().startswith("--")}
    assert set(found) == set(dbmod.TABLES) == set(dbmod.COLUMNS)
    for t, cols in found.items():
        assert cols == set(dbmod.COLUMNS[t]), t
        assert f"alter table {t} add column if not exists extra jsonb" in sql


class FakePostgrest:
    """Tiny PostgREST: real column checks (PGRST204), missing tables (PGRST205), eq/in/order/limit/select."""

    def __init__(self, tables=None):
        self.rows = {t: {} for t in (tables if tables is not None else dbmod.TABLES)}

    def _err(self, code, msg, status=400):
        return httpx.Response(status, json={"code": code, "message": msg})

    def __call__(self, req: httpx.Request) -> httpx.Response:
        table = req.url.path.rsplit("/", 1)[-1]
        if table not in self.rows:
            return self._err("PGRST205", f"Could not find the table 'public.{table}' in the schema cache", 404)
        allowed = set(dbmod.COLUMNS[table]) | {"extra"}
        params = list(req.url.params.multi_items())
        filt = [(k, v) for k, v in params if k not in ("order", "limit", "select")]

        def match(row):
            for k, v in filt:
                op, _, val = v.partition(".")
                if op == "eq" and str(row.get(k)) != val:
                    return False
                if op == "in" and str(row.get(k)) not in val.strip("()").replace('"', "").split(","):
                    return False
            return True

        if req.method in ("POST", "PATCH"):
            body = json.loads(req.content)
            bad = set(body) - allowed
            if bad:
                return self._err("PGRST204", f"Could not find the '{sorted(bad)[0]}' column of '{table}'")
        if req.method == "POST":
            self.rows[table][body["id"]] = dict(body)
            return httpx.Response(201, json=[body])
        hits = [r for r in self.rows[table].values() if match(r)]
        if req.method == "PATCH":
            for r in hits:
                r.update(body)
            return httpx.Response(200, json=hits)
        if req.method == "DELETE":
            for r in hits:
                self.rows[table].pop(r["id"])
            return httpx.Response(204)
        sel = dict(params).get("select")
        out = [{k: r.get(k) for k in sel.split(",")} if sel else r for r in hits]
        return httpx.Response(200, json=out[: int(dict(params).get("limit", 1000))])


def _db(fake):
    d = dbmod.SupabaseDB("https://example.supabase.co", "test-key")
    d.client = httpx.Client(transport=httpx.MockTransport(fake), headers=d.client.headers)
    return d


def test_extra_fields_round_trip_and_merge():
    fake = FakePostgrest()
    d = _db(fake)
    ep = d.insert("episodes", {"id": "e1", "status": "planned", "topic": "Bees", "palette": "sunny", "retries": 0})
    assert ep["palette"] == "sunny" and "extra" not in ep
    stored = fake.rows["episodes"]["e1"]
    assert stored["extra"] == {"palette": "sunny", "retries": 0} and "palette" not in stored

    d.update("episodes", "e1", {"retries": 1, "auto_hold": ["demo"], "status": "review"})
    got = d.get("episodes", "e1")
    assert got["palette"] == "sunny" and got["retries"] == 1 and got["auto_hold"] == ["demo"]
    assert got["status"] == "review" and got["topic"] == "Bees"

    assert d.claim("episodes", "e1", ["review"], {"status": "approved", "rendered_palette": "sunny"})
    got = d.query("episodes", eq={"status": "approved"})[0]
    assert got["palette"] == "sunny" and got["rendered_palette"] == "sunny" and got["retries"] == 1

    d.set_setting("app", {"full_auto": True})
    assert d.get_setting("app") == {"full_auto": True}


def test_missing_tables_say_what_to_do():
    d = _db(FakePostgrest(tables=[]))
    with pytest.raises(RuntimeError, match="docs/supabase.sql"):
        d.get_setting("app")
