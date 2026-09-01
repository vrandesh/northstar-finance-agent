"""
AI Assist used to generate and store structured data related to AI model runs and events. (Only to Save Time)
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

class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()
            
    def save_run(self, run_id, case_id, result=None):
        pass
    
    def get_run(self, run_id):
        pass
    
    def log(self):
        pass
    
    def events(self, run_id):
        pass
    
    def remember(self, key, result=None):
        pass
    
    def set_approval(self):
        pass
    
    def get_approval(self):
        pass
    
    