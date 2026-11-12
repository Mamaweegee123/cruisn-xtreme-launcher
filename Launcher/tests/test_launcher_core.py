import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher_core import GameConfig, ManagedGame, exact_external_pids, load_games


class LauncherCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rom = self.root / "game.z64"
        self.rom.write_bytes(b"read-only test rom")
        self.rom.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.errors = []

    def tearDown(self):
        self.temp.cleanup()

    def make_game(self, body: str) -> ManagedGame:
        executable = self.root / "mock_game"
        executable.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        executable.chmod(0o755)
        config = GameConfig(
            id="mock",
            display_name="Mock Game",
            executable_path=executable,
            rom_path=self.rom,
            working_directory=self.root,
            arguments=("{rom_path}",),
            log_path=self.root / "logs",
        )
        return ManagedGame(config, lambda _game_id: None, lambda game_id, msg: self.errors.append((game_id, msg)))

    def make_stubborn_game(self) -> ManagedGame:
        executable = self.root / "stubborn_game.py"
        executable.write_text(
            "#!/usr/bin/env python3\n"
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "while True: time.sleep(1)\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        config = GameConfig(
            id="stubborn",
            display_name="Stubborn Game",
            executable_path=executable,
            rom_path=self.rom,
            working_directory=self.root,
            arguments=(),
            log_path=self.root / "logs",
        )
        return ManagedGame(config, lambda _game_id: None, lambda game_id, msg: self.errors.append((game_id, msg)))

    def wait_stopped(self, game: ManagedGame, timeout=3):
        deadline = time.monotonic() + timeout
        while game.is_owned_running() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(game.is_owned_running())

    def wait_reaped(self, game: ManagedGame, timeout=3):
        deadline = time.monotonic() + timeout
        while game.process is not None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIsNone(game.process)

    def test_launch_captures_both_streams_and_blocks_duplicate(self):
        game = self.make_game('echo "out:$1"\necho "err" >&2\nsleep 30\n')
        log = game.launch()
        with self.assertRaises(RuntimeError):
            game.launch()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if "[stderr] err" in log.read_text(encoding="utf-8"):
                break
            time.sleep(0.02)
        self.assertTrue(game.stop())
        self.wait_stopped(game)
        self.wait_reaped(game)
        contents = log.read_text(encoding="utf-8")
        self.assertIn("[stdout] out:", contents)
        self.assertIn("[stderr] err", contents)
        self.assertIn("exit_code:", contents)
        self.assertIn(f"rom: {self.rom}", contents)

    def test_force_quit_owned_process(self):
        game = self.make_game("trap '' TERM\nsleep 30\n")
        game.launch()
        time.sleep(0.1)
        self.assertTrue(game.force_quit())
        self.wait_stopped(game)

    def test_stop_timeout_restores_force_quit_state(self):
        game = self.make_stubborn_game()
        log = game.launch()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and "[stdout] ready" not in log.read_text(encoding="utf-8"):
            time.sleep(0.02)
        self.assertIn("[stdout] ready", log.read_text(encoding="utf-8"))
        self.assertFalse(game.stop(timeout=0.05))
        self.assertTrue(game.is_owned_running())
        self.assertFalse(game.is_stopping())
        self.assertTrue(game.force_quit())
        self.wait_reaped(game)

    def test_missing_rom_has_clean_error(self):
        game = self.make_game("sleep 30\n")
        self.rom.unlink()
        with self.assertRaisesRegex(FileNotFoundError, "ROM missing"):
            game.launch()

    def test_natural_exit_is_waited_and_reaped(self):
        game = self.make_game("exit 7\n")
        game.launch()
        pid = game.process.pid
        self.wait_reaped(game)
        self.assertEqual(game.last_exit_code, 7)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_game_can_be_relaunched_after_a_clean_exit(self):
        game = self.make_game("echo launch-ok\nexit 0\n")
        game.launch()
        self.wait_reaped(game)
        first_log = game.latest_log
        self.assertEqual(game.last_exit_code, 0)
        game.launch()
        self.wait_reaped(game)
        self.assertNotEqual(game.latest_log, first_log)
        self.assertEqual(game.last_exit_code, 0)

    def test_advanced_arguments_remain_separate_argv_items(self):
        from dataclasses import replace
        game = self.make_game("exit 0\n")
        game.config = replace(game.config, extras={"advanced_arguments": "--window-title 'Race Test'"})
        self.assertEqual(game.config.command[-2:], ["--window-title", "Race Test"])

    def test_relative_process_requires_resolved_image_match(self):
        fake_ps = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="4321 ./cruisn_world_recomp /a/rom.z64\n"
        )
        target = Path("/repo/build/bin/cruisn_world_recomp")
        with patch("launcher_core.subprocess.run", return_value=fake_ps), patch(
            "launcher_core._actual_executable", return_value=str(target)
        ):
            self.assertEqual(exact_external_pids(target), [4321])

    def test_external_executable_path_with_spaces_is_matched_exactly(self):
        target = Path("/tmp/Mock Game Folder/game binary")
        fake_ps = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=f"4322 {target} '/tmp/My ROMs/game.z64'\n",
        )
        with patch("launcher_core.subprocess.run", return_value=fake_ps):
            self.assertEqual(exact_external_pids(target), [4322])

    def test_external_pid_refreshes_cannot_commit_out_of_order(self):
        game = self.make_game("exit 0\n")
        first_entered = threading.Event()
        second_entered = threading.Event()
        release_first = threading.Event()
        calls = 0
        calls_lock = threading.Lock()

        def controlled_scan(*_args):
            nonlocal calls
            with calls_lock:
                calls += 1
                call_number = calls
            if call_number == 1:
                first_entered.set()
                release_first.wait(timeout=2)
                return [101]
            second_entered.set()
            return []

        with patch("launcher_core.exact_external_pids", side_effect=controlled_scan):
            first = threading.Thread(target=game.refresh_external)
            second = threading.Thread(target=game.refresh_external)
            first.start()
            self.assertTrue(first_entered.wait(timeout=1))
            second.start()
            self.assertFalse(second_entered.wait(timeout=0.05))
            release_first.set()
            first.join(timeout=1)
            second.join(timeout=1)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(game.external_pids, [])

    def test_project_config_has_disabled_usa_card(self):
        config_path = Path(__file__).resolve().parents[1] / "games.json"
        games = {game.id: game for game in load_games(config_path)}
        self.assertEqual(set(games), {"cruisn_world", "cruisn_exotica", "cruisn_usa", "velocity"})
        self.assertFalse(games["cruisn_usa"].enabled)
        self.assertIsNone(games["cruisn_usa"].executable_path)
        self.assertIsNone(games["cruisn_usa"].rom_path)
        usa = ManagedGame(games["cruisn_usa"], lambda _game_id: None, lambda *_args: None)
        with self.assertRaisesRegex(RuntimeError, "coming soon"):
            usa.launch()

    def test_unsupported_rom_revision_is_rejected(self):
        from dataclasses import replace
        from launcher_core import sha256_file
        expected_file = self.root / "expected rom.z64"
        expected_file.write_bytes(b"right revision")
        wrong_file = self.root / "wrong revision.z64"
        wrong_file.write_bytes(b"wrong revision")
        executable = self.root / "mock_game"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        game = GameConfig(
            id="revision", display_name="Revision Game", executable_path=executable,
            rom_path=wrong_file, working_directory=self.root, arguments=(),
            log_path=self.root / "logs", extras={"expected_rom_sha256": sha256_file(expected_file)},
        )
        managed = ManagedGame(game, lambda *_: None, lambda *_: None)
        self.assertEqual(managed.state(refresh_external=False).status.value, "Unsupported ROM revision")
        with self.assertRaisesRegex(ValueError, "Unsupported ROM"):
            managed.launch()

    def test_dependency_failure_is_described_clearly(self):
        game = self.make_game("echo 'dyld: Library not loaded: missing.dylib' >&2\nexit 1\n")
        game.launch()
        self.wait_reaped(game)
        self.assertTrue(self.errors)
        self.assertIn("dependency may be missing", self.errors[-1][1])


if __name__ == "__main__":
    unittest.main()
