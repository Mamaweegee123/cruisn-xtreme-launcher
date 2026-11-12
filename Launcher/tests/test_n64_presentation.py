import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame

from app import LauncherWindow


class LauncherPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.external_patch = patch("launcher_core.exact_external_pids", return_value=[])
        self.external_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.window = LauncherWindow(
            QSettings(str(Path(self.temp.name) / "prefs.ini"), QSettings.IniFormat),
            data_directory=Path(self.temp.name) / "app-data",
        )
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.external_patch.stop()
        self.temp.cleanup()

    def test_exact_four_card_positions_and_no_archive_row(self):
        expected = [("cruisn_usa", 0, 0), ("cruisn_world", 0, 1), ("cruisn_exotica", 1, 0), ("velocity", 1, 1)]
        self.assertFalse(hasattr(self.window, "portable_archive"))
        for game_id, row, col in expected:
            index = self.window.card_grid.indexOf(self.window.rows[game_id])
            actual_row, actual_col, *_ = self.window.card_grid.getItemPosition(index)
            self.assertEqual((actual_row, actual_col), (row, col))

    def test_assets_and_card_trays_remain_consistent(self):
        for card in self.window.rows.values():
            self.assertEqual(len(card.findChildren(QFrame, "controlTray")), 1)
            self.assertEqual(card.launch_button.text(), "PLAY")
            self.assertEqual(card.advanced_button.text(), "ADVANCED")
        velocity = self.window.rows["velocity"]
        if velocity.artwork.has_artwork:
            self.assertTrue(velocity.title.has_logo)
        else:
            self.assertEqual(velocity.title.text(), "Velocity")
            self.assertFalse(velocity.title.has_logo)

    def test_only_world_is_launch_enabled(self):
        self.assertTrue(self.window.rows["cruisn_world"].launch_button.isEnabled())
        for game_id in ("cruisn_usa", "cruisn_exotica", "velocity"):
            self.assertFalse(self.window.rows[game_id].launch_button.isEnabled())

    def test_hover_state_does_not_change_availability(self):
        card = self.window.rows["cruisn_exotica"]
        before = self.window.manager.games["cruisn_exotica"].state(refresh_external=False)
        QApplication.sendEvent(card, QEvent(QEvent.Enter))
        QTest.qWait(190)
        after = self.window.manager.games["cruisn_exotica"].state(refresh_external=False)
        self.assertEqual(before, after)
        self.assertFalse(after.can_launch)

    def test_layout_has_no_secondary_handheld_shelf(self):
        self.assertEqual(self.window.card_grid.rowCount(), 2)
        self.assertIsNone(self.window.findChild(QFrame, "portableShelf"))
        self.assertNotIn("Handheld Archive", self.window.windowTitle())


if __name__ == "__main__":
    unittest.main()
