from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath


def safe_filename(requested: str, original_suffix: str = "") -> str:
    name = unicodedata.normalize("NFC", requested.strip())
    if any(c in name for c in '/\\<>:"|?*') or any(unicodedata.category(c).startswith("C") for c in name):
        raise ValueError('Use a filename without slashes, control characters or < > : " | ? *.')
    name = name.rstrip(" .")
    if not name or name in {".", ".."}:
        raise ValueError("Enter a non-empty filename.")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", name.split(".")[0].rstrip(" "), re.I):
        raise ValueError("That filename is reserved by Windows. Choose another name.")
    if not PurePosixPath(name).suffix and re.fullmatch(r"\.[A-Za-z0-9]{1,15}", original_suffix):
        name += original_suffix
    if len(name.encode("utf-8")) > 120:
        raise ValueError("Filename is too long. Use at most 120 UTF-8 bytes (fewer for Telugu/emoji).")
    return name


async def is_subscribed(client, channel, user_id: int) -> bool:
    if not channel:
        return True
    from pyrogram.enums import ChatMemberStatus
    from pyrogram.errors import UserNotParticipant
    try:
        member = await client.get_chat_member(channel, user_id)
        if member.status == ChatMemberStatus.RESTRICTED:
            return bool(member.is_member)
        return member.status not in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT)
    except UserNotParticipant:
        return False
