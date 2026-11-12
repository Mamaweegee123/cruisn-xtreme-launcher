import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app import GameTitleLabel
from launcher_core import GameConfig, GameStatus, ManagedGame, load_games


class LogoPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_config(self, *, enabled=True, logo=None):
        return GameConfig(
            id="mock",
            display_name="Cruis'n Mock",
            executable_path=None,
            rom_path=Path("/missing/game.z64"),
            working_directory=Path("/missing"),
            arguments=(),
            log_path=Path("/missing/logs"),
            enabled=enabled,
            extras={"logo": logo},
        )

    def make_transparent_logo(self, directory: str) -> Path:
        path = Path(directory) / "logo.png"
        image = QImage(240, 72, QImage.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        for x in range(24, 216):
            for y in range(22, 50):
                image.setPixelColor(x, y, QColor(40, 190, 225, 255))
        for x in range(108, 132):
            for y in range(30, 42):
                image.setPixelColor(x, y, QColor(0, 0, 0, 0))
        self.assertTrue(image.save(str(path)))
        return path

    def test_missing_logo_falls_back_to_single_text_title(self):
        title = GameTitleLabel(self.make_config(logo="assets/missing-logo.png"))
        self.assertFalse(title.has_logo)
        self.assertEqual(title.text(), "Cruis'n Mock")

    def test_transparent_logo_preserves_alpha_and_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_transparent_logo(directory)
            title = GameTitleLabel(self.make_config(logo=str(path)))
            title.resize(330, 102)
            title._update_logo_pixmap()
            displayed = title.pixmap()
            self.assertTrue(title.has_logo)
            self.assertTrue(title.source_pixmap.hasAlphaChannel())
            self.assertTrue(displayed.hasAlphaChannel())
            self.assertAlmostEqual(
                displayed.width() / displayed.height(),
                title.source_pixmap.width() / title.source_pixmap.height(),
                delta=0.15,
            )
            self.assertLessEqual(displayed.width(), 300)
            self.assertLessEqual(displayed.height(), 96)

    def test_logo_does_not_change_game_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_transparent_logo(directory)
            config = self.make_config(enabled=False, logo=str(path))
            managed = ManagedGame(config, lambda _game_id: None, lambda *_args: None)
            before = managed.state(refresh_external=False)
            title = GameTitleLabel(config)
            after = managed.state(refresh_external=False)
            self.assertTrue(title.has_logo)
            self.assertTrue(title.muted)
            self.assertEqual(after, before)
            self.assertEqual(after.status, GameStatus.COMING_SOON)

    def test_configured_usa_remains_disabled_with_logo_available(self):
        config_path = Path(__file__).resolve().parents[1] / "games.json"
        usa = next(game for game in load_games(config_path) if game.id == "cruisn_usa")
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_transparent_logo(directory)
            config_with_logo = replace(usa, extras={**usa.extras, "logo": str(path)})
            title = GameTitleLabel(config_with_logo)
            state = ManagedGame(config_with_logo, lambda _game_id: None, lambda *_args: None).state(False)
        self.assertTrue(title.has_logo)
        self.assertTrue(title.muted)
        self.assertFalse(config_with_logo.enabled)
        self.assertEqual(state.status, GameStatus.COMING_SOON)
        self.assertFalse(state.can_launch)


if __name__ == "__main__":
    unittest.main()
