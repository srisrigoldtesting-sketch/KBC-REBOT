from __future__ import annotations

import asyncio
import base64
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import MAX_FILE_BYTES, Settings, SetupError, read_values, validate_session
from app.configure import write_values
from app.database import Database
from app.main import error_message
from app.runlock import RunLock
from app.security import safe_filename
from app.worker import RenameJob, RenameWorker, telegram_call


def fixture_values():
    # Synthetic, nonfunctional credentials; no account is contacted by tests.
    session = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", 2, 123456, False, b"x" * 256, 123456, False)).decode().rstrip("=")
    return dict(API_ID="123456", API_HASH="a" * 32, BOT_TOKEN="123456:" + "b" * 35,
                ADMIN_ID="123456", STRING_SESSION=session, STAGING_CHAT_ID="-1001234567890",
                DATABASE_URL="", WORK_DIR="data", TRANSFER_MODE="user")


class ConfigurationTests(unittest.TestCase):
    def test_config_redacts_credentials_and_uses_relative_data_folder(self):
        values = fixture_values()
        settings = Settings.from_values(values, Path(tempfile.gettempdir()))
        for key in ("API_HASH", "BOT_TOKEN", "STRING_SESSION"):
            self.assertNotIn(values[key], repr(settings))
        self.assertEqual(settings.work_dir, (Path(tempfile.gettempdir()) / "data").resolve())

    def test_bad_token_forms_rejected_without_disclosure(self):
        values = fixture_values()
        token = values["BOT_TOKEN"]
        for malformed in (f"<{token}>", token + token, "replace_with_token", "1234:bad"):
            with self.subTest(malformed=malformed[:4]):
                with self.assertRaises(SetupError) as error:
                    Settings.from_values({**values, "BOT_TOKEN": malformed})
                self.assertNotIn(malformed, str(error.exception))

    def test_bad_session_is_not_echoed(self):
        with self.assertRaises(SetupError) as error:
            validate_session("not-a-session-PRIVATE")
        self.assertNotIn("PRIVATE", str(error.exception))

    def test_legacy_and_current_user_sessions_supported(self):
        for fmt, args in ((">B?256sI?", (2, False, b"x"*256, 123, False)),
                          (">B?256sQ?", (2, False, b"x"*256, 123, False)),
                          (">BI?256sQ?", (2, 123, False, b"x"*256, 123, False))):
            validate_session(base64.urlsafe_b64encode(struct.pack(fmt, *args)).decode().rstrip("="))

    def test_test_account_or_bot_session_rejected(self):
        for test_mode, is_bot in ((True, False), (False, True)):
            session = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", 2, 123, test_mode, b"x"*256, 123, is_bot)).decode().rstrip("=")
            with self.assertRaises(SetupError):
                validate_session(session)

    def test_old_environment_names_supported(self):
        values = fixture_values()
        values["ADMIN"] = values.pop("ADMIN_ID")
        values["FORCE_SUBS"] = "@example_channel"
        values["LOG_CHANNEL"] = "-1001234567890"
        settings = Settings.from_values(values)
        self.assertEqual(settings.admin_id, 123456)
        self.assertEqual(settings.force_sub_channel, "@example_channel")

    def test_env_roundtrip_preserves_quotes_dollars_and_windows_paths(self):
        values = {"DATABASE_URL": "mongodb://" + "user:p'ass$word@localhost", "WORK_DIR": r"C:\KBC REBOT\data", "CUSTOM": "${UNSET_VARIABLE}"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            write_values(values, path)
            self.assertEqual(read_values(path), values)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_exception_text_never_reveals_raw_sdk_secrets(self):
        self.assertNotIn("PRIVATE", error_message(RuntimeError("PRIVATE")))

    def test_filename_validation(self):
        for invalid in ("../a", "C:\\a", "a/b", "a\x00.txt", "CON.txt", "LPT1", "..", "a?b", "😀"*31, "a"*121, "photo\u202Etxt"):
            with self.subTest(name=invalid):
                with self.assertRaises(ValueError):
                    safe_filename(invalid)
        self.assertEqual(safe_filename("My Movie", ".mkv"), "My Movie.mkv")
        self.assertEqual(safe_filename("తెలుగు.mp4"), "తెలుగు.mp4")

    def test_single_process_lock_releases_after_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock"
            with RunLock(path):
                with self.assertRaises(SetupError):
                    with RunLock(path):
                        pass
            with RunLock(path):
                pass


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_records_users_jobs_and_marks_interrupted_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database("", "test", Path(directory))
            try:
                await db.ping()
                await db.register_user(1)
                await db.register_user(1)
                await db.create_job("one", 1, "Movie.mkv")
                await db.create_job("two", 1, "Other.mkv")
                await db.set_job_status("one", "done")
                await db.recover()
                self.assertEqual(await db.counts(), (1, 2))
                statuses = dict(db.local.execute("SELECT id,status FROM jobs").fetchall())
                self.assertEqual(statuses, {"one": "done", "two": "interrupted"})
            finally:
                await db.close()


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings.from_values({**fixture_values(), "WORK_DIR": self.temp.name})
        self.db = SimpleNamespace(create_job=AsyncMock(), set_job_status=AsyncMock())
        self.staged = SimpleNamespace(id=11)
        self.premium_message = SimpleNamespace(id=11, owner="premium")
        self.bot = SimpleNamespace(copy_message=AsyncMock(return_value=self.staged), send_message=AsyncMock(return_value=SimpleNamespace(id=9)),
                                   edit_message_text=AsyncMock(), delete_messages=AsyncMock())
        self.paths = []

        async def download(message, file_name, **kwargs):
            self.assertIs(message, self.premium_message)
            Path(file_name).write_bytes(b"data")
            self.paths.append(Path(file_name))
            return file_name

        self.premium = SimpleNamespace(get_messages=AsyncMock(return_value=self.premium_message),
                                       download_media=AsyncMock(side_effect=download), send_document=AsyncMock(return_value=SimpleNamespace(id=22)),
                                       me=SimpleNamespace(is_bot=False, is_premium=True))
        self.worker = RenameWorker(self.bot, self.premium, self.db, self.settings)

    async def asyncTearDown(self):
        await self.worker.stop()
        self.temp.cleanup()

    def job(self, user=1, size=4):
        return RenameJob(user, user, 5, "Same Movie.mkv", size)

    async def drain(self):
        if not self.worker.runner:
            await self.worker.start()
        await asyncio.wait_for(self.worker.queue.join(), 5)

    async def test_refetch_as_premium_upload_copy_back_and_cleanup(self):
        job = self.job()
        await self.worker.submit(job)
        await self.drain()
        self.premium.get_messages.assert_awaited_once_with(self.settings.staging_chat_id, 11)
        self.bot.copy_message.assert_any_await(job.user_id, self.settings.staging_chat_id, 22, caption=job.target_name)
        self.bot.delete_messages.assert_awaited_once_with(self.settings.staging_chat_id, [11, 22])
        self.assertEqual(list((self.settings.work_dir / "jobs").iterdir()), [])
        self.db.set_job_status.assert_any_await(job.job_id, "done", None)

    async def test_same_filenames_use_distinct_job_directories(self):
        await self.worker.submit(self.job(1))
        await self.worker.submit(self.job(2))
        await self.drain()
        self.assertEqual(len(self.paths), 2)
        self.assertNotEqual(self.paths[0].parent, self.paths[1].parent)
        self.assertFalse(any(p.exists() for p in self.paths))

    async def test_failure_does_not_kill_queue_even_if_database_and_notifications_fail(self):
        self.db.set_job_status.side_effect = RuntimeError("PRIVATE")
        self.bot.send_message.side_effect = RuntimeError("PRIVATE")
        self.premium.send_document.side_effect = [RuntimeError("PRIVATE"), SimpleNamespace(id=22)]
        await self.worker.submit(self.job(1))
        await self.worker.submit(self.job(2))
        with self.assertLogs("app.worker", level="WARNING") as logs:
            await self.drain()
        self.assertEqual(self.premium.send_document.await_count, 2)
        self.assertFalse(self.worker.runner.done())
        self.assertNotIn("PRIVATE", " ".join(logs.output))

    async def test_partial_download_removed_and_not_uploaded(self):
        job = self.job(size=50)
        await self.worker.submit(job)
        with self.assertLogs("app.worker", level="WARNING"):
            await self.drain()
        self.premium.send_document.assert_not_awaited()
        self.bot.delete_messages.assert_awaited_once_with(self.settings.staging_chat_id, [11])
        self.assertFalse(self.paths[0].parent.exists())

    async def test_active_cancel_cleans_partial_file_and_next_job_succeeds(self):
        started = asyncio.Event()
        original = self.premium.download_media.side_effect

        async def blocked(message, file_name, **kwargs):
            Path(file_name).write_bytes(b"da")
            started.set()
            await asyncio.Event().wait()

        self.premium.download_media.side_effect = blocked
        await self.worker.submit(self.job())
        await self.worker.start()
        await asyncio.wait_for(started.wait(), 5)
        self.assertTrue(await self.worker.cancel(1))
        await self.drain()
        self.assertEqual(list((self.settings.work_dir / "jobs").iterdir()), [])
        self.premium.download_media.side_effect = original
        await self.worker.submit(self.job(2))
        await self.drain()
        self.premium.send_document.assert_awaited_once()

    async def test_queued_cancel_does_not_contact_telegram(self):
        job = self.job()
        await self.worker.submit(job)
        await self.worker.cancel(job.user_id)
        await self.drain()
        self.bot.copy_message.assert_not_awaited()
        self.db.set_job_status.assert_any_await(job.job_id, "cancelled", None)

    async def test_oversize_empty_duplicate_and_full_queue_rejected(self):
        for size in (0, MAX_FILE_BYTES + 1):
            with self.assertRaises(SetupError):
                await self.worker.submit(self.job(size=size))
        await self.worker.submit(self.job(size=MAX_FILE_BYTES))
        with self.assertRaises(SetupError):
            await self.worker.submit(self.job())
        for user in range(2, 11):
            await self.worker.submit(self.job(user))
        with self.assertRaises(SetupError):
            await self.worker.submit(self.job(11))

    async def test_disk_space_checked_before_staging(self):
        await self.worker.submit(self.job())
        with patch("app.worker.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
            with self.assertLogs("app.worker", level="WARNING"):
                await self.drain()
        self.bot.copy_message.assert_not_awaited()

    async def test_rate_limit_retry_is_bounded(self):
        from pyrogram.errors import FloodWait
        method = AsyncMock(side_effect=FloodWait(1))
        with patch("app.worker.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(SetupError):
                await telegram_call(method)
        self.assertEqual(method.await_count, 3)
        self.assertEqual(sleep.await_count, 2)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_library_client_construction_and_session_loading(self):
        from app.clients import build_clients
        settings = Settings.from_values(fixture_values())
        bot, premium = build_clients(settings)
        self.assertEqual(bot.bot_token, settings.bot_token)
        await premium.storage.open()
        try:
            self.assertEqual(await premium.storage.user_id(), 123456)
            self.assertFalse(await premium.storage.is_bot())
        finally:
            await premium.storage.close()

    async def test_missing_session_never_triggers_interactive_login(self):
        from app.clients import connect_client
        client = SimpleNamespace(connect=AsyncMock(return_value=False), authorize=AsyncMock())
        with self.assertRaises(SetupError):
            await connect_client(client)
        client.authorize.assert_not_awaited()

    async def test_bot_session_rejected_before_channel_calls(self):
        from app.clients import verify_telegram
        bot = SimpleNamespace(me=SimpleNamespace(is_bot=True))
        premium = SimpleNamespace(me=SimpleNamespace(is_bot=True, is_premium=False))
        with self.assertRaises(SetupError):
            await verify_telegram(bot, premium, Settings.from_values(fixture_values()))

    async def test_channel_permissions_and_content_protection(self):
        from app.clients import verify_telegram
        from pyrogram.enums import ChatMemberStatus, ChatType
        settings = Settings.from_values(fixture_values())
        chat = SimpleNamespace(id=settings.staging_chat_id, type=ChatType.CHANNEL, username=None, has_protected_content=False)
        member = SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR,
                                 privileges=SimpleNamespace(can_post_messages=True, can_delete_messages=True))

        async def dialogs():
            yield SimpleNamespace(chat=chat)

        bot = SimpleNamespace(me=SimpleNamespace(is_bot=True), get_chat=AsyncMock(return_value=chat), get_chat_member=AsyncMock(return_value=member))
        premium = SimpleNamespace(me=SimpleNamespace(is_bot=False, is_premium=True), get_dialogs=dialogs,
                                  get_chat=AsyncMock(return_value=chat), get_chat_member=AsyncMock(return_value=member))
        await verify_telegram(bot, premium, settings)
        premium.me.is_premium = False
        await verify_telegram(bot, premium, settings)  # Standard accounts are valid too.
        member.privileges.can_delete_messages = False
        with self.assertRaises(SetupError):
            await verify_telegram(bot, premium, settings)
        member.privileges.can_delete_messages = True
        chat.has_protected_content = True
        with self.assertRaises(SetupError):
            await verify_telegram(bot, premium, settings)
        chat.has_protected_content = False
        chat.username = "public_staging"
        with self.assertRaises(SetupError):
            await verify_telegram(bot, premium, settings)


if __name__ == "__main__":
    unittest.main()
