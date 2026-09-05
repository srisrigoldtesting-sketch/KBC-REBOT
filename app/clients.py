from __future__ import annotations

import asyncio
from contextlib import suppress

from .config import FREE_UPLOAD_BYTES, MAX_FILE_BYTES, Settings, SetupError


def upload_limit_bytes(client):
    identity = getattr(client, "me", None)
    return MAX_FILE_BYTES if identity and not identity.is_bot and identity.is_premium else FREE_UPLOAD_BYTES


def build_clients(settings: Settings):
    from pyrogram import Client, enums
    common = dict(api_id=settings.api_id, api_hash=settings.api_hash, in_memory=True,
                  parse_mode=enums.ParseMode.DISABLED, sleep_threshold=30, max_concurrent_transmissions=1)
    user = Client("kbc_user", session_string=settings.string_session, no_updates=True, **common) if settings.transfer_mode == "user" else None
    return Client("kbc_bot", bot_token=settings.bot_token, **common), user


async def connect_client(client, token: str | None = None):
    """Explicit auth avoids interactive fallback in the running bot."""
    from pyrogram import raw
    authorized = await client.connect()
    if not authorized:
        if not token:
            raise SetupError("The saved user session is not authorized. Run GENERATE_SESSION.cmd.")
        await client.sign_in_bot(token)
    await client.invoke(raw.functions.updates.GetState())
    client.me = await client.get_me()
    await client.initialize()


async def disconnect_client(client):
    if client is None:
        return
    with suppress(Exception):
        async with asyncio.timeout(20):
            if client.is_initialized:
                await client.stop()
            elif client.is_connected:
                await client.disconnect()


async def verify_telegram(bot, user, settings: Settings):
    from pyrogram.enums import ChatMemberStatus, ChatType
    if not bot.me.is_bot:
        raise SetupError("BOT_TOKEN must authenticate a Telegram bot.")
    if user is not None:
        if user.me.is_bot:
            raise SetupError("Optional STRING_SESSION must belong to a user account, not another bot.")
        await verify_staging(bot, user, settings)
    if settings.force_sub_channel:
        chat = await bot.get_chat(settings.force_sub_channel)
        if chat.type not in (ChatType.CHANNEL, ChatType.SUPERGROUP):
            raise SetupError("FORCE_SUB_CHANNEL must be a channel/group, not a bot username. Leave it blank to disable.")
        member = await bot.get_chat_member(settings.force_sub_channel, "me")
        if member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            raise SetupError("Make the bot an admin in FORCE_SUB_CHANNEL, or leave that setting blank.")


async def verify_staging(bot, user, settings: Settings):
    from pyrogram.enums import ChatMemberStatus, ChatType
    found = False
    async for dialog in user.get_dialogs():
        if dialog.chat.id == settings.staging_chat_id:
            found = True
            break
    if not found:
        raise SetupError("The optional user account must join the private STAGING_CHAT_ID channel first.")
    for label, client in (("Bot", bot), ("User account", user)):
        chat = await client.get_chat(settings.staging_chat_id)
        if chat.type != ChatType.CHANNEL or chat.username:
            raise SetupError("STAGING_CHAT_ID must be a private broadcast channel without a public username.")
        if chat.has_protected_content:
            raise SetupError("Turn off protected content in the private staging channel so results can be copied back.")
        member = await client.get_chat_member(settings.staging_chat_id, "me")
        if member.status == ChatMemberStatus.OWNER:
            continue
        rights = member.privileges
        if member.status != ChatMemberStatus.ADMINISTRATOR or not rights or not rights.can_post_messages or not rights.can_delete_messages:
            raise SetupError(f"Give the {label} Post Messages and Delete Messages admin permissions in the staging channel.")
