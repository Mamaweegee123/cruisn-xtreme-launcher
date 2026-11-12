import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QPushButton

from app import ArtworkPanel, GameCard
from launcher_core import GameConfig


class ArtworkPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_config(self, artwork):
        return GameConfig(
            id="mock",
            display_name="Cruis'n Mock",
            executable_path=None,
            rom_path=Path("/missing/game.z64"),
            working_directory=Path("/missing"),
            arguments=(),
            log_path=Path("/missing/logs"),
            enabled=False,
            extras={"artwork": artwork},
        )

    def test_missing_artwork_fallback_renders(self):
        panel = ArtworkPanel(self.make_config("assets/does-not-exist.png"))
        self.assertFalse(panel.has_artwork)
        panel.resize(280, 80)
        image = QImage(panel.size(), QImage.Format_ARGB32)
        image.fill(0)
        panel.render(image)
        self.assertFalse(image.isNull())

    def test_configured_artwork_loads(self):
        panel = ArtworkPanel(self.make_config("assets/world/card-key-art.png"))
        self.assertTrue(panel.muted)
        if not panel.has_artwork:
            panel.resize(280, 80)
            image = QImage(panel.size(), QImage.Format_ARGB32)
            panel.render(image)
            self.assertFalse(image.isNull())

    def test_transparent_png_preserves_alpha_channel(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "transparent.png"
            image = QImage(24, 16, QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            image.setPixelColor(8, 8, QColor(40, 180, 220, 255))
            self.assertTrue(image.save(str(path)))
            panel = ArtworkPanel(self.make_config(str(path)))
            self.assertTrue(panel.has_artwork)
            self.assertTrue(panel.pixmap.hasAlphaChannel())

    def test_folder_shortcuts_are_not_part_of_primary_card_flow(self):
        card = GameCard(self.make_config(None), object())
        self.assertIsNone(card.save_folder_button)
        config = replace(self.make_config(None), save_folder=Path("/configured/saves"))
        configured_card = GameCard(config, object())
        self.assertIsNone(configured_card.save_folder_button)
        self.assertEqual([button.text() for button in configured_card.findChildren(QPushButton)], ["PLAY", "ADVANCED"])


if __name__ == "__main__":
    unittest.main()
