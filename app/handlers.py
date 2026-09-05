from __future__ import annotations

from pathlib import PurePosixPath

from .config import SetupError
from .security import is_subscribed, safe_filename
from .worker import RenameJob


def register_handlers(bot, db, worker, settings):
    from pyrogram import filters

    @bot.on_message(filters.private & filters.command(["start", "help"]))
    async def start_handler(_, message):
        text = ("KBC REBOT — 4GB file renamer\n\n"
                "Send a document/video/audio, then reply to it with:\n/rename New File Name.ext\n\n"
                "/status — queue\n/cancel — stop your job\n"
                "One job per user. Maximum 4000 MiB. Files pass through the operator's laptop and private staging channel.")
        if settings.start_pic:
            try:
                await message.reply_photo(settings.start_pic, caption=text)
                return
            except Exception:
                pass
        await message.reply_text(text)

    @bot.on_message(filters.private & filters.command("rename"))
    async def rename_handler(client, message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        try:
            if not await is_subscribed(client, settings.force_sub_channel, user_id):
                await message.reply_text(f"Join {settings.force_sub_channel}, then try /rename again.")
                return
            replied = message.reply_to_message
            media = (replied.document or replied.video or replied.audio) if replied else None
            parts = (message.text or "").split(maxsplit=1)
            if not media or len(parts) != 2:
                await message.reply_text("Reply to a document, video or audio with /rename New Name.ext")
                return
            suffix = PurePosixPath(media.file_name or "").suffix
            name = safe_filename(parts[1], suffix)
            await db.register_user(user_id)
            await worker.submit(RenameJob(user_id, message.chat.id, replied.id, name, media.file_size or 0))
        except ValueError as exc:
            await message.reply_text(str(exc) if isinstance(exc, SetupError) else "Invalid filename. Avoid Windows reserved names/symbols and keep the name short.")
            return
        except Exception:
            await message.reply_text("Unable to queue this file. The admin should run CHECK.cmd on the bot laptop.")
            return
        await message.reply_text("Added to the rename queue. Use /cancel to stop your job.")

    @bot.on_message(filters.private & filters.command("status"))
    async def status_handler(_, message):
        job = worker.pending.get(message.from_user.id) if message.from_user else None
        own = f"Your job: {job.job_id[:8]}" if job else "You have no queued or active job."
        await message.reply_text(f"{own}\nWaiting: {worker.queue.qsize()}\nActive: {int(worker.active_job is not None)}")

    @bot.on_message(filters.private & filters.command("cancel"))
    async def cancel_handler(_, message):
        cancelled = await worker.cancel(message.from_user.id) if message.from_user else False
        await message.reply_text("Cancellation requested." if cancelled else "You have no job to cancel.")

    @bot.on_message(filters.private & filters.command("admin") & filters.user(settings.admin_id))
    async def admin_handler(_, message):
        try:
            users, jobs = await db.counts()
            await message.reply_text(f"Users: {users}\nJobs recorded: {jobs}\nWaiting: {worker.queue.qsize()}")
        except Exception:
            await message.reply_text("Database unavailable. Run CHECK.cmd after stopping the bot.")
