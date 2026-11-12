import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import ArtworkPanel, GameTitleLabel, LauncherWindow
from launcher_core import GameStatus, ManagedGame, load_games, sha256_file

ROOT = Path(__file__).resolve().parents[1]


class LauncherGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.games = load_games(ROOT / "games.json")
        cls.by_id = {game.id: game for game in cls.games}

    def settings(self, path):
        return QSettings(str(path), QSettings.IniFormat)

    def make_window(self, settings_path):
        return LauncherWindow(self.settings(settings_path), data_directory=settings_path.parent / "app-data")

    def test_exact_four_primary_games_and_two_by_two_order(self):
        self.assertEqual([g.id for g in self.games], ["cruisn_usa", "cruisn_world", "cruisn_exotica", "velocity"])
        window = self.make_window(Path(tempfile.mkdtemp()) / "settings.ini")
        try:
            self.assertEqual(set(window.rows), {"cruisn_usa", "cruisn_world", "cruisn_exotica", "velocity"})
            self.assertFalse(hasattr(window, "portable_archive"))
            self.assertNotIn("cruisn_xtreme", window.rows)
            for index, game_id in enumerate(window.rows):
                item = window.card_grid.indexOf(window.rows[game_id])
                row, col, *_ = window.card_grid.getItemPosition(item)
                self.assertEqual((row, col), divmod(index, 2))
            self.assertEqual(window.windowTitle(), "Cruis'n Xtreme")
        finally:
            window.close()

    def test_exotica_and_velocity_are_disabled_even_if_build_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_executable = Path(temp) / "experimental build"
            fake_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_executable.chmod(0o755)
            for game_id in ("cruisn_exotica", "velocity"):
                game = self.by_id[game_id]
                self.assertFalse(game.enabled)
                from dataclasses import replace
                configured_prototype = replace(game, executable_path=fake_executable)
                managed = ManagedGame(configured_prototype, lambda *_: None, lambda *_: None)
                self.assertEqual(managed.state(refresh_external=False).status, GameStatus.COMING_SOON)
                self.assertFalse(managed.state(refresh_external=False).can_launch)
        self.assertIn("Not Yet Playable", self.by_id["cruisn_exotica"].extras["availability_note"])

    def test_usa_is_not_claimed_playable(self):
        game = self.by_id["cruisn_usa"]
        self.assertFalse(game.enabled)
        self.assertIsNone(game.executable_path)
        managed = ManagedGame(game, lambda *_: None, lambda *_: None)
        self.assertFalse(managed.state(refresh_external=False).can_launch)

    def test_world_is_only_enabled_native_game_and_has_expected_rom_revision(self):
        enabled = [g.id for g in self.games if g.enabled]
        self.assertEqual(enabled, ["cruisn_world"])
        self.assertEqual(self.by_id["cruisn_world"].extras["expected_rom_sha256"], "5320594232f0c492a672464832425351bd06497c95fb243745e2493bc5df9c2c")
        self.assertEqual(self.by_id["cruisn_world"].executable_path.name, "cruisn_world_recomp")
        managed_world = ManagedGame(self.by_id["cruisn_world"], lambda *_: None, lambda *_: None)
        self.assertEqual(managed_world.state(refresh_external=False).executable_ready, self.by_id["cruisn_world"].executable_path.is_file())
        self.assertIsNone(self.by_id["cruisn_world"].rom_path)

    def test_rom_picker_and_executable_picker_persist_paths_with_spaces_and_play(self):
        with tempfile.TemporaryDirectory(prefix="launcher settings ") as temp:
            root = Path(temp)
            rom = root / "Cruis'n World ROM.z64"
            rom.write_bytes(b"fixture rom for launcher test")
            executable = root / "fake game executable"
            executable.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            settings = self.settings(root / "settings.ini")
            window = LauncherWindow(settings, data_directory=root / "app-data")
            try:
                managed = window.manager.games["cruisn_world"]
                expected = sha256_file(rom)
                window._update_config("cruisn_world", extras={**managed.config.extras, "expected_rom_sha256": expected})
                window._update_config("cruisn_world", executable_path=None, rom_path=None, working_directory=None)
                with patch("app.QFileDialog.getOpenFileName", side_effect=[(str(rom), ""), (str(executable), "")]), patch("launcher_core.exact_external_pids", return_value=[]):
                    window.launch("cruisn_world")
                self.assertEqual(Path(settings.value("games/cruisn_world/rom")).resolve(), rom.resolve())
                self.assertEqual(Path(settings.value("games/cruisn_world/executable")).resolve(), executable.resolve())
                self.assertEqual(managed.config.working_directory, root.resolve())
                deadline = time.monotonic() + 3
                while managed.process is not None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertIsNone(managed.process)
                self.assertEqual(managed.last_exit_code, 0)
                self.assertIn(str(rom), managed.latest_log.read_text())
                self.assertIn(str(executable), managed.latest_log.read_text())
                restored = LauncherWindow(self.settings(root / "settings.ini"), data_directory=root / "app-data")
                try:
                    restored_game = restored.manager.games["cruisn_world"].config
                    self.assertEqual(restored_game.rom_path, rom.resolve())
                    self.assertEqual(restored_game.executable_path, executable.resolve())
                finally:
                    restored.close()
            finally:
                window.close()

    def test_unsupported_rom_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "wrong revision.z64"
            rom.write_bytes(b"wrong")
            game = self.by_id["cruisn_world"]
            from dataclasses import replace
            game = replace(game, rom_path=rom)
            managed = ManagedGame(game, lambda *_: None, lambda *_: None)
            self.assertEqual(managed.state(refresh_external=False).status, GameStatus.MISSING_BUILD if not game.executable_path.is_file() else GameStatus.UNSUPPORTED_ROM)
            if game.executable_path.is_file():
                with self.assertRaisesRegex(ValueError, "Unsupported ROM"):
                    managed.launch()

    def test_cards_have_one_primary_play_and_advanced_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            window = self.make_window(Path(temp) / "settings.ini")
            try:
                for game_id, card in window.rows.items():
                    self.assertEqual(card.launch_button.text(), "PLAY")
                    self.assertEqual(card.advanced_button.text(), "ADVANCED")
                    self.assertEqual(len(card.findChildren(type(card.launch_button))), 2)
                self.assertFalse(window.rows["cruisn_exotica"].launch_button.isEnabled())
                self.assertFalse(window.rows["velocity"].launch_button.isEnabled())
            finally:
                window.close()

    def test_velocity_and_exotica_artwork_load(self):
        for game_id in ("cruisn_exotica", "velocity"):
            game = self.by_id[game_id]
            title = GameTitleLabel(game)
            panel = ArtworkPanel(game)
            if not title.has_logo:
                self.assertEqual(title.text(), game.display_name)
            if not panel.has_artwork:
                panel.resize(240, 80)
                self.assertFalse(panel.grab().isNull())


if __name__ == "__main__":
    unittest.main()
