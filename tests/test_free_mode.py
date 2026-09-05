from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from contextlib import aclosing, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.clients import build_clients, upload_limit_bytes, verify_telegram
from app.config import FREE_UPLOAD_BYTES, MAX_FILE_BYTES, Settings, SetupError
from app.parts import join_parts, load_manifest, split_file, write_manifest
from app.parts_tool import split_local
from app.worker import RenameJob, RenameWorker
from test_bot import fixture_values


def free_values():
    return {**fixture_values(), "TRANSFER_MODE": "bot", "STRING_SESSION": "", "STAGING_CHAT_ID": ""}


class FreeConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bot_mode_needs_neither_session_nor_staging(self):
        settings = Settings.from_values(free_values())
        self.assertIsNone(settings.staging_chat_id)
        bot, user = build_clients(settings)
        self.assertIsNone(user)
        bot.me = SimpleNamespace(is_bot=True, is_premium=None)
        await verify_telegram(bot, user, settings)
        self.assertEqual(upload_limit_bytes(bot), FREE_UPLOAD_BYTES)

    async def test_old_invalid_session_ignored_in_bot_mode(self):
        values = free_values()
        values.pop("TRANSFER_MODE")
        values.update(STRING_SESSION="old-invalid-session", STAGING_CHAT_ID="not-a-number")
        settings = Settings.from_values(values)
        self.assertEqual(settings.transfer_mode, "bot")
        self.assertEqual(settings.string_session, "")
        self.assertIsNone(settings.staging_chat_id)

    async def test_user_mode_still_requires_valid_session(self):
        with self.assertRaises(SetupError):
            Settings.from_values({**free_values(), "TRANSFER_MODE": "user"})

    async def test_standard_and_premium_limits_differ(self):
        user = SimpleNamespace(me=SimpleNamespace(is_bot=False, is_premium=False))
        self.assertEqual(upload_limit_bytes(user), FREE_UPLOAD_BYTES)
        user.me.is_premium = True
        self.assertEqual(upload_limit_bytes(user), MAX_FILE_BYTES)

    async def test_generator_saves_standard_session_without_disclosure(self):
        from app.generate_session import generate
        session = fixture_values()["STRING_SESSION"]
        client = SimpleNamespace(connect=AsyncMock(), send_code=AsyncMock(return_value=SimpleNamespace(phone_code_hash="fake")),
                                 sign_in=AsyncMock(return_value=SimpleNamespace(id=123)),
                                 get_me=AsyncMock(return_value=SimpleNamespace(is_bot=False, is_premium=False)),
                                 export_session_string=AsyncMock(return_value=session), disconnect=AsyncMock(), is_connected=True)
        output = io.StringIO()
        with patch("pyrogram.Client", return_value=client), patch("app.generate_session.read_values", return_value=free_values()), \
             patch("app.generate_session.getpass.getpass", side_effect=["+10000000000", "12345"]), \
             patch("app.generate_session.write_values") as save, redirect_stdout(output):
            await generate()
        self.assertEqual(save.call_args.args[0]["STRING_SESSION"], session)
        self.assertNotIn(session, output.getvalue())
        self.assertIn("2000 MiB (standard account)", output.getvalue())
        client.disconnect.assert_awaited_once()


class PartsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "original.bin"
        self.payload = b"KBC REBOT binary content\x00\xff with spaces"
        self.source.write_bytes(self.payload)
        self.output = self.root / "parts"
        self.output.mkdir()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def prepare(self):
        async with aclosing(split_file(self.source, self.output, "Renamed.bin", limit=7)) as iterator:
            parts = [part async for part in iterator]
        self.assertTrue(all(0 < part.size <= 7 for part in parts))
        return write_manifest(self.output, "Renamed.bin", parts)

    async def test_split_and_join_preserve_every_byte_and_original(self):
        manifest = await self.prepare()
        joined = join_parts(manifest)
        self.assertEqual(joined.name, "Renamed.bin")
        self.assertEqual(joined.read_bytes(), self.payload)
        self.assertEqual(self.source.read_bytes(), self.payload)

    async def test_corrupt_part_removes_incomplete_output(self):
        manifest = await self.prepare()
        first = self.output / "Renamed.bin.part001"
        first.write_bytes(b"!" * first.stat().st_size)
        with self.assertRaises(SetupError):
            join_parts(manifest)
        self.assertFalse((self.output / "Renamed.bin").exists())
        self.assertTrue(first.exists())

    async def test_missing_part_rejected_without_output(self):
        manifest = await self.prepare()
        (self.output / "Renamed.bin.part001").unlink()
        with self.assertRaises(SetupError):
            join_parts(manifest)
        self.assertFalse((self.output / "Renamed.bin").exists())

    async def test_existing_file_never_overwritten(self):
        manifest = await self.prepare()
        target = self.output / "Renamed.bin"
        target.write_bytes(b"existing document")
        with self.assertRaises(SetupError):
            join_parts(manifest)
        self.assertEqual(target.read_bytes(), b"existing document")

    async def test_manifest_rejects_traversal_and_invalid_shapes(self):
        manifest = await self.prepare()
        original = json.loads(manifest.read_text(encoding="utf-8"))
        bad_names = ("../outside", "C:\\outside", "CON.txt")
        for name in bad_names:
            manifest.write_text(json.dumps({**original, "filename": name}))
            with self.assertRaises(SetupError):
                load_manifest(manifest)
        for value in ([], {**original, "filename": None}, {**original, "parts": "bad"}):
            manifest.write_text(json.dumps(value))
            with self.assertRaises(SetupError):
                load_manifest(manifest)
        original["parts"][0]["name"] = "../outside"
        manifest.write_text(json.dumps(original))
        with self.assertRaises(SetupError):
            load_manifest(manifest)

    async def test_local_split_tool_preserves_source_and_publishes_complete_directory(self):
        with redirect_stdout(io.StringIO()):
            directory = await split_local(self.source, "Local.bin")
        manifest = directory / "Local.bin.kbc-parts.json"
        self.assertTrue(manifest.exists())
        self.assertEqual(join_parts(manifest).read_bytes(), self.payload)
        self.assertTrue(self.source.exists())
        self.assertEqual(list(self.root.glob(".kbc-split-*")), [])


class FreeWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings.from_values({**free_values(), "WORK_DIR": self.temp.name})
        self.message = SimpleNamespace(id=5, owner="bot")
        self.payload = b"abcdefghijkl"
        self.uploads = {}

        async def download(source, file_name, **kwargs):
            self.assertIs(source, self.message)
            Path(file_name).write_bytes(self.payload)
            return file_name

        async def send(chat_id, path, **kwargs):
            self.assertEqual(chat_id, 1)
            self.uploads[kwargs["file_name"]] = Path(path).read_bytes()
            return SimpleNamespace(id=len(self.uploads))

        self.bot = SimpleNamespace(me=SimpleNamespace(is_bot=True, is_premium=False), get_messages=AsyncMock(return_value=self.message),
                                   download_media=AsyncMock(side_effect=download), send_document=AsyncMock(side_effect=send),
                                   send_message=AsyncMock(return_value=SimpleNamespace(id=10)), edit_message_text=AsyncMock(),
                                   copy_message=AsyncMock(), delete_messages=AsyncMock())
        self.db = SimpleNamespace(create_job=AsyncMock(), set_job_status=AsyncMock())
        self.worker = RenameWorker(self.bot, None, self.db, self.settings)

    async def asyncTearDown(self):
        await self.worker.stop()
        self.temp.cleanup()

    def job(self, split=False, size=None):
        return RenameJob(1, 1, 5, "New.bin", len(self.payload) if size is None else size, split_output=split)

    async def drain(self):
        if self.worker.runner is None:
            await self.worker.start()
        await asyncio.wait_for(self.worker.queue.join(), 5)

    async def test_direct_bot_download_upload_no_staging(self):
        await self.worker.submit(self.job())
        await self.drain()
        self.bot.get_messages.assert_awaited_once_with(1, 5)
        self.assertEqual(self.uploads, {"New.bin": self.payload})
        self.bot.copy_message.assert_not_awaited()
        self.bot.delete_messages.assert_not_awaited()
        self.assertEqual(list((self.settings.work_dir / "jobs").iterdir()), [])

    async def test_4gb_input_requires_explicit_split_command(self):
        with self.assertRaisesRegex(SetupError, "/splitrename"):
            await self.worker.submit(self.job(size=MAX_FILE_BYTES))
        await self.worker.submit(self.job(split=True, size=MAX_FILE_BYTES))
        self.assertEqual(self.worker.queue.qsize(), 1)

    async def test_split_delivery_can_be_joined_and_temp_files_are_removed(self):
        self.worker.upload_limit = 5  # Exercise the same streaming path with small test files.
        await self.worker.submit(self.job(split=True))
        await self.drain()
        self.assertEqual(set(self.uploads), {"New.bin.part001", "New.bin.part002", "New.bin.part003", "New.bin.kbc-parts.json"})
        restored = Path(self.temp.name) / "downloaded"
        restored.mkdir()
        for name, content in self.uploads.items():
            (restored / name).write_bytes(content)
        self.assertEqual(join_parts(restored / "New.bin.kbc-parts.json").read_bytes(), self.payload)
        self.assertEqual(list((self.settings.work_dir / "jobs").iterdir()), [])

    async def test_split_cancel_closes_files_on_windows_and_queue_survives(self):
        self.worker.upload_limit = 5
        blocked = asyncio.Event()

        async def block_send(*args, **kwargs):
            blocked.set()
            await asyncio.Event().wait()

        self.bot.send_document.side_effect = block_send
        await self.worker.submit(self.job(split=True))
        await self.worker.start()
        await asyncio.wait_for(blocked.wait(), 5)
        await self.worker.cancel(1)
        await self.drain()
        self.assertEqual(list((self.settings.work_dir / "jobs").iterdir()), [])
        self.assertFalse(self.worker.runner.done())
