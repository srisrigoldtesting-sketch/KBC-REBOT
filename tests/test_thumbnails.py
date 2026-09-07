import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from PIL import Image
from app.config import SetupError
from app.database import Database
from app.handlers import register_handlers
from app.progress import TransferProgress
from app.thumbnails import normalize_thumbnail
import test_free_mode


def photo_bytes():
    with io.BytesIO() as output:
        Image.new("RGBA", (1200, 600), (255, 0, 0, 120)).save(output, "PNG")
        return output.getvalue()


class ThumbnailTests(unittest.IsolatedAsyncioTestCase):
    def test_normalizes_transparency_dimensions_and_format(self):
        jpeg = normalize_thumbnail(photo_bytes())
        self.assertLess(len(jpeg), 200_000)
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (320, 160))
            self.assertEqual(image.mode, "RGB")
            self.assertFalse(image.getexif())

    def test_invalid_and_oversized_images_rejected(self):
        for data in (b"", b"not an image", b"x" * (10 * 1024 * 1024 + 1)):
            with self.assertRaises(SetupError):
                normalize_thumbnail(data)

    async def test_sqlite_thumbnails_survive_restart_and_are_private(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database("", "test", Path(folder))
            await db.set_thumbnail(1, b"first")
            await db.set_thumbnail(2, b"second")
            await db.set_thumbnail(1, b"replacement")
            await db.close()
            db = Database("", "test", Path(folder))
            try:
                self.assertEqual(await db.get_thumbnail(1), b"replacement")
                self.assertEqual(await db.get_thumbnail(2), b"second")
                await db.delete_thumbnail(1)
                self.assertIsNone(await db.get_thumbnail(1))
                self.assertEqual(await db.get_thumbnail(2), b"second")
            finally:
                await db.close()

    async def test_mongodb_uses_sender_id_for_every_operation(self):
        db = Database.__new__(Database)
        db.client = Mock()
        collection = Mock()
        collection.find_one.return_value = {"jpeg": b"image"}
        db.db = SimpleNamespace(thumbnails=collection)
        await db.set_thumbnail(42, b"image")
        self.assertEqual(await db.get_thumbnail(42), b"image")
        await db.delete_thumbnail(42)
        collection.update_one.assert_called_once_with({"_id": 42}, {"$set": {"jpeg": b"image"}}, upsert=True)
        collection.find_one.assert_called_once_with({"_id": 42})
        collection.delete_one.assert_called_once_with({"_id": 42})

    async def test_commands_save_view_delete_only_sender_thumbnail(self):
        handlers = {}
        def register(_):
            def attach(function):
                handlers[function.__name__] = function
                return function
            return attach
        bot = SimpleNamespace(on_message=register, download_media=AsyncMock(return_value=io.BytesIO(photo_bytes())))
        db = SimpleNamespace(set_thumbnail=AsyncMock(), get_thumbnail=AsyncMock(return_value=b"saved"), delete_thumbnail=AsyncMock())
        register_handlers(bot, db, None, SimpleNamespace(admin_id=123, force_sub_channel=None))
        source = SimpleNamespace(photo=SimpleNamespace(file_size=len(photo_bytes())))
        message = SimpleNamespace(from_user=SimpleNamespace(id=42), text="/setthumb", photo=None,
                                  reply_to_message=source, reply_text=AsyncMock(), reply_photo=AsyncMock())
        handler = handlers["thumbnail_handler"]
        await handler(bot, message)
        self.assertEqual(db.set_thumbnail.await_args.args[0], 42)
        with Image.open(io.BytesIO(db.set_thumbnail.await_args.args[1])) as image:
            self.assertEqual(image.format, "JPEG")
        message.text = "/viewthumb"
        await handler(bot, message)
        db.get_thumbnail.assert_awaited_once_with(42)
        message.reply_photo.assert_awaited_once()
        message.text = "/delthumb"
        await handler(bot, message)
        db.delete_thumbnail.assert_awaited_once_with(42)

    async def test_blocked_status_edit_does_not_block_transfer_callback_or_stop(self):
        entered = asyncio.Event()
        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()
        bot = SimpleNamespace(edit_message_text=AsyncMock(side_effect=blocked))
        progress = TransferProgress(bot, 1, 2, "job", interval=0.001)
        progress.begin("Downloading")
        await progress.update(1, 100)
        progress.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.wait_for(progress.update(100, 100), 0.1)
            self.assertEqual(progress.current, 100)
            self.assertEqual(bot.edit_message_text.await_count, 1)
        finally:
            await asyncio.wait_for(progress.stop(), 0.1)
        self.assertIsNone(progress.task)

    def test_speed_eta_and_phase_reset(self):
        with patch("app.progress.time.monotonic", return_value=100):
            progress = TransferProgress(None, 1, None, "job")
            progress.begin("Downloading")
        progress.current, progress.total = 10 * 1024**2, 30 * 1024**2
        with patch("app.progress.time.monotonic", return_value=110):
            self.assertIn("1.00 MiB/s | ETA: 20s", progress.text())
            progress.begin("Uploading")
            self.assertEqual(progress.current, 0)
            self.assertIn("estimating", progress.text())


class ThumbnailDeliveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_free_mode.FreeWorkerTests.asyncSetUp
    asyncTearDown = test_free_mode.FreeWorkerTests.asyncTearDown
    job = test_free_mode.FreeWorkerTests.job
    drain = test_free_mode.FreeWorkerTests.drain

    async def check_uploads(self, split):
        jpeg = normalize_thumbnail(photo_bytes())
        self.db.get_thumbnail.return_value = jpeg
        if split:
            self.worker.upload_limit = 5
        streams = []
        original = self.bot.send_document.side_effect
        async def send(*args, **kwargs):
            thumb = kwargs["thumb"]
            if kwargs["file_name"].endswith(".kbc-parts.json"):
                self.assertIsNone(thumb)
            else:
                self.assertEqual(thumb.read(), jpeg)
                self.assertNotIn(thumb, streams)
                streams.append(thumb)
            return await original(*args, **kwargs)
        self.bot.send_document.side_effect = send
        await self.worker.submit(self.job(split=split))
        await self.drain()
        self.db.get_thumbnail.assert_awaited_once_with(1)
        self.assertEqual(len(streams), 3 if split else 1)
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertFalse(any(task.get_name() == "transfer-progress" for task in asyncio.all_tasks()))
        self.assertEqual(len(self.uploads), 4 if split else 1)

    async def test_saved_thumbnail_on_single_file(self):
        await self.check_uploads(False)

    async def test_fresh_thumbnail_on_every_part_except_manifest(self):
        await self.check_uploads(True)
