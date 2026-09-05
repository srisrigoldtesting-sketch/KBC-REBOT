from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import shutil
import sys
import tempfile
from importlib.metadata import version

from .config import DISK_RESERVE, FREE_UPLOAD_BYTES, MAX_FILE_BYTES, ROOT, Settings, SetupError
from .main import error_message
from .runlock import RunLock


async def check(settings, online):
    from .database import Database
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=settings.work_dir) as file:
        file.write(b"kbc")
    free = shutil.disk_usage(settings.work_dir).free
    if free < FREE_UPLOAD_BYTES + DISK_RESERVE:
        raise SetupError("Free at least 3 GiB for standard renaming. For 4GB splitting, keep about 7 GiB available; 10 GiB is recommended.")
    print(f"PASS: data folder writable; {free / 1024**3:.1f} GiB available.")
    if free < MAX_FILE_BYTES + FREE_UPLOAD_BYTES + DISK_RESERVE:
        print("NOTE: more disk space is needed before splitting a maximum-size input.")
    db = Database(settings.database_url, settings.database_name, settings.work_dir)
    try:
        await db.ping()
        print("PASS: metadata database reachable (MongoDB)." if settings.database_url else "PASS: local SQLite database ready.")
    finally:
        await db.close()
    if online:
        from .clients import build_clients, connect_client, disconnect_client, upload_limit_bytes, verify_telegram
        bot, user = build_clients(settings)
        try:
            async with asyncio.timeout(180):
                if user is not None:
                    await connect_client(user)
                await connect_client(bot, settings.bot_token)
                await verify_telegram(bot, user, settings)
            limit = upload_limit_bytes(user if user is not None else bot)
            print(f"PASS: bot @{bot.me.username}; {settings.transfer_mode} mode; single-file upload limit {limit // 1024**2} MiB.")
            if user is None:
                print("No user session, Premium subscription or staging channel is required in bot mode.")
            print("No test files were sent. Run START.cmd and try a small document, then a larger file.")
        finally:
            await disconnect_client(bot)
            await disconnect_client(user)


def main():
    parser = argparse.ArgumentParser(description="KBC REBOT checks; never prints credentials.")
    parser.add_argument("--offline", action="store_true", help="Skip Telegram login; configured MongoDB is still checked.")
    args = parser.parse_args()
    logging.getLogger("pyrogram").addHandler(logging.NullHandler())
    logging.getLogger("pyrogram").propagate = False
    try:
        print(f"Python {platform.python_version()} ({platform.architecture()[0]}), Pyrofork {version('pyrofork')}")
        settings = Settings.load()
        print("PASS: configuration format; secrets hidden.")
        with RunLock(ROOT / ".kbc.lock"):
            asyncio.run(check(settings, not args.offline))
        print("Checks completed.")
        return 0
    except KeyboardInterrupt:
        print("Check cancelled.")
        return 1
    except Exception as exc:
        print("CHECK FAILED: " + error_message(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
