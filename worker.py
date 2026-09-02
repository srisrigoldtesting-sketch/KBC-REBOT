from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from pyrogram import Client

from .config import Settings
from .database import Database


@dataclass(frozen=True)
class RenameJob:
    user_id: int
    source_chat_id: int
    source_message_id: int
    target_name: str


class RenameWorker:
    def __init__(self, bot: Client, premium: Client, db: Database, settings: Settings):
        self.bot = bot
        self.premium = premium
        self.db = db
        self.settings = settings
        self.queue: asyncio.Queue[RenameJob] = asyncio.Queue(maxsize=100)
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.tasks = [asyncio.create_task(self._run()) for _ in range(self.settings.max_concurrent_jobs)]

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def submit(self, job: RenameJob) -> None:
        await self.queue.put(job)

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            job_id = uuid.uuid4().hex
            path: Path | None = None
            try:
                await self.db.create_job(job_id, job.user_id, job.target_name)
                await self.db.set_job_status(job_id, "staging")
                staged = await self.bot.copy_message(
                    self.settings.staging_chat_id,
                    job.source_chat_id,
                    job.source_message_id,
                )
                await self.db.set_job_status(job_id, "downloading")
                downloaded = await self.premium.download_media(
                    staged,
                    file_name=str(self.settings.work_dir / f"{job_id}_"),
                )
                if not downloaded:
                    raise RuntimeError("Premium client did not download the staged file")
                path = Path(downloaded)
                renamed = path.with_name(job.target_name)
                path.replace(renamed)
                path = renamed
                await self.db.set_job_status(job_id, "uploading")
                uploaded = await self.premium.send_document(
                    self.settings.staging_chat_id,
                    str(path),
                    file_name=job.target_name,
                    caption=f"job:{job_id}",
                )
                await self.bot.copy_message(job.user_id, self.settings.staging_chat_id, uploaded.id)
                await self.db.set_job_status(job_id, "done")
                await self.bot.send_message(job.user_id, "✅ Renaming completed.")
            except Exception as exc:
                await self.db.set_job_status(job_id, "failed", str(exc))
                await self.bot.send_message(job.user_id, "❌ Rename failed. Please try again or contact the admin.")
                if self.settings.log_channel_id:
                    await self.bot.send_message(self.settings.log_channel_id, f"Job {job_id} failed: {type(exc).__name__}: {str(exc)[:300]}")
            finally:
                if path:
                    path.unlink(missing_ok=True)
                self.queue.task_done()

