from __future__ import annotations

import asyncio
import sqlite3
import time
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
                CREATE TABLE IF NOT EXISTS profiles (id INTEGER PRIMARY KEY, trial_started INTEGER NOT NULL,
                  premium_until INTEGER NOT NULL DEFAULT 0, capacity_mib INTEGER NOT NULL DEFAULT 2000, caption TEXT);
                CREATE TABLE IF NOT EXISTS thumbnails (user_id INTEGER PRIMARY KEY, jpeg BLOB NOT NULL);
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

    async def get_profile(self, user_id: int):
        await self.register_user(user_id)
        now = int(time.time())
        if self.client is not None:
            from pymongo import ReturnDocument
            return await asyncio.to_thread(self.db.profiles.find_one_and_update, {"_id": user_id},
                {"$setOnInsert": {"trial_started": now, "premium_until": 0, "capacity_mib": 2000, "caption": None}},
                upsert=True, return_document=ReturnDocument.AFTER)
        self.local.execute("INSERT OR IGNORE INTO profiles(id,trial_started) VALUES (?,?)", (user_id, now))
        self.local.commit()
        row = self.local.execute("SELECT trial_started,premium_until,capacity_mib,caption FROM profiles WHERE id=?", (user_id,)).fetchone()
        return dict(zip(("trial_started", "premium_until", "capacity_mib", "caption"), row))

    async def update_profile(self, user_id: int, **fields):
        allowed = {"premium_until", "capacity_mib", "caption"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("Unsupported profile update")
        await self.get_profile(user_id)
        if self.client is not None:
            await asyncio.to_thread(self.db.profiles.update_one, {"_id": user_id}, {"$set": fields})
        else:
            assignments = ",".join(key + "=?" for key in fields)
            self.local.execute(f"UPDATE profiles SET {assignments} WHERE id=?", (*fields.values(), user_id))
            self.local.commit()

    async def has_user(self, user_id):
        if self.client is not None:
            return await asyncio.to_thread(self.db.users.find_one, {"_id": user_id}) is not None
        return self.local.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is not None

    async def iter_user_ids(self):
        # Stable upper bound prevents a long broadcast from chasing new registrations.
        if self.client is not None:
            last = await asyncio.to_thread(self.db.users.find_one, {}, sort=[("_id", -1)])
            upper = last["_id"] if last else 0
        else:
            upper = self.local.execute("SELECT COALESCE(MAX(id),0) FROM users").fetchone()[0]
        after = 0
        while after < upper:
            if self.client is not None:
                def page():
                    return [row["_id"] for row in self.db.users.find({"_id": {"$gt": after, "$lte": upper}}, {"_id": 1}).sort("_id", 1).limit(500)]
                ids = await asyncio.to_thread(page)
            else:
                ids = [row[0] for row in self.local.execute("SELECT id FROM users WHERE id>? AND id<=? ORDER BY id LIMIT 500", (after, upper))]
            if not ids:
                break
            for user_id in ids:
                yield user_id
            after = ids[-1]

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

    async def set_thumbnail(self, user_id: int, jpeg: bytes):
        if self.client is not None:
            await asyncio.to_thread(self.db.thumbnails.update_one, {"_id": user_id}, {"$set": {"jpeg": jpeg}}, upsert=True)
        else:
            self.local.execute("INSERT INTO thumbnails VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET jpeg=excluded.jpeg", (user_id, jpeg))
            self.local.commit()

    async def get_thumbnail(self, user_id: int) -> bytes | None:
        if self.client is not None:
            row = await asyncio.to_thread(self.db.thumbnails.find_one, {"_id": user_id})
            return bytes(row["jpeg"]) if row else None
        row = self.local.execute("SELECT jpeg FROM thumbnails WHERE user_id=?", (user_id,)).fetchone()
        return bytes(row[0]) if row else None

    async def delete_thumbnail(self, user_id: int):
        if self.client is not None:
            await asyncio.to_thread(self.db.thumbnails.delete_one, {"_id": user_id})
        else:
            self.local.execute("DELETE FROM thumbnails WHERE user_id=?", (user_id,))
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
