from __future__ import annotations

import asyncio

from .clients import build_clients
from .config import Settings
from .database import Database
from .handlers import register_handlers
from .worker import RenameWorker


async def run() -> None:
    settings = Settings.load()
    db = Database(settings.database_url, settings.database_name)
    await db.ping()
    bot, premium = build_clients(settings)
    worker = RenameWorker(bot, premium, db, settings)
    register_handlers(bot, db, worker, settings)
    await premium.start()
    await bot.start()
    await worker.start()
    print("Renamer bot started")
    try:
        await asyncio.Event().wait()
    finally:
        await worker.stop()
        await bot.stop()
        await premium.stop()
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())

