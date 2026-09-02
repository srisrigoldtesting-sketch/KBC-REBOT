from pyrogram import Client
from pyrogram.session import Session

from .config import Settings


def build_clients(settings: Settings) -> tuple[Client, Client]:
    bot = Client(
        "renamer_bot",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        in_memory=True,
    )
    premium = Client(
        "premium_worker",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        session_string=settings.string_session,
        in_memory=True,
    )
    # Telegram Premium accounts may transfer files up to 4 GiB.
    Session.MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024
    return bot, premium

