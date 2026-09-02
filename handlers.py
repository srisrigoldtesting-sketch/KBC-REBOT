from __future__ import annotations

from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

from .config import Settings
from .database import Database
from .security import is_subscribed, safe_filename
from .worker import RenameJob, RenameWorker


def register_handlers(bot: Client, db: Database, worker: RenameWorker, settings: Settings) -> None:
    @bot.on_message(filters.private & filters.command("start"))
    async def start_handler(_: Client, message: Message) -> None:
        await db.register_user(message.from_user.id)
        text = (
            "🤖 <b>KBC REBOT — Premium 4GB File Renamer</b>\n\n"
            "Send a document, then reply to it with:\n"
            "<code>/rename New File Name.ext</code>\n\n"
            "Files are processed through a private staging channel and deleted from local disk after upload."
        )
        if settings.start_pic:
            await message.reply_photo(settings.start_pic, caption=text)
        else:
            await message.reply_text(text)

    @bot.on_message(filters.private & filters.command("rename"))
    async def rename_handler(client: Client, message: Message) -> None:
        user_id = message.from_user.id
        if not await is_subscribed(client, settings.force_sub_channel, user_id):
            await message.reply_text(f"Please join {settings.force_sub_channel} and try again.")
            return
        replied = message.reply_to_message
        if not replied or not replied.document:
            await message.reply_text("Reply to a document with /rename New Name.ext")
            return
        requested = message.text.split(maxsplit=1)
        if len(requested) != 2:
            await message.reply_text("Usage: /rename New Name.ext")
            return
        original_suffix = Path(replied.document.file_name or "").suffix
        try:
            target_name = safe_filename(requested[1], original_suffix)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return
        await db.register_user(user_id)
        await worker.submit(RenameJob(user_id, message.chat.id, replied.id, target_name))
        await message.reply_text("⏳ Added to the rename queue.")

    @bot.on_message(filters.private & filters.command("status"))
    async def status_handler(_: Client, message: Message) -> None:
        await message.reply_text(f"Queued jobs: {worker.queue.qsize()}")

    @bot.on_message(filters.private & filters.command("admin") & filters.user(settings.admin_id))
    async def admin_handler(_: Client, message: Message) -> None:
        users = await db.db.users.count_documents({})
        jobs = await db.db.jobs.count_documents({})
        await message.reply_text(f"Users: {users}\nJobs: {jobs}\nQueue: {worker.queue.qsize()}")
