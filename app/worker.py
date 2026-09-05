from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import DISK_RESERVE, MAX_FILE_BYTES, Settings, SetupError
from .security import safe_filename

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenameJob:
    user_id: int
    source_chat_id: int
    source_message_id: int
    target_name: str
    file_size: int
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)


async def telegram_call(method, *args, **kwargs):
    from pyrogram.errors import FloodWait
    for attempt in range(3):
        try:
            return await method(*args, **kwargs)
        except FloodWait as exc:
            if attempt == 2 or exc.value > 120:
                raise SetupError("Telegram rate limit reached. Wait a few minutes before trying again.") from None
            await asyncio.sleep(exc.value + 1)


class RenameWorker:
    def __init__(self, bot, premium, db, settings: Settings):
        self.bot, self.premium, self.db, self.settings = bot, premium, db, settings
        self.queue: asyncio.Queue[RenameJob] = asyncio.Queue(maxsize=10)
        self.pending: dict[int, RenameJob] = {}
        self.cancelled: set[str] = set()
        self.runner = None
        self.active = None
        self.active_job = None
        self.stopping = False

    async def start(self):
        self.stopping = False
        self.runner = asyncio.create_task(self._run(), name="rename-queue")

    async def stop(self):
        self.stopping = True
        if self.runner:
            self.runner.cancel()
            await asyncio.gather(self.runner, return_exceptions=True)
        while not self.queue.empty():
            job = self.queue.get_nowait()
            await self._record(job, "interrupted")
            self.pending.pop(job.user_id, None)
            self.queue.task_done()

    async def submit(self, job: RenameJob):
        if self.stopping:
            raise SetupError("The bot is stopping. Try again after it restarts.")
        safe_filename(job.target_name)
        if not 0 < job.file_size <= MAX_FILE_BYTES:
            raise SetupError("File must be non-empty and at most 4000 MiB (Telegram Premium's 4GB tier).")
        if job.user_id in self.pending:
            raise SetupError("You already have a job. Use /status or /cancel before sending another.")
        if self.queue.full():
            raise SetupError("Queue is full. Try again after a job finishes.")
        self.pending[job.user_id] = job
        try:
            await self.db.create_job(job.job_id, job.user_id, job.target_name)
            self.queue.put_nowait(job)
        except BaseException:
            self.pending.pop(job.user_id, None)
            raise

    async def cancel(self, user_id: int) -> bool:
        job = self.pending.get(user_id)
        if not job:
            return False
        self.cancelled.add(job.job_id)
        if self.active_job == job and self.active:
            self.active.cancel()
        return True

    async def _record(self, job, status, error=None):
        try:
            await self.db.set_job_status(job.job_id, status, error)
        except Exception as exc:
            log.warning("Metadata write failed (%s), job %s", type(exc).__name__, job.job_id)

    async def _notify(self, chat_id, text):
        try:
            return await self.bot.send_message(chat_id, text)
        except Exception as exc:
            log.warning("Notification failed (%s)", type(exc).__name__)

    async def _run(self):
        while True:
            job = await self.queue.get()
            self.active_job = job
            try:
                if job.job_id in self.cancelled:
                    await self._record(job, "cancelled")
                else:
                    self.active = asyncio.create_task(self._process(job))
                    await self.active
            except asyncio.CancelledError:
                await self._record(job, "interrupted" if self.stopping else "cancelled")
                if self.stopping:
                    raise
            except Exception as exc:
                # A failed DB or notification must not kill the only queue consumer.
                log.error("Queue task failed (%s), job %s", type(exc).__name__, job.job_id)
            finally:
                self.pending.pop(job.user_id, None)
                self.cancelled.discard(job.job_id)
                self.active = self.active_job = None
                self.queue.task_done()

    async def _process(self, job):
        staging_ids = []
        status = None
        last_update = 0.0
        phase = "Downloading"

        async def progress(current, total):
            nonlocal last_update
            if not status or time.monotonic() - last_update < 5:
                return
            last_update = time.monotonic()
            try:
                await self.bot.edit_message_text(job.user_id, status.id, f"{phase}: {current * 100 // max(total, 1)}% | {job.job_id[:8]}")
            except Exception:
                pass

        jobs_dir = self.settings.work_dir / "jobs"
        try:
            status = await self._notify(job.user_id, f"KBC REBOT: starting job {job.job_id[:8]}.")
            jobs_dir.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(jobs_dir).free < job.file_size + DISK_RESERVE:
                raise SetupError("Not enough disk space on the bot laptop. Free space and try again.")
            async with asyncio.timeout(6 * 60 * 60):
                with tempfile.TemporaryDirectory(prefix="job-", dir=jobs_dir) as directory:
                    await self._record(job, "staging")
                    staged = await telegram_call(self.bot.copy_message, self.settings.staging_chat_id,
                                                job.source_chat_id, job.source_message_id)
                    staging_ids.append(staged.id)
                    # File references belong to the account that retrieved them.
                    source = await telegram_call(self.premium.get_messages, self.settings.staging_chat_id, staged.id)
                    await self._record(job, "downloading")
                    destination = Path(directory) / "source.bin"
                    downloaded = await telegram_call(self.premium.download_media, source,
                                                    file_name=str(destination), progress=progress)
                    if not downloaded or not destination.is_file() or destination.stat().st_size != job.file_size:
                        raise SetupError("Download was incomplete. Send the file again and retry.")
                    renamed = destination.with_name(job.target_name)
                    if renamed != destination:
                        destination.replace(renamed)
                    phase = "Uploading"
                    last_update = 0.0
                    await self._record(job, "uploading")
                    uploaded = await telegram_call(self.premium.send_document, self.settings.staging_chat_id,
                                                  str(renamed), file_name=job.target_name,
                                                  caption="KBC REBOT", force_document=True, progress=progress)
                    if not uploaded:
                        raise SetupError("Upload did not finish. Try again when the connection is stable.")
                    staging_ids.append(uploaded.id)
                    await telegram_call(self.bot.copy_message, job.user_id, self.settings.staging_chat_id,
                                        uploaded.id, caption=job.target_name)
                    await self._record(job, "done")
                    await self._notify(job.user_id, "Renaming completed.")
        except asyncio.CancelledError:
            await self._record(job, "interrupted" if self.stopping else "cancelled")
            await self._notify(job.user_id, "Job stopped. Send /rename again when you are ready.")
            raise
        except Exception as exc:
            # Only an error class is stored or logged; never raw SDK/DB exceptions.
            await self._record(job, "failed", type(exc).__name__)
            detail = str(exc) if isinstance(exc, SetupError) else f"Transfer failed ({type(exc).__name__}). Try again or contact the admin."
            await self._notify(job.user_id, detail)
            log.warning("Transfer failed (%s), job %s", type(exc).__name__, job.job_id)
            if self.settings.log_channel_id:
                await self._notify(self.settings.log_channel_id, f"Job {job.job_id[:8]} failed: {type(exc).__name__}")
        finally:
            if staging_ids:
                try:
                    async with asyncio.timeout(20):
                        await self.bot.delete_messages(self.settings.staging_chat_id, staging_ids)
                except Exception as exc:
                    log.warning("Staging cleanup failed (%s), job %s; admin should check the private staging channel.", type(exc).__name__, job.job_id)
