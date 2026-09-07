"""User preferences and explicitly authorized administrator operations."""
import asyncio
import time
from io import BytesIO

from .config import SetupError
from .plans import describe_plan, require_access, validate_caption
from .security import is_subscribed
from .worker import telegram_call

ADMIN_COMMANDS = ["users", "allids", "broadcast", "warn", "ceasepower", "resetpower", "addpremium", "restart"]


class BotControl:
    def __init__(self):
        self.restart = asyncio.Event()
        self.broadcast_task = None
        self.plan_lock = asyncio.Lock()

    async def close(self):
        if self.broadcast_task:
            self.broadcast_task.cancel()
            await asyncio.gather(self.broadcast_task, return_exceptions=True)
            self.broadcast_task = None


async def broadcast_message(bot, db, source, admin_id, pause=0.1):
    sent = failed = 0
    try:
        async for user_id in db.iter_user_ids():
            try:
                async with asyncio.timeout(180):
                    await telegram_call(bot.copy_message, user_id, source.chat.id, source.id)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(pause)
        summary = f"Broadcast finished. Sent: {sent}; failed/blocked: {failed}."
    except asyncio.CancelledError:
        raise
    except Exception:
        summary = f"Broadcast stopped by a database/service error. Sent: {sent}; failed: {failed}."
    try:
        await bot.send_message(admin_id, summary)
    except Exception:
        pass


def positive_id(value):
    if not value.isdecimal() or not 0 < int(value) < 2**63:
        raise SetupError("User ID must be a positive number from /allids.")
    return int(value)


def register_features(bot, db, worker, settings, control):
    from pyrogram import filters

    @bot.on_message(filters.private & filters.command(["set_caption", "see_caption", "del_caption", "ping", "myplan", "donate", "upgrade"]))
    async def user_features(client, message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        parts = (message.text or "").split(maxsplit=1)
        command = parts[0].split("@", 1)[0].lower()
        try:
            if command == "/ping":
                started = time.monotonic()
                reply = await message.reply_text("Pinging...")
                await reply.edit_text(f"Pong! Message round trip: {(time.monotonic() - started) * 1000:.0f} ms. This is not file transfer speed.")
                return
            if command in ("/upgrade", "/donate"):
                text = ("Free trial: 6 hours, inputs up to 2000 MiB.\n" + settings.plan_price_text +
                        "\nAdmin activation required. Bot Premium is separate from Telegram Premium.") if command == "/upgrade" else settings.donation_text
                await message.reply_text(f"{text}\nAdmin Telegram ID: {settings.admin_id}")
                return
            profile = await db.get_profile(user_id)
            if command == "/myplan":
                await message.reply_text(describe_plan(profile, user_id, settings.admin_id, worker.upload_limit))
            elif command == "/see_caption":
                await message.reply_text(profile["caption"] or "No custom caption. Set one with /set_caption Your text {filename}")
            elif command == "/del_caption":
                await db.update_profile(user_id, caption=None)
                await message.reply_text("Custom caption removed.")
            else:
                if not await is_subscribed(client, settings.force_sub_channel, user_id):
                    raise SetupError(f"Join {settings.force_sub_channel}, then try again.")
                await require_access(db, user_id, settings.admin_id)
                if len(parts) != 2:
                    raise SetupError("Use /set_caption Your text {filename} — {filesize}")
                await db.update_profile(user_id, caption=validate_caption(parts[1]))
                await message.reply_text("Caption saved for your next uploads. Placeholders: {filename}, {filesize}.")
        except SetupError as exc:
            await message.reply_text(str(exc))
        except Exception:
            await message.reply_text("Command failed. Try again or ask the admin to check the bot.")

    @bot.on_message(filters.private & filters.command(ADMIN_COMMANDS) & filters.user(settings.admin_id))
    async def admin_features(client, message):
        # Keep a second explicit check so dispatch changes cannot bypass authorization.
        if not message.from_user or message.from_user.id != settings.admin_id:
            return
        parts = (message.text or "").split()
        command = parts[0].split("@", 1)[0].lower()
        try:
            if control.restart.is_set():
                raise SetupError("Restart is already in progress.")
            if command == "/users":
                users, _ = await db.counts()
                await message.reply_text(f"Total registered users: {users}")
            elif command == "/allids":
                with BytesIO() as file:
                    file.name = "KBC-REBOT-user-ids.txt"
                    async for user_id in db.iter_user_ids():
                        file.write(f"{user_id}\n".encode())
                    if not file.tell():
                        await message.reply_text("No registered users yet.")
                        return
                    file.seek(0)
                    await message.reply_document(file, caption="Registered user IDs — admin only.")
            elif command == "/broadcast":
                source = message.reply_to_message
                if not source:
                    raise SetupError("Reply to the message/photo you want to send to all registered users with /broadcast.")
                if control.broadcast_task and not control.broadcast_task.done():
                    raise SetupError("A broadcast is already running.")
                control.broadcast_task = asyncio.create_task(broadcast_message(client, db, source, settings.admin_id), name="admin-broadcast")
                await message.reply_text("Broadcast started. A sent/failed summary will follow.")
            elif command == "/restart":
                await message.reply_text("Restarting KBC REBOT. Active/queued renames and any broadcast will be cancelled. Saved plans, captions and thumbnails remain.")
                worker.stopping = True
                control.restart.set()
            else:
                if len(parts) < 2:
                    raise SetupError("Specify the user ID. Examples: /warn ID text, /addpremium ID 30 4000, /ceasepower ID 500, /resetpower ID")
                target = positive_id(parts[1])
                if not await db.has_user(target):
                    raise SetupError("Unknown user. Ask them to send /start to this bot first.")
                if command == "/warn":
                    text_parts = (message.text or "").split(maxsplit=2)
                    if len(text_parts) == 3:
                        await telegram_call(client.send_message, target, text_parts[2])
                    elif message.reply_to_message:
                        source = message.reply_to_message
                        await telegram_call(client.copy_message, target, source.chat.id, source.id)
                    else:
                        raise SetupError("Use /warn USER_ID Your message, or reply to a message with /warn USER_ID.")
                    await message.reply_text("Message delivered.")
                    return
                if target == settings.admin_id:
                    raise SetupError("The admin account has unrestricted bot access; its plan cannot be changed.")
                async with control.plan_lock:
                    profile = await db.get_profile(target)
                    if command == "/addpremium":
                        if len(parts) not in (3, 4) or not parts[2].isdecimal():
                            raise SetupError("Use /addpremium USER_ID DAYS [CAPACITY_MIB]. Example: /addpremium 123456 30 4000")
                        days = int(parts[2])
                        capacity = int(parts[3]) if len(parts) == 4 and parts[3].isdecimal() else (4000 if len(parts) == 3 else -1)
                        if not 1 <= days <= 3650 or not 1 <= capacity <= 4000:
                            raise SetupError("DAYS must be 1–3650; CAPACITY_MIB must be 1–4000.")
                        until = max(int(time.time()), profile["premium_until"]) + days * 86400
                        await db.update_profile(target, premium_until=until, capacity_mib=capacity)
                        await message.reply_text(f"Premium activated/extended for {target}: +{days} days, {capacity} MiB input capacity. Telegram upload limits still apply.")
                    elif command == "/ceasepower":
                        capacity = int(parts[2]) if len(parts) == 3 and parts[2].isdecimal() else (0 if len(parts) == 2 else -1)
                        if not 0 <= capacity <= profile["capacity_mib"]:
                            raise SetupError("Specify a lower capacity in MiB, or omit it to disable renaming. Use /addpremium or /resetpower to increase capacity.")
                        await db.update_profile(target, capacity_mib=capacity)
                        await worker.cancel(target)
                        await message.reply_text(f"Capacity for {target}: {capacity} MiB. Existing job cancellation requested; expiry unchanged.")
                    elif command == "/resetpower":
                        if len(parts) != 2:
                            raise SetupError("Use /resetpower USER_ID")
                        await db.update_profile(target, capacity_mib=2000)
                        await worker.cancel(target)
                        await message.reply_text(f"Capacity reset to 2000 MiB for {target}. Trial/premium expiry was not extended.")
        except SetupError as exc:
            await message.reply_text(str(exc))
        except Exception:
            await message.reply_text("Admin command failed. No success is confirmed; check /myplan or /users before retrying a plan change. The user may have blocked the bot.")
