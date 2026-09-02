from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


class Database:
    def __init__(self, url: str, name: str):
        self.client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=8000)
        self.db = self.client[name]

    async def ping(self) -> None:
        await self.client.admin.command("ping")

    async def register_user(self, user_id: int) -> None:
        await self.db.users.update_one(
            {"_id": user_id},
            {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def create_job(self, job_id: str, user_id: int, filename: str) -> None:
        await self.db.jobs.insert_one({
            "_id": job_id,
            "user_id": user_id,
            "filename": filename,
            "status": "queued",
            "created_at": datetime.now(timezone.utc),
        })

    async def set_job_status(self, job_id: str, status: str, error: str | None = None) -> None:
        update = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if error:
            update["error"] = error[:500]
        await self.db.jobs.update_one({"_id": job_id}, {"$set": update})

    async def close(self) -> None:
        self.client.close()

