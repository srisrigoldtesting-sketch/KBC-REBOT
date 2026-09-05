from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys
from contextlib import suppress

from .config import ROOT, SetupError, read_values, validate_app
from .configure import write_values
from .main import error_message
from .runlock import RunLock


async def generate():
    from pyrogram import Client, raw
    from pyrogram.errors import PhoneCodeInvalid, SessionPasswordNeeded
    private_values = read_values()
    values = {**private_values, **os.environ}
    api_id, api_hash = validate_app(values)
    client = Client("kbc_session_setup", api_id=api_id, api_hash=api_hash, in_memory=True, no_updates=True)
    saved = False
    try:
        await client.connect()
        phone = getpass.getpass("Your existing Telegram account phone number, including +country code (hidden): ").strip()
        sent = await client.send_code(phone)
        print("Check Telegram or the delivery method Telegram selected. Enter the code only in this local window.")
        for attempt in range(3):
            code = getpass.getpass("Telegram login code (hidden): ").strip().replace(" ", "")
            try:
                result = await client.sign_in(phone, sent.phone_code_hash, code)
                if not getattr(result, "id", None):
                    raise SetupError("Use an existing Telegram account. This tool does not create accounts or accept new account terms.")
                break
            except PhoneCodeInvalid:
                if attempt == 2:
                    raise SetupError("The login code was incorrect. Close this window and try again later.") from None
                print("Incorrect code. Try again.")
            except SessionPasswordNeeded:
                await client.check_password(getpass.getpass("Telegram two-step verification password (hidden): "))
                break
        me = await client.get_me()
        if me.is_bot:
            raise SetupError("Use your existing Telegram user account, not a bot.")
        private_values.update(API_ID=str(api_id), API_HASH=api_hash, STRING_SESSION=await client.export_session_string())
        write_values(private_values)
        saved = True
        print("User session saved directly to your private .env. It was not printed or sent to any chat.")
        print("Account upload limit: " + ("4000 MiB (Premium)." if me.is_premium else "2000 MiB (standard account)."))
        print("Session generation does not grant Premium. Bot mode needs no user session.")
        print("To use this optional session, select user mode in CONFIGURE.cmd and set a private staging channel; then CHECK.cmd and START.cmd.")
    finally:
        if client.is_connected:
            if not saved:
                with suppress(Exception):
                    await client.invoke(raw.functions.auth.LogOut())
            with suppress(Exception):
                await client.disconnect()


def main():
    logging.getLogger("pyrogram").addHandler(logging.NullHandler())
    logging.getLogger("pyrogram").propagate = False
    try:
        with RunLock(ROOT / ".kbc.lock"):
            asyncio.run(generate())
    except KeyboardInterrupt:
        print("Session setup cancelled.")
        return 1
    except Exception as exc:
        print(error_message(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
