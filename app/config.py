from __future__ import annotations

import base64
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
MAX_FILE_BYTES = 4000 * 1024 * 1024  # Pyrofork Premium limit: 4000 MiB.
FREE_UPLOAD_BYTES = 2000 * 1024 * 1024
DISK_RESERVE = 1024 * 1024 * 1024


class SetupError(ValueError):
    """Actionable message containing no credential values."""


def read_values(path: Path = ENV_FILE) -> dict[str, str]:
    return {k: v or "" for k, v in dotenv_values(path, interpolate=False).items()}


def required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value or value.lower().startswith(("replace_", "your_", "paste_")):
        raise SetupError(f"Set {key} in CONFIGURE.cmd or the private .env file.")
    return value


def validate_app(values: Mapping[str, str]) -> tuple[int, str]:
    api_id = required(values, "API_ID")
    if not api_id.isdecimal() or not 0 < int(api_id) < 2**31:
        raise SetupError("API_ID must be a positive numeric Telegram app ID.")
    api_hash = required(values, "API_HASH")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        raise SetupError("API_HASH must contain exactly 32 hexadecimal characters.")
    return int(api_id), api_hash


def validate_session(value: str) -> None:
    formats = {351: ">B?256sI?", 356: ">B?256sQ?", 362: ">BI?256sQ?"}
    try:
        fmt = formats.get(len(value))
        if not fmt or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError
        parts = struct.unpack(fmt, base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
        if parts[-1] or parts[-4] or not 1 <= parts[0] <= 5:
            raise ValueError
    except (ValueError, struct.error):
        raise SetupError("STRING_SESSION must be a production Pyrogram/Pyrofork USER session. Use GENERATE_SESSION.cmd.") from None


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    bot_token: str = field(repr=False)
    admin_id: int
    string_session: str = field(repr=False)
    staging_chat_id: int | None
    work_dir: Path
    force_sub_channel: str | int | None = None
    log_channel_id: int | None = None
    database_url: str = field(default="", repr=False)
    database_name: str = "cluster0"
    start_pic: str | None = None
    max_concurrent_jobs: int = 1
    transfer_mode: str = "bot"

    @classmethod
    def from_values(cls, source: Mapping[str, str], root: Path = ROOT) -> "Settings":
        values = {k: str(v).strip() for k, v in source.items()}
        for old, new in (("ADMIN", "ADMIN_ID"), ("FORCE_SUBS", "FORCE_SUB_CHANNEL"), ("LOG_CHANNEL", "LOG_CHANNEL_ID")):
            if new not in values and old in values:
                values[new] = values[old]
        api_id, api_hash = validate_app(values)
        token = required(values, "BOT_TOKEN")
        if not re.fullmatch(r"[0-9]{5,15}:[A-Za-z0-9_-]{35}", token):
            raise SetupError("BOT_TOKEN must be ONE token from BotFather, without < >, spaces or repeated copies.")
        mode = (values.get("TRANSFER_MODE") or "bot").lower()
        if mode not in ("bot", "user"):
            raise SetupError("TRANSFER_MODE must be bot (no session required) or user (optional account session).")
        session = required(values, "STRING_SESSION") if mode == "user" else ""
        if session:
            validate_session(session)
        try:
            admin = int(required(values, "ADMIN_ID"))
            staging = int(required(values, "STAGING_CHAT_ID")) if mode == "user" else None
            log = int(values["LOG_CHANNEL_ID"]) if values.get("LOG_CHANNEL_ID") else None
            concurrency = int(values.get("MAX_CONCURRENT_JOBS") or "1")
        except ValueError as exc:
            if isinstance(exc, SetupError):
                raise
            raise SetupError("ADMIN_ID, STAGING_CHAT_ID, LOG_CHANNEL_ID and MAX_CONCURRENT_JOBS must be numbers.") from None
        if admin <= 0 or (staging is not None and staging >= -1000000000000) or (log is not None and log >= 0):
            raise SetupError("Use a positive ADMIN_ID. In user mode, STAGING_CHAT_ID must be a private channel ID starting with -100.")
        if concurrency != 1:
            raise SetupError("Set MAX_CONCURRENT_JOBS=1 for this laptop edition.")
        database_url = values.get("DATABASE_URL", "")
        if database_url and not database_url.startswith(("mongodb://", "mongodb+srv://")):
            raise SetupError("DATABASE_URL must be a MongoDB URI, or leave it blank to use local SQLite.")
        database_name = values.get("DATABASE_NAME") or "cluster0"
        if re.search(r'[/\\. "$*<>:|?\x00]', database_name):
            raise SetupError("DATABASE_NAME contains an unsupported character.")
        force: str | int | None = values.get("FORCE_SUB_CHANNEL") or None
        if force and str(force).lstrip("-").isdigit():
            force = int(force)
        work_dir = Path(values.get("WORK_DIR") or "data").expanduser()
        if not work_dir.is_absolute():
            work_dir = root / work_dir
        return cls(api_id=api_id, api_hash=api_hash, bot_token=token, admin_id=admin,
                   string_session=session, staging_chat_id=staging, work_dir=work_dir.resolve(),
                   force_sub_channel=force, log_channel_id=log, database_url=database_url,
                   database_name=database_name, start_pic=values.get("START_PIC") or None, transfer_mode=mode)

    @classmethod
    def load(cls) -> "Settings":
        return cls.from_values({**read_values(), **os.environ})
