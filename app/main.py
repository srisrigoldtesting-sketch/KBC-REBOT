from __future__ import annotations

import asyncio
import logging
import shutil
import sys

from .config import ROOT, Settings, SetupError
from .runlock import RunLock
from .windows import KeepAwake


def error_message(exc):
    if isinstance(exc, SetupError):
        return str(exc)
    name = type(exc).__name__
    hints = {
        "AccessTokenInvalid": "Replace BOT_TOKEN locally with one fresh token from BotFather.",
        "AccessTokenExpired": "Replace BOT_TOKEN locally with a fresh token from BotFather.",
        "AuthKeyUnregistered": "Run GENERATE_SESSION.cmd to create a new user session.",
        "SessionRevoked": "Run GENERATE_SESSION.cmd to create a new user session.",
        "AuthKeyDuplicated": "Stop other copies using this session, then generate a fresh session.",
        "ApiIdInvalid": "Check API_ID and API_HASH from my.telegram.org.",
        "ChannelInvalid": "In user mode, check STAGING_CHAT_ID and both accounts' access; bot mode needs no staging channel.",
        "ChannelPrivate": "Check channel permissions, or choose bot mode without a staging channel.",
        "PeerIdInvalid": "Check the channel ID and both accounts' membership.",
        "ServerSelectionTimeoutError": "Check MongoDB access, or leave DATABASE_URL blank for SQLite.",
        "PermissionError": "Extract to a writable short path such as C:\\KBC-REBOT.",
        "TimeoutError": "Telegram did not respond in time. Check internet access and try again.",
    }
    return f"{name}: {hints.get(name, 'Run CHECK.cmd; check settings and your internet connection.')}"


async def run(settings):
    from .clients import build_clients, connect_client, disconnect_client, verify_telegram
    from .database import Database
    from .handlers import register_handlers
    from .worker import RenameWorker
    bot, user = build_clients(settings)
    db = worker = None
    try:
        db = Database(settings.database_url, settings.database_name, settings.work_dir)
        await db.ping()
        await db.recover()
        # Only this app's interrupted temporary job folders are removed.
        jobs_dir = settings.work_dir / "jobs"
        if jobs_dir.exists():
            for directory in jobs_dir.glob("job-*"):
                if directory.is_dir() and not directory.is_symlink():
                    shutil.rmtree(directory)
        print("Connecting to Telegram and checking the selected transfer mode...", flush=True)
        async with asyncio.timeout(180):
            if user is not None:
                await connect_client(user)
            await connect_client(bot, settings.bot_token)
            await verify_telegram(bot, user, settings)
        worker = RenameWorker(bot, user, db, settings)
        register_handlers(bot, db, worker, settings)
        await worker.start()
        print(f"KBC REBOT is running: @{bot.me.username}. Keep this window open. Ctrl+C stops it.", flush=True)
        print(f"Single-file upload limit: {worker.upload_limit // 1024**2} MiB. /splitrename returns larger files as parts.", flush=True)
        await asyncio.Event().wait()
    finally:
        if worker:
            await worker.stop()
        await disconnect_client(bot)
        await disconnect_client(user)
        if db:
            await db.close()


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    logging.getLogger("pyrogram").disabled = True
    # Pyrofork logs raw SDK exceptions in child loggers; keep them off the console.
    logging.getLogger("pyrogram").addHandler(logging.NullHandler())
    logging.getLogger("pyrogram").propagate = False
    try:
        settings = Settings.load()
        with RunLock(ROOT / ".kbc.lock"), KeepAwake():
            asyncio.run(run(settings))
    except KeyboardInterrupt:
        print("KBC REBOT stopped.")
        return 0
    except Exception as exc:
        print("KBC REBOT could not start: " + error_message(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
