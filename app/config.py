from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    admin_id: int
    string_session: str
    staging_chat_id: int
    force_sub_channel: str | None
    log_channel_id: int | None
    database_url: str
    database_name: str
    start_pic: str | None
    work_dir: Path
    max_concurrent_jobs: int

    @classmethod
    def load(cls) -> "Settings":
        work_dir = Path(os.getenv("WORK_DIR", "/tmp/renamer")).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            api_id=int(required("API_ID")),
            api_hash=required("API_HASH"),
            bot_token=required("BOT_TOKEN"),
            admin_id=int(required("ADMIN_ID")),
            string_session=required("STRING_SESSION"),
            staging_chat_id=int(required("STAGING_CHAT_ID")),
            force_sub_channel=os.getenv("FORCE_SUB_CHANNEL") or None,
            log_channel_id=int(os.environ["LOG_CHANNEL_ID"]) if os.getenv("LOG_CHANNEL_ID") else None,
            database_url=required("DATABASE_URL"),
            database_name=os.getenv("DATABASE_NAME", "renamer_bot"),
            start_pic=os.getenv("START_PIC") or None,
            work_dir=work_dir,
            max_concurrent_jobs=max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1"))),
        )

