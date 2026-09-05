from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Database:
    """Local metadata store; MongoDB is optional for existing deployments."""

    def __init__(self, url: str, name: str, work_dir: Path):
        self.client = None
        self.local = None
        if url:
            from pymongo import MongoClient
            self.client = MongoClient(url, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000, socketTimeoutMS=15000)
            self.db = self.client[name]
        else:
            work_dir.mkdir(parents=True, exist_ok=True)
            self.local = sqlite3.connect(work_dir / "metadata.sqlite3")
            self.local.executescript("""
                CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                  filename TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT);
            """)
            self.local.commit()

    async def ping(self):
        if self.client is not None:
            await asyncio.to_thread(self.client.admin.command, "ping")
        else:
            self.local.execute("SELECT 1")

    async def recover(self):
        terminal = ("done", "failed", "cancelled", "interrupted")
        if self.client is not None:
            await asyncio.to_thread(self.db.jobs.update_many, {"status": {"$nin": list(terminal)}}, {"$set": {"status": "interrupted"}})
        else:
            self.local.execute("UPDATE jobs SET status='interrupted' WHERE status NOT IN (?,?,?,?)", terminal)
            self.local.commit()

    async def register_user(self, user_id: int):
        now = datetime.now(timezone.utc).isoformat()
        if self.client is not None:
            await asyncio.to_thread(self.db.users.update_one, {"_id": user_id}, {"$setOnInsert": {"created_at": now}}, upsert=True)
        else:
            self.local.execute("INSERT OR IGNORE INTO users VALUES (?,?)", (user_id, now))
            self.local.commit()

    async def create_job(self, job_id: str, user_id: int, filename: str):
        now = datetime.now(timezone.utc).isoformat()
        if self.client is not None:
            await asyncio.to_thread(self.db.jobs.insert_one, {"_id": job_id, "user_id": user_id, "filename": filename, "status": "queued", "updated_at": now})
        else:
            self.local.execute("INSERT INTO jobs VALUES (?,?,?,?,?,NULL)", (job_id, user_id, filename, "queued", now))
            self.local.commit()

    async def set_job_status(self, job_id: str, status: str, error: str | None = None):
        now = datetime.now(timezone.utc).isoformat()
        if self.client is not None:
            await asyncio.to_thread(self.db.jobs.update_one, {"_id": job_id}, {"$set": {"status": status, "updated_at": now, "error": error}})
        else:
            self.local.execute("UPDATE jobs SET status=?, updated_at=?, error=? WHERE id=?", (status, now, error, job_id))
            self.local.commit()

    async def counts(self) -> tuple[int, int]:
        if self.client is not None:
            return (await asyncio.to_thread(self.db.users.count_documents, {}), await asyncio.to_thread(self.db.jobs.count_documents, {}))
        return self.local.execute("SELECT COUNT(*) FROM users").fetchone()[0], self.local.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    async def close(self):
        if self.client is not None:
            await asyncio.to_thread(self.client.close)
        elif self.local is not None:
            self.local.close()
