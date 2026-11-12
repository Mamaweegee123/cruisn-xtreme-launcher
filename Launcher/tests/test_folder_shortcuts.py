import stat
import tempfile
import unittest
from pathlib import Path

from launcher_core import GameConfig, ManagedGame
from launcher_shortcuts import (
    FolderShortcutError,
    configured_game_folder,
    configured_save_folder,
    open_configured_folder,
)


class FolderShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_config(self, *, project_path=None, save_folder=None):
        executable = self.root / "game"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(stat.S_IRWXU)
        rom = self.root / "game.z64"
        rom.write_bytes(b"fixture")
        return GameConfig(
            id="mock",
            display_name="Mock Game",
            executable_path=executable,
            rom_path=rom,
            working_directory=self.root,
            arguments=(),
            log_path=self.root / "logs",
            save_folder=save_folder,
            project_path=project_path,
            enabled=True,
        )

    def test_valid_configured_game_folder_opens(self):
        project = self.root / "project"
        project.mkdir()
        config = self.make_config(project_path=project)
        opened = []
        open_configured_folder(configured_game_folder(config), "Game folder", lambda path: opened.append(path) or True)
        self.assertEqual(opened, [project])

    def test_missing_game_folder_fails_readably(self):
        missing = self.root / "missing-project"
        config = self.make_config(project_path=missing)
        with self.assertRaisesRegex(FolderShortcutError, "Game folder does not exist"):
            open_configured_folder(configured_game_folder(config), "Game folder", lambda _path: True)

    def test_optional_save_folder_absent(self):
        self.assertIsNone(configured_save_folder(self.make_config()))

    def test_optional_save_folder_present(self):
        save_folder = self.root / "saves"
        save_folder.mkdir()
        config = self.make_config(save_folder=save_folder)
        self.assertEqual(configured_save_folder(config), save_folder)

    def test_invalid_save_folder_is_not_created_or_opened(self):
        save_folder = self.root / "missing-saves"
        config = self.make_config(save_folder=save_folder)
        opened = []
        with self.assertRaisesRegex(FolderShortcutError, "Save folder does not exist"):
            open_configured_folder(configured_save_folder(config), "Save folder", lambda path: opened.append(path) or True)
        self.assertFalse(save_folder.exists())
        self.assertEqual(opened, [])

    def test_folder_action_does_not_change_game_state(self):
        project = self.root / "project"
        project.mkdir()
        managed = ManagedGame(self.make_config(project_path=project), lambda _game_id: None, lambda *_args: None)
        before = managed.state(refresh_external=False)
        open_configured_folder(configured_game_folder(managed.config), "Game folder", lambda _path: True)
        after = managed.state(refresh_external=False)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
