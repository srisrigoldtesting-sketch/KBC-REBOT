import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.config import Settings, SetupError
from app.database import Database
from app.features import ADMIN_COMMANDS, BotControl, broadcast_message, register_features
from app.plans import TRIAL_SECONDS, plan_state, require_access, render_caption, validate_caption
import test_free_mode


class PlanTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database("", "test", Path(self.temp.name))

    async def asyncTearDown(self):
        await self.db.close()
        self.temp.cleanup()

    async def test_trial_does_not_restart_on_repeat_use_or_reopen(self):
        with patch("app.database.time.time", return_value=1000):
            first = await self.db.get_profile(42)
        await self.db.close()
        self.db = Database("", "test", Path(self.temp.name))
        with patch("app.database.time.time", return_value=99999):
            again = await self.db.get_profile(42)
        self.assertEqual(first, again)
        self.assertTrue(plan_state(again, 1000 + TRIAL_SECONDS - 1)[1])
        self.assertFalse(plan_state(again, 1000 + TRIAL_SECONDS)[1])

    async def test_capacity_expiry_disable_and_admin_bypass(self):
        with patch("app.database.time.time", return_value=1000):
            await self.db.get_profile(42)
        with patch("app.plans.time.time", return_value=1001):
            await require_access(self.db, 42, 99, 2000 * 1024**2)
            with self.assertRaisesRegex(SetupError, "2000 MiB"):
                await require_access(self.db, 42, 99, 2000 * 1024**2 + 1)
        with patch("app.plans.time.time", return_value=1000 + TRIAL_SECONDS):
            with self.assertRaises(SetupError):
                await require_access(self.db, 42, 99)
            await self.db.update_profile(42, premium_until=1000 + TRIAL_SECONDS + 60, capacity_mib=4000)
            await require_access(self.db, 42, 99, 4000 * 1024**2)
            await self.db.update_profile(42, capacity_mib=0)
            with self.assertRaises(SetupError):
                await require_access(self.db, 42, 99)
            await require_access(self.db, 42, 42, 4000 * 1024**2)

    async def test_caption_and_capacity_updates_do_not_reset_trial(self):
        initial = await self.db.get_profile(1)
        await self.db.update_profile(1, caption="Hello {filename}", capacity_mib=500)
        await self.db.get_profile(2)
        self.assertIsNone((await self.db.get_profile(2))["caption"])
        self.assertEqual((await self.db.get_profile(1))["trial_started"], initial["trial_started"])
        self.assertEqual((await self.db.get_profile(1))["caption"], "Hello {filename}")
        with self.assertRaises(ValueError):
            await self.db.update_profile(1, trial_started=0)

    async def test_user_id_paging_is_ordered_unique_and_bounded(self):
        self.db.local.executemany("INSERT INTO users VALUES (?,?)", [(n, "now") for n in range(1, 1002)])
        self.db.local.commit()
        ids = [user async for user in self.db.iter_user_ids()]
        self.assertEqual(ids, list(range(1, 1002)))
        self.assertTrue(await self.db.has_user(1001))
        self.assertFalse(await self.db.has_user(1002))

    def test_captions_are_literal_and_bound_unicode_length(self):
        self.assertEqual(render_caption("{filename} {filesize}", "New.pdf", 1024**2), "New.pdf 1.0 MiB")
        self.assertEqual(render_caption("{filename.__class__}", "x", 1), "{filename.__class__}")
        with self.assertRaises(SetupError):
            validate_caption("😀" * 351)
        text = render_caption("{filename}" * 60, "😀" * 100, 1)
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 900)


class FeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database("", "test", Path(self.temp.name))
        self.settings = Settings.from_values(test_free_mode.free_values())
        self.handlers = {}
        def register(_):
            def attach(function):
                self.handlers[function.__name__] = function
                return function
            return attach
        self.bot = SimpleNamespace(on_message=register, send_message=AsyncMock(), copy_message=AsyncMock())
        self.worker = SimpleNamespace(cancel=AsyncMock(), stopping=False, upload_limit=2000 * 1024**2)
        self.control = BotControl()
        register_features(self.bot, self.db, self.worker, self.settings, self.control)
        await self.db.get_profile(42)

    async def asyncTearDown(self):
        await self.control.close()
        await self.db.close()
        self.temp.cleanup()

    def message(self, text, admin=True):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=self.settings.admin_id if admin else 42),
                               reply_to_message=None, reply_text=AsyncMock(), reply_document=AsyncMock())

    async def admin(self, text):
        message = self.message(text)
        await self.handlers["admin_features"](self.bot, message)
        return message

    async def test_every_admin_command_denies_non_admin_even_without_dispatch_filters(self):
        before = await self.db.get_profile(42)
        for command in ADMIN_COMMANDS:
            message = self.message(f"/{command} 42 30 4000", admin=False)
            await self.handlers["admin_features"](self.bot, message)
            message.reply_text.assert_not_awaited()
        self.assertEqual(before, await self.db.get_profile(42))
        self.assertFalse(self.control.restart.is_set())
        self.bot.copy_message.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_premium_renewal_downgrade_reset_preserves_expiry_and_trial(self):
        before = await self.db.get_profile(42)
        with patch("app.features.time.time", return_value=2_000_000_000):
            await asyncio.gather(self.admin("/addpremium 42 30 4000"), self.admin("/addpremium 42 7 3000"))
        profile = await self.db.get_profile(42)
        self.assertEqual(profile["premium_until"], 2_000_000_000 + 37 * 86400)
        await self.admin("/ceasepower 42 500")
        self.assertEqual((await self.db.get_profile(42))["capacity_mib"], 500)
        await self.admin("/ceasepower 42")
        self.assertEqual((await self.db.get_profile(42))["capacity_mib"], 0)
        await self.admin("/resetpower 42")
        reset = await self.db.get_profile(42)
        self.assertEqual(reset["capacity_mib"], 2000)
        self.assertEqual(reset["premium_until"], profile["premium_until"])
        self.assertEqual(reset["trial_started"], before["trial_started"])
        self.assertEqual(self.worker.cancel.await_count, 3)

    async def test_invalid_plan_arguments_and_unknown_users_cannot_modify_access(self):
        before = await self.db.get_profile(42)
        for text in ("/addpremium 42 0", "/addpremium 42 30 4001", "/ceasepower 42 3000", "/addpremium 999 30", "/resetpower 42 extra"):
            await self.admin(text)
        self.assertEqual(before, await self.db.get_profile(42))
        self.assertFalse(await self.db.has_user(999))

    async def test_warn_targets_only_named_registered_user(self):
        await self.admin("/warn 42 Please check your file.")
        self.bot.send_message.assert_awaited_once_with(42, "Please check your file.")

    async def test_allids_exports_registered_ids(self):
        observed = []
        message = self.message("/allids")
        async def capture(file, **kwargs):
            observed.append(file.read())
        message.reply_document.side_effect = capture
        await self.handlers["admin_features"](self.bot, message)
        self.assertEqual(observed, [b"42\n"])

    async def test_expired_user_can_read_delete_but_not_set_caption(self):
        self.db.local.execute("UPDATE profiles SET trial_started=0 WHERE id=42")
        self.db.local.commit()
        await self.db.update_profile(42, caption="saved")
        message = self.message("/set_caption changed", admin=False)
        await self.handlers["user_features"](self.bot, message)
        self.assertEqual((await self.db.get_profile(42))["caption"], "saved")
        message.text = "/del_caption"
        await self.handlers["user_features"](self.bot, message)
        self.assertIsNone((await self.db.get_profile(42))["caption"])
        message.text = "/upgrade"
        await self.handlers["user_features"](self.bot, message)
        self.assertIn("6 hours", message.reply_text.await_args.args[0])

    async def test_restart_signals_shutdown_and_cancels_broadcast(self):
        entered = asyncio.Event()
        async def running():
            entered.set()
            await asyncio.Event().wait()
        self.control.broadcast_task = asyncio.create_task(running())
        task = self.control.broadcast_task
        await entered.wait()
        await self.admin("/restart")
        self.assertTrue(self.worker.stopping)
        self.assertTrue(self.control.restart.is_set())
        await self.control.close()
        self.assertTrue(task.cancelled())

    async def test_broadcast_continues_after_blocked_user_and_reports_counts(self):
        await self.db.get_profile(43)
        self.bot.copy_message.side_effect = [RuntimeError("blocked"), SimpleNamespace(id=2)]
        source = SimpleNamespace(chat=SimpleNamespace(id=99), id=100)
        await broadcast_message(self.bot, self.db, source, self.settings.admin_id, pause=0)
        self.assertEqual([call.args[0] for call in self.bot.copy_message.await_args_list], [42, 43])
        self.assertIn("Sent: 1; failed/blocked: 1", self.bot.send_message.await_args.args[1])


class GatedWorkerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_free_mode.FreeWorkerTests.asyncSetUp
    asyncTearDown = test_free_mode.FreeWorkerTests.asyncTearDown
    job = test_free_mode.FreeWorkerTests.job
    drain = test_free_mode.FreeWorkerTests.drain

    async def test_expired_profile_denied_at_submit(self):
        self.db.get_profile.return_value = {"trial_started": 0, "premium_until": 0, "capacity_mib": 2000, "caption": None}
        with self.assertRaises(SetupError):
            await self.worker.submit(self.job())
        self.assertFalse(self.worker.pending)

    async def test_expiry_while_queued_blocks_download(self):
        await self.worker.submit(self.job())
        self.db.get_profile.return_value = {"trial_started": 0, "premium_until": 0, "capacity_mib": 2000, "caption": None}
        with self.assertLogs("app.worker", level="WARNING"):
            await self.drain()
        self.bot.download_media.assert_not_awaited()

    async def test_caption_applied_and_part_instructions_fit_telegram(self):
        self.worker.upload_limit = 5
        self.db.get_profile.return_value = {"trial_started": 4102444800, "premium_until": 4102444800, "capacity_mib": 4000, "caption": "{filename}" * 60}
        await self.worker.submit(self.job(split=True))
        await self.drain()
        for call in self.bot.send_document.await_args_list:
            caption = call.kwargs["caption"]
            self.assertLessEqual(len(caption.encode("utf-16-le")) // 2, 1024)
            if call.kwargs["file_name"].endswith(".part001"):
                self.assertIn("Part 1 of", caption)
                self.assertIn("New.bin.part001", caption)


class RestartLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_closes_old_worker_clients_and_db_before_reconnecting(self):
        from app.main import serve
        settings = Settings.from_values(test_free_mode.free_values())
        ready = asyncio.Event()
        events = []
        clients = []
        databases = []
        workers = []
        def build(_):
            number = len(clients) + 1
            if number == 2:
                self.assertEqual(events, ["worker-stop", "disconnect", "disconnect", "db-close"])
            bot = SimpleNamespace(me=SimpleNamespace(username="test_bot"))
            clients.append(bot)
            return bot, None
        def database(*args):
            db = SimpleNamespace(ping=AsyncMock(), recover=AsyncMock(), close=AsyncMock(side_effect=lambda: events.append("db-close")))
            databases.append(db)
            return db
        def worker(*args):
            instance = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(side_effect=lambda: events.append("worker-stop")), upload_limit=2000 * 1024**2)
            workers.append(instance)
            return instance
        def handlers(*args):
            control = BotControl()
            if len(clients) == 1:
                control.restart.set()
            else:
                ready.set()
            return control
        with tempfile.TemporaryDirectory() as folder:
            from dataclasses import replace
            settings = replace(settings, work_dir=Path(folder))
            with patch("app.clients.build_clients", side_effect=build), patch("app.clients.connect_client", new=AsyncMock()), \
                 patch("app.clients.verify_telegram", new=AsyncMock()), \
                 patch("app.clients.disconnect_client", new=AsyncMock(side_effect=lambda client: events.append("disconnect"))), \
                 patch("app.database.Database", side_effect=database), patch("app.worker.RenameWorker", side_effect=worker), \
                 patch("app.handlers.register_handlers", side_effect=handlers), patch("app.main.Settings.load", return_value=settings), \
                 patch("builtins.print"):
                task = asyncio.create_task(serve(settings))
                try:
                    await asyncio.wait_for(ready.wait(), 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(len(clients), 2)
            for item in workers:
                item.stop.assert_awaited_once()
            for db in databases:
                db.close.assert_awaited_once()
