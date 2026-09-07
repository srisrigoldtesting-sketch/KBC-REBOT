"""Publish status separately so Telegram edits cannot stall file transfers."""
import asyncio
import time


class TransferProgress:
    def __init__(self, bot, chat_id, message_id, job_id, interval=5):
        self.bot, self.chat_id, self.message_id = bot, chat_id, message_id
        self.job_id, self.interval = job_id, interval
        self.task = None
        self.begin("Preparing")

    def begin(self, phase):
        self.phase = phase
        self.started = time.monotonic()
        self.current = self.total = 0

    async def update(self, current, total):
        # Pyrofork awaits this callback inside its transfer loop: no RPCs here.
        self.current, self.total = current, total

    def text(self):
        elapsed = max(time.monotonic() - self.started, 0.001)
        speed = self.current / elapsed
        eta = f"{max(0, int((self.total - self.current) / speed))}s" if speed else "estimating"
        return (f"{self.phase}: {self.current * 100 // max(self.total, 1)}%\n"
                f"{self.current / 1024**2:.1f} / {self.total / 1024**2:.1f} MiB\n"
                f"{speed / 1024**2:.2f} MiB/s | ETA: {eta}\nJob: {self.job_id[:8]}")

    def start(self):
        if self.message_id is not None:
            self.task = asyncio.create_task(self._publish(), name="transfer-progress")

    async def _publish(self):
        from pyrogram.errors import FloodWait
        delay = self.interval
        while True:
            await asyncio.sleep(delay)
            delay = self.interval
            if not self.total:
                continue
            try:
                async with asyncio.timeout(10):
                    await self.bot.edit_message_text(self.chat_id, self.message_id, self.text())
            except FloodWait as exc:
                delay = max(self.interval, exc.value + 1)
            except Exception:
                pass

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
