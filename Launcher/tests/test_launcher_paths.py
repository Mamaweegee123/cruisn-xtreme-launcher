import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher_core import load_games
from launcher_paths import artwork_asset_path, bundled_resource_root, games_config_path, launcher_workspace, logo_asset_path


class LauncherPathTests(unittest.TestCase):
    def test_development_paths_are_source_relative_not_cwd_or_home_hardcoded(self):
        expected = Path(__file__).resolve().parents[1]
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(launcher_workspace(), expected)
            self.assertEqual(games_config_path(), expected / "games.json")
            self.assertEqual(artwork_asset_path("assets/world/world.png"), expected / "assets/world/world.png")
            self.assertEqual(logo_asset_path("assets/world/logo.png"), expected / "assets/world/logo.png")

    def test_frozen_config_and_assets_use_packaged_resources(self):
        resource_root = Path(__file__).resolve().parents[1]
        executable = Path("/Applications/Cruis'n Xtreme.app/Contents/MacOS/Cruis'n Xtreme")
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(resource_root), create=True), patch.object(sys, "executable", str(executable)):
            self.assertEqual(launcher_workspace(), executable.parent)
            self.assertEqual(bundled_resource_root(), resource_root)
            self.assertEqual(games_config_path(), resource_root / "games.json")
            games = {game.id: game for game in load_games(games_config_path())}
            self.assertEqual(games["cruisn_world"].log_path, resource_root / "logs/cruisn_world")
            self.assertEqual(artwork_asset_path("assets/usa/usa.png"), resource_root / "assets/usa/usa.png")

    def test_missing_artwork_configuration_is_optional(self):
        self.assertIsNone(artwork_asset_path(None))


if __name__ == "__main__":
    unittest.main()
