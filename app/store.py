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
