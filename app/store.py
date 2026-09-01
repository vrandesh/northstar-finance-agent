"""
Note: AI Assist used to generate and store structured data related to AI model runs and events. (Only to Save Time)
"""

import json
import re
import sqlite3
import threading

from .schemas import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, case_id TEXT, status TEXT, version INTEGER DEFAULT 1,
  result TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts TEXT, node TEXT,
  event TEXT, outcome TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, result TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS approvals (
  run_id TEXT PRIMARY KEY, request TEXT, status TEXT, decision TEXT, updated_at TEXT);
"""
_LONG_NUMBER = re.compile(r"\b(\d{8,})\b")

def mask(value):
    if isinstance(value, str):
        return _LONG_NUMBER.sub(lambda m: "****" + m.group(1)[-4:], value)
    if isinstance(value, dict):
        return {k: mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value

class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()
            
    def save_run(self, run_id, case_id, status, result=None, bump=True) -> int:
        with self._lock:
            row = self._db.execute("SELECT version FROM runs WHERE run_id=?", (run_id,)).fetchone()
            payload = json.dumps(result, default=str) if result is not None else None
            if row:
                version = row["version"] + (1 if bump else 0)
                self._db.execute("UPDATE runs SET status=?, version=?, result=COALESCE(?,result), "
                                 "updated_at=? WHERE run_id=?",
                                 (status, version, payload, now_iso(), run_id))
            else:
                version = 1
                self._db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                                 (run_id, case_id, status, version, payload, now_iso(), now_iso()))
            self._db.commit()
            return version
    
    def save_run(self, run_id, case_id, status, result=None, bump=True) -> int:
        with self._lock:
            row = self._db.execute("SELECT version FROM runs WHERE run_id=?", (run_id,)).fetchone()
            payload = json.dumps(result, default=str) if result is not None else None
            if row:
                version = row["version"] + (1 if bump else 0)
                self._db.execute("UPDATE runs SET status=?, version=?, result=COALESCE(?,result), "
                                 "updated_at=? WHERE run_id=?",
                                 (status, version, payload, now_iso(), run_id))
            else:
                version = 1
                self._db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                                 (run_id, case_id, status, version, payload, now_iso(), now_iso()))
            self._db.commit()
            return version
    
    def log(self, run_id, node, event, outcome="", detail=None):
        with self._lock:
            self._db.execute("INSERT INTO events(run_id,ts,node,event,outcome,detail) VALUES(?,?,?,?,?,?)",
                             (run_id, now_iso(), node, event, outcome,
                              json.dumps(mask(detail or {}), default=str)))
            self._db.commit()
    
    def events(self, run_id):
        with self._lock:
            rows = self._db.execute("SELECT ts,node,event,outcome,detail FROM events "
                                    "WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [{"ts": r["ts"], "node": r["node"], "event": r["event"], "outcome": r["outcome"],
                 "detail": json.loads(r["detail"])} for r in rows]
    
    def remember(self, key, result):
        """Store result under a unique key. If the key exists, return the first
        result and False (do not repeat the effect)."""
        with self._lock:
            row = self._db.execute("SELECT result FROM idempotency WHERE key=?", (key,)).fetchone()
            if row:
                return False, json.loads(row["result"])
            self._db.execute("INSERT INTO idempotency VALUES(?,?,?)",
                             (key, json.dumps(result, default=str), now_iso()))
            self._db.commit()
            return True, result
    
    def set_approval(self, run_id, request=None, status="pending", decision=None):
        with self._lock:
            row = self._db.execute("SELECT run_id FROM approvals WHERE run_id=?", (run_id,)).fetchone()
            if row:
                self._db.execute("UPDATE approvals SET status=?, decision=COALESCE(?,decision), "
                                 "updated_at=? WHERE run_id=?",
                                 (status, json.dumps(decision, default=str) if decision else None,
                                  now_iso(), run_id))
            else:
                self._db.execute("INSERT INTO approvals VALUES(?,?,?,?,?)",
                                 (run_id, json.dumps(mask(request or {}), default=str), status,
                                  json.dumps(decision, default=str) if decision else None, now_iso()))
            self._db.commit()
    
    def get_approval(self, run_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM approvals WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {"run_id": row["run_id"],
                "request": json.loads(row["request"]) if row["request"] else None,
                "status": row["status"],
                "decision": json.loads(row["decision"]) if row["decision"] else None}
    
    