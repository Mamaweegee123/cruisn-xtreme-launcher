import os
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from launcher_core import GameConfig, GameStatus, ManagedGame


class StateMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_temp = tempfile.TemporaryDirectory()
        cls.external_fixture = Path(cls.build_temp.name) / "external_fixture"
        source = Path(__file__).resolve().parent / "fixtures" / "external_fixture.c"
        subprocess.run(["cc", str(source), "-o", str(cls.external_fixture)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executable = self.root / "fixture_game.sh"
        self.rom = self.root / "fixture.z64"
        self.rom.write_bytes(b"fixture rom")
        self._write_graceful_executable()
        self.errors = []
        self.states = []
        self.game = self._make_game(self.executable)

    def tearDown(self):
        if self.game.is_owned_running():
            self.game.force_quit()
        self._wait_reaped(self.game)
        self.temp.cleanup()

    def _write_graceful_executable(self):
        self.executable.write_text(
            "#!/bin/sh\n"
            "trap 'sleep 0.25; exit 0' TERM INT\n"
            "printf '%s\\n' ready\n"
            "while :; do sleep 1; done\n",
            encoding="utf-8",
        )
        self.executable.chmod(0o755)

    def _make_game(self, executable: Path, *, enabled=True, arguments=("{rom_path}",)):
        config = GameConfig(
            id="fixture",
            display_name="Fixture",
            executable_path=executable,
            rom_path=self.rom,
            working_directory=self.root,
            arguments=arguments,
            log_path=self.root / "logs",
            enabled=enabled,
        )
        return ManagedGame(config, self.states.append, lambda game_id, message: self.errors.append((game_id, message)))

    def _wait_for_log(self, game: ManagedGame, text="[stdout] ready", timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if game.latest_log and text in game.latest_log.read_text(encoding="utf-8"):
                return
            time.sleep(0.01)
        self.fail(f"did not find {text!r} in fixture log")

    def _wait_reaped(self, game: ManagedGame, timeout=3):
        deadline = time.monotonic() + timeout
        while game.process is not None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNone(game.process)

    def test_ready_running_stop_requested_clean_exit_ready(self):
        self.assertEqual(self.game.state().status, GameStatus.READY)
        self.game.launch()
        self._wait_for_log(self.game)
        running = self.game.state(refresh_external=False)
        self.assertEqual(running.status, GameStatus.RUNNING)
        self.assertIsNotNone(running.owned_pid)
        self.assertFalse(running.can_launch)

        self.assertTrue(self.game.request_stop())
        requested = self.game.state(refresh_external=False)
        self.assertEqual(requested.status, GameStatus.STOP_REQUESTED)
        self.assertEqual(requested.owned_pid, running.owned_pid)
        self.assertFalse(requested.can_launch)

        stop_thread = threading.Thread(target=lambda: self.game.stop(timeout=2))
        stop_thread.start()
        deadline = time.monotonic() + 1
        observed = None
        while time.monotonic() < deadline:
            observed = self.game.state(refresh_external=False)
            if observed.status is GameStatus.STOP_REQUESTED:
                break
            time.sleep(0.01)
        self.assertEqual(observed.status, GameStatus.STOP_REQUESTED)
        self.assertEqual(observed.owned_pid, running.owned_pid)
        stop_thread.join(timeout=3)
        self.assertFalse(stop_thread.is_alive())
        self._wait_reaped(self.game)
        ready = self.game.state()
        self.assertEqual(ready.status, GameStatus.READY)
        self.assertIsNone(ready.owned_pid)
        self.assertEqual(ready.last_exit_code, 0)

    def test_sigterm_timeout_remains_running_and_force_quit_is_available(self):
        stubborn = self.root / "stubborn.py"
        stubborn.write_text(
            "#!/usr/bin/env python3\n"
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "while True: time.sleep(1)\n",
            encoding="utf-8",
        )
        stubborn.chmod(0o755)
        self.game = self._make_game(stubborn, arguments=())
        self.game.launch()
        self._wait_for_log(self.game)
        pid = self.game.state(refresh_external=False).owned_pid
        self.assertFalse(self.game.stop(timeout=0.05))
        timed_out = self.game.state(refresh_external=False)
        self.assertEqual(timed_out.status, GameStatus.RUNNING)
        self.assertEqual(timed_out.owned_pid, pid)
        self.assertTrue(timed_out.can_force_quit)
        self.assertFalse(timed_out.can_launch)
        self.assertTrue(self.game.force_quit())
        self._wait_reaped(self.game)
        finished = self.game.state()
        self.assertEqual(finished.status, GameStatus.READY)
        self.assertIsNone(finished.owned_pid)
        self.assertEqual(finished.last_exit_code, -signal.SIGKILL)

    def test_rom_presence_transitions_both_directions(self):
        self.assertEqual(self.game.state().status, GameStatus.READY)
        self.rom.unlink()
        self.assertEqual(self.game.state().status, GameStatus.MISSING_ROM)
        self.assertFalse(self.game.state().can_launch)
        self.rom.write_bytes(b"restored fixture rom")
        self.assertEqual(self.game.state().status, GameStatus.READY)

    def test_build_presence_transitions_both_directions(self):
        self.assertEqual(self.game.state().status, GameStatus.READY)
        self.executable.unlink()
        self.assertEqual(self.game.state().status, GameStatus.MISSING_BUILD)
        self.assertFalse(self.game.state().can_launch)
        self._write_graceful_executable()
        self.assertEqual(self.game.state().status, GameStatus.READY)

    def test_coming_soon_is_never_launchable(self):
        self.game = self._make_game(self.executable, enabled=False)
        state = self.game.state()
        self.assertEqual(state.status, GameStatus.COMING_SOON)
        self.assertFalse(state.can_launch)
        self.rom.unlink()
        self.executable.unlink()
        self.assertEqual(self.game.state().status, GameStatus.COMING_SOON)
        self._write_graceful_executable()
        self.rom.write_bytes(b"restored")
        self.assertEqual(self.game.state().status, GameStatus.COMING_SOON)
        with self.assertRaisesRegex(RuntimeError, "coming soon"):
            self.game.launch()

    def test_external_process_appears_and_disappears_without_touching_history(self):
        self.game = self._make_game(self.external_fixture, arguments=())
        owned_timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
        self.game.last_run_at = owned_timestamp
        self.game.last_exit_code = 23
        external = subprocess.Popen([str(self.external_fixture)], start_new_session=True)
        try:
            deadline = time.monotonic() + 2
            detected = None
            while time.monotonic() < deadline:
                detected = self.game.state()
                if external.pid in detected.external_pids:
                    break
                time.sleep(0.02)
            self.assertEqual(detected.status, GameStatus.RUNNING_EXTERNALLY)
            self.assertEqual(detected.external_pids, (external.pid,))
            self.assertFalse(detected.can_launch)
            self.assertEqual(detected.last_run_at, owned_timestamp)
            self.assertEqual(detected.last_exit_code, 23)
        finally:
            os.killpg(os.getpgid(external.pid), signal.SIGTERM)
            external.wait(timeout=2)

        after = self.game.state()
        self.assertEqual(after.status, GameStatus.READY)
        self.assertEqual(after.external_pids, ())
        self.assertEqual(self.game.external_pids, [])
        self.assertEqual(after.last_run_at, owned_timestamp)
        self.assertEqual(after.last_exit_code, 23)
        with self.assertRaises(ProcessLookupError):
            os.kill(external.pid, 0)

    def test_natural_owned_exit_cannot_leave_running_or_stale_pid(self):
        self.executable.write_text("#!/bin/sh\nexit 6\n", encoding="utf-8")
        self.executable.chmod(0o755)
        self.game.launch()
        pid = self.game.process.pid
        self._wait_reaped(self.game)
        state = self.game.state()
        self.assertEqual(state.status, GameStatus.READY)
        self.assertIsNone(state.owned_pid)
        self.assertEqual(state.last_exit_code, 6)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
