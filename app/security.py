from __future__ import annotations

import re
from pathlib import Path

from pyrogram import Client, enums
from pyrogram.errors import UserNotParticipant

SAFE_NAME = re.compile(r"[^\w.()\[\] -]+", re.UNICODE)


def safe_filename(value: str, original_suffix: str = "") -> str:
    name = Path(value.strip()).name
    name = SAFE_NAME.sub("_", name).strip(" .")
    if not name:
        raise ValueError("Filename is empty after sanitization")
    if "." not in name and original_suffix:
        name += original_suffix
    return name[:240]


async def is_subscribed(bot: Client, channel: str | None, user_id: int) -> bool:
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status not in {enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT}
    except UserNotParticipant:
        return False

