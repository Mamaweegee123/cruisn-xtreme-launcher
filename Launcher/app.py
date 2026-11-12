#!/usr/bin/env python3
from __future__ import annotations

import sys
import threading
import shlex
import os
from dataclasses import replace
from pathlib import Path

try:
    from PySide6.QtCore import QEvent, QEasingCurve, QObject, QRectF, QSize, QTimer, QUrl, QVariantAnimation, Signal, Slot, Qt, QSettings, QStandardPaths
    from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion
    from PySide6.QtWidgets import (
        QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
        QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
        QSizePolicy, QStatusBar, QVBoxLayout, QWidget,
    )
except ImportError:
    print("PySide6 is required. Run ./setup.sh in the Launcher directory first.", file=sys.stderr)
    raise SystemExit(1)

from launcher_core import GameConfig, GameStatus, ProcessManager, load_games, sha256_file
from launcher_paths import artwork_asset_path, games_config_path, launcher_workspace, logo_asset_path
from launcher_shortcuts import (
    FolderShortcutError,
    configured_game_folder,
    configured_save_folder,
    open_configured_folder,
)


BASE_DIR = launcher_workspace()
VERSION = "EXPERIMENTAL"
PALETTE = {
    "background": "#0a1020",
    "shell": "#18243a",
    "card": "#253149",
    "world": "#26a8d1",
    "world_dark": "#176f91",
    "exotica": "#e05d78",
    "exotica_dark": "#9d344f",
    "usa": "#77828f",
    "usa_dark": "#4c5661",
    "velocity": "#e6b94f",
    "velocity_dark": "#94702b",
}

EXHIBIT_LABELS = {
    "cruisn_usa": "1994  •  ARCADE / NINTENDO 64",
    "cruisn_world": "1996  •  ARCADE / NINTENDO 64",
    "cruisn_exotica": "1999  •  ARCADE / NINTENDO 64",
    "velocity": "GAME BOY ADVANCE  •  EXPERIMENTAL",
}


class Bridge(QObject):
    state_changed = Signal(str)
    error = Signal(str, str)


class CheckerStrip(QWidget):
    """Small programmatic checker accent; no image asset or platform mark."""

    def __init__(self):
        super().__init__()
        self.setObjectName("checkerStrip")
        self.setMinimumWidth(130)
        self.setMaximumWidth(220)
        self.setFixedHeight(34)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        cell = 13
        colors = (QColor("#314866"), QColor("#1b2c48"))
        for row in range(3):
            for column in range((self.width() // cell) + 2):
                painter.fillRect(column * cell, row * cell, cell, cell, colors[(row + column) % 2])
        fade = QLinearGradient(self.rect().topLeft(), self.rect().topRight())
        fade.setColorAt(0.0, QColor(24, 36, 58, 245))
        fade.setColorAt(0.55, QColor(24, 36, 58, 35))
        fade.setColorAt(1.0, QColor(24, 36, 58, 120))
        painter.fillRect(self.rect(), fade)


class ArtworkPanel(QWidget):
    """Load optional key art and retain the standalone fallback renderer."""

    def __init__(self, game: GameConfig):
        super().__init__()
        self.setObjectName("artworkPanel")
        artwork_value = game.extras.get("artwork")
        self.artwork_path = artwork_asset_path(artwork_value if isinstance(artwork_value, str) else None)
        self.pixmap = QPixmap(str(self.artwork_path)) if self.artwork_path is not None else QPixmap()
        self.has_artwork = not self.pixmap.isNull()
        self.muted = not game.enabled
        self.setProperty("hasArtwork", self.has_artwork)
        self.setProperty("muted", self.muted)
        self.setMinimumHeight(62)
        self.setMaximumHeight(124)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if self.has_artwork:
            self.setToolTip(f"Artwork: {self.artwork_path}")
        else:
            self.setToolTip("Optional artwork is unavailable; using the built-in fallback.")

    def sizeHint(self) -> QSize:
        return QSize(280, 112)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        frame = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(frame, QColor("#171a1e"))

        if self.has_artwork:
            scaled = self.pixmap.scaled(frame.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = frame.x() + (frame.width() - scaled.width()) // 2
            y = frame.y() + (frame.height() - scaled.height()) // 2
            painter.setOpacity(0.48 if self.muted else 0.86)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)
        else:
            painter.setPen(QPen(QColor("#2b3037"), 1))
            for x in range(-frame.height(), frame.width(), 18):
                painter.drawLine(x, frame.bottom(), x + frame.height(), frame.top())

        shade = QLinearGradient(frame.topLeft(), frame.bottomRight())
        shade.setColorAt(0.0, QColor(5, 7, 9, 35 if self.has_artwork else 90))
        shade.setColorAt(0.55, QColor(5, 7, 9, 15 if self.has_artwork else 65))
        shade.setColorAt(1.0, QColor(5, 7, 9, 145))
        painter.fillRect(frame, shade)
        if self.muted:
            painter.fillRect(frame, QColor(30, 34, 39, 112))

        if self.muted:
            badge_font = QFont("DIN Alternate")
            badge_font.setPixelSize(9)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(QColor("#a2a8ad"))
            painter.drawText(frame.adjusted(8, 7, -9, -8), Qt.AlignRight | Qt.AlignTop, "COMING SOON")

        if not self.has_artwork:
            fallback_font = QFont("DIN Alternate")
            fallback_font.setPixelSize(9)
            fallback_font.setBold(True)
            painter.setFont(fallback_font)
            painter.setPen(QColor("#79869a"))
            painter.drawText(frame.adjusted(10, 10, -10, -10), Qt.AlignCenter, "PREVIEW UNAVAILABLE")

        painter.setPen(QPen(QColor("#4b515a") if not self.muted else QColor("#353a41"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class GameTitleLabel(QLabel):
    """One title slot: transparent logo when available, styled text otherwise."""

    def __init__(self, game: GameConfig):
        super().__init__()
        self.setObjectName("gameTitle")
        logo_value = game.extras.get("logo")
        self.logo_path = logo_asset_path(logo_value if isinstance(logo_value, str) else None)
        loaded_pixmap = QPixmap(str(self.logo_path)) if self.logo_path is not None else QPixmap()
        self.source_pixmap = self._trim_transparent_margins(loaded_pixmap)
        self.has_logo = not self.source_pixmap.isNull()
        self.muted = not game.enabled
        self.logo_max_width = {
            "cruisn_usa": 285,
            "cruisn_world": 310,
            "cruisn_exotica": 320,
        }.get(game.id, 300)
        self.setProperty("hasLogo", self.has_logo)
        self.setMinimumSize(230, 88)
        self.setMaximumSize(330, 102)
        self.setAlignment(Qt.AlignCenter)
        if self.has_logo:
            self.setToolTip(f"Logo: {self.logo_path}")
            self._update_logo_pixmap()
        else:
            self.setText(game.display_name)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.has_logo:
            self._update_logo_pixmap()

    @staticmethod
    def _trim_transparent_margins(pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull() or not pixmap.hasAlphaChannel():
            return pixmap
        bounds = QRegion(pixmap.mask()).boundingRect()
        return pixmap.copy(bounds) if bounds.isValid() and not bounds.isEmpty() else pixmap

    def _update_logo_pixmap(self) -> None:
        if not self.has_logo or self.width() <= 0:
            return
        bounds = QSize(min(self.width(), self.logo_max_width), min(self.height(), 96))
        scaled = self.source_pixmap.scaled(bounds, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self.muted:
            muted_pixmap = QPixmap(scaled.size())
            muted_pixmap.fill(Qt.transparent)
            painter = QPainter(muted_pixmap)
            painter.setOpacity(0.48)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            scaled = muted_pixmap
        self.setPixmap(scaled)


def game_accent(game_id: str) -> str:
    return {
        "cruisn_world": PALETTE["world"],
        "cruisn_exotica": PALETTE["exotica"],
        "cruisn_usa": PALETTE["usa"],
        "velocity": PALETTE["velocity"],
    }.get(game_id, "#78889c")


class RecessedTray(QFrame):
    """One broad, painted control cavity shared by every game card."""

    def __init__(self):
        super().__init__()
        self.setObjectName("controlTray")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 13, 13)

        well = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        well.setColorAt(0.0, QColor(4, 9, 17, 246))
        well.setColorAt(0.10, QColor(12, 21, 35, 244))
        well.setColorAt(0.72, QColor(21, 34, 53, 241))
        well.setColorAt(1.0, QColor(30, 45, 66, 242))
        painter.fillPath(path, well)

        painter.setPen(QPen(QColor(2, 5, 10, 225), 3))
        painter.drawRoundedRect(rect, 13, 13)
        painter.setPen(QPen(QColor(115, 136, 160, 92), 1))
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 10, 10)

        # Static occlusion and reflection where the tray meets the upper shell.
        painter.setPen(QPen(QColor(0, 0, 0, 155), 4))
        painter.drawLine(13, 4, self.width() - 13, 4)
        painter.setPen(QPen(QColor(166, 187, 208, 48), 1))
        painter.drawLine(15, self.height() - 5, self.width() - 15, self.height() - 5)


class GameCard(QFrame):
    def __init__(self, game: GameConfig, window: "LauncherWindow"):
        super().__init__()
        self.game = game
        self.window = window
        self.setObjectName("gameCard")
        self.setProperty("runState", "idle")
        self.setProperty("gameId", game.id)
        self.setMinimumWidth(380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover)
        self._selected = False
        self._highlight = 0.0
        self._background_cache = QPixmap()
        self._background_cache_size = QSize()

        self.artwork = ArtworkPanel(game)
        self.artwork.setParent(self)
        self.artwork.hide()
        self.highlight_animation = QVariantAnimation(self)
        self.highlight_animation.setDuration(160)
        self.highlight_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.highlight_animation.valueChanged.connect(self._set_highlight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 8)
        layout.setSpacing(2)
        accent_bar = QFrame()
        accent_bar.setObjectName("accentBar")
        accent_bar.setFixedSize(132, 7)
        layout.addWidget(accent_bar, 0, Qt.AlignLeft)
        self.title = GameTitleLabel(game)
        layout.addWidget(self.title, 0, Qt.AlignHCenter)
        self.exhibit_label = QLabel(EXHIBIT_LABELS.get(game.id, "ARCHIVE EXHIBIT"))
        self.exhibit_label.setObjectName("exhibitLabel")
        self.exhibit_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.exhibit_label)
        layout.addStretch(1)

        tray = RecessedTray()
        tray_layout = QVBoxLayout(tray)
        tray_layout.setContentsMargins(10, 6, 10, 6)
        tray_layout.setSpacing(2)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        self.status = QLabel("●  Checking…")
        self.status.setObjectName("gameStatus")
        self.status.setMinimumHeight(23)
        self.status.setMinimumWidth(142)
        self.status.setMaximumWidth(170)
        summary_row.addWidget(self.status)
        summary_row.addStretch(1)

        indicators = QVBoxLayout()
        indicators.setSpacing(0)
        self.build_indicator = QLabel("BUILD  CHECKING")
        self.rom_indicator = QLabel("ROM    CHECKING")
        self.build_indicator.setObjectName("indicator")
        self.rom_indicator.setObjectName("indicator")
        indicators.addWidget(self.build_indicator)
        indicators.addWidget(self.rom_indicator)
        summary_row.addLayout(indicators)
        tray_layout.addLayout(summary_row)

        self.detail = QLabel()
        self.detail.setObjectName("detail")
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(15)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tray_layout.addWidget(self.detail)
        self.history = QLabel("Never launched")
        self.history.setObjectName("history")
        self.history.setMinimumHeight(9)
        tray_layout.addWidget(self.history)

        groove = QFrame()
        groove.setObjectName("trayGroove")
        groove.setFixedHeight(2)
        tray_layout.addWidget(groove)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(7)
        self.launch_button = QPushButton("LAUNCH")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.clicked.connect(lambda: window.launch(game.id))
        self.launch_button.setText("PLAY")
        primary_row.addWidget(self.launch_button, 1)
        self.advanced_button = QPushButton("ADVANCED")
        self.advanced_button.setObjectName("utilityButton")
        self.advanced_button.clicked.connect(lambda: window.open_advanced(game.id))
        primary_row.addWidget(self.advanced_button, 1)
        tray_layout.addLayout(primary_row)
        self.game_folder_button: QPushButton | None = None
        self.save_folder_button: QPushButton | None = None
        layout.addWidget(tray)

        for child in self.findChildren(QPushButton):
            child.installEventFilter(self)

    @property
    def presentation_active(self) -> bool:
        return self._selected

    def set_presentation_active(self, active: bool) -> None:
        if self._selected == active:
            return
        self._selected = active
        self.setProperty("presentationActive", active)
        self.highlight_animation.stop()
        self.highlight_animation.setStartValue(self._highlight)
        self.highlight_animation.setEndValue(1.0 if active else 0.0)
        self.highlight_animation.start()
        self.update()

    def _set_highlight(self, value) -> None:
        self._highlight = float(value)
        self.update()

    def _has_keyboard_focus(self) -> bool:
        focused = QApplication.focusWidget()
        return self.hasFocus() or (focused is not None and self.isAncestorOf(focused))

    def enterEvent(self, event) -> None:
        self.window.activate_card(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._has_keyboard_focus():
            self.window.deactivate_card(self)
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self.window.activate_card(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        QTimer.singleShot(0, self._deactivate_if_unfocused)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.FocusIn:
            self.window.activate_card(self)
        elif event.type() == QEvent.FocusOut:
            QTimer.singleShot(0, self._deactivate_if_unfocused)
        return super().eventFilter(watched, event)

    def _deactivate_if_unfocused(self) -> None:
        if not self.underMouse() and not self._has_keyboard_focus():
            self.window.deactivate_card(self)

    def resizeEvent(self, event) -> None:
        self._background_cache = QPixmap()
        self._background_cache_size = QSize()
        super().resizeEvent(event)

    def _scaled_background(self) -> QPixmap:
        if not self.artwork.has_artwork:
            return QPixmap()
        target_size = QSize(max(1, self.width() - 16), max(1, self.height() - 16))
        if self._background_cache_size != target_size or self._background_cache.isNull():
            self._background_cache = self.artwork.pixmap.scaled(
                target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._background_cache_size = target_size
        return self._background_cache

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outer = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        outer_path = QPainterPath()
        outer_path.addRoundedRect(outer, 17, 17)
        accent = QColor(game_accent(self.game.id))

        # A broad, slightly tinted rim reads as molded ABS rather than a flat outline.
        rim = QLinearGradient(outer.topLeft(), outer.bottomRight())
        rim.setColorAt(0.0, QColor(112, 131, 155, 245))
        rim.setColorAt(0.10, QColor(54, 71, 95, 248))
        rim.setColorAt(0.56, QColor(34, 48, 70, 250))
        rim.setColorAt(1.0, QColor(8, 14, 25, 255))
        painter.fillPath(outer_path, rim)

        art_rect = outer.adjusted(7, 7, -7, -7)
        art_path = QPainterPath()
        art_path.addRoundedRect(art_rect, 11, 11)
        painter.save()
        painter.setClipPath(art_path)
        painter.fillPath(art_path, QColor("#18243a"))

        background = self._scaled_background()
        if not background.isNull():
            x = round(art_rect.center().x() - background.width() / 2)
            y = round(art_rect.center().y() - background.height() / 2)
            painter.setOpacity(0.88 if self.game.enabled else 0.58)
            painter.drawPixmap(x, y, background)
            painter.setOpacity(1.0)
        else:
            fallback = QLinearGradient(art_rect.topLeft(), art_rect.bottomRight())
            fallback.setColorAt(0.0, QColor("#302b4b"))
            fallback.setColorAt(0.5, QColor("#20283b"))
            fallback.setColorAt(1.0, QColor("#111827"))
            painter.fillPath(art_path, fallback)
            painter.setPen(QPen(QColor("#303b54"), 1))
            for x in range(-self.height(), self.width(), 22):
                painter.drawLine(x, self.height(), x + self.height(), 0)

        # Idle art is strongly subdued; selection removes roughly 12% of the shade.
        idle_alpha = 190 if self.game.enabled else 208
        overlay_alpha = round(idle_alpha - (30 * self._highlight))
        shade = QLinearGradient(self.rect().topLeft(), self.rect().bottomRight())
        shade.setColorAt(0.0, QColor(7, 13, 24, max(120, overlay_alpha - 24)))
        shade.setColorAt(0.55, QColor(9, 16, 29, overlay_alpha))
        shade.setColorAt(1.0, QColor(5, 9, 18, min(235, overlay_alpha + 24)))
        painter.fillPath(art_path, shade)

        gloss = QLinearGradient(art_rect.topLeft(), art_rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(225, 238, 250, 42 if self._selected else 28))
        gloss.setColorAt(0.18, QColor(163, 188, 215, 14))
        gloss.setColorAt(0.38, QColor(255, 255, 255, 0))
        painter.fillPath(art_path, gloss)
        painter.restore()

        run_state = self.property("runState")
        if run_state == "running":
            accent = QColor("#f0bb45")
        elif run_state == "stopping":
            accent = QColor("#ef7744")
        elif run_state == "external":
            accent = QColor("#d98449")
        border = accent if self._selected or run_state in {"running", "stopping", "external"} else QColor("#526781")
        painter.setPen(QPen(border, 3))
        painter.drawRoundedRect(outer, 17, 17)
        painter.setPen(QPen(QColor(216, 229, 242, 135 if self._selected else 88), 1))
        painter.drawRoundedRect(outer.adjusted(3, 3, -3, -3), 14, 14)
        painter.setPen(QPen(QColor(4, 8, 15, 210), 2))
        painter.drawRoundedRect(art_rect.adjusted(-1, -1, 1, 1), 12, 12)
        painter.setPen(QPen(QColor(206, 221, 238, 72), 1))
        painter.drawRoundedRect(art_rect.adjusted(1, 1, -1, -1), 10, 10)

    def set_run_state(self, state: str) -> None:
        if self.property("runState") == state:
            return
        self.setProperty("runState", state)
        for widget in (self, self.title, self.status):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()


class LauncherWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None, data_directory: Path | None = None):
        super().__init__()
        self.setWindowTitle("Cruis'n Xtreme")
        self.resize(1080, 760)
        self.setMinimumSize(900, 700)
        application = QApplication.instance()
        if application is not None:
            application.setOrganizationName("Cruisn Xtreme")
            application.setApplicationName("Launcher")
        self.settings = settings or QSettings(QSettings.IniFormat, QSettings.UserScope, "Cruisn Xtreme", "Launcher")
        self.bridge = Bridge()
        games = load_games(games_config_path())
        user_data = data_directory or Path(
            QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            or (Path.home() / "Library/Application Support/Cruisn Xtreme/Launcher")
        )
        for index, game in enumerate(games):
            rom = self.settings.value(f"games/{game.id}/rom", str(game.rom_path) if game.rom_path else "")
            executable = self.settings.value(f"games/{game.id}/executable", str(game.executable_path) if game.executable_path else "")
            working = self.settings.value(f"games/{game.id}/workingDirectory", str(game.working_directory) if game.working_directory else "")
            advanced = self.settings.value(f"games/{game.id}/advancedArguments", "")
            log_path = user_data / "logs" / game.id
            games[index] = replace(
                game,
                rom_path=Path(rom).expanduser().resolve() if rom else None,
                executable_path=Path(executable).expanduser().resolve() if executable else None,
                working_directory=Path(working).expanduser().resolve() if working else None,
                log_path=log_path,
                extras={**game.extras, "advanced_arguments": advanced},
            )
        self.manager = ProcessManager(games, self.bridge.state_changed.emit, self.bridge.error.emit)
        self.rows: dict[str, GameCard] = {}
        self._active_card: GameCard | None = None

        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.addStretch()
        content = QFrame()
        content.setObjectName("content")
        content.setMaximumWidth(1080)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(17, 15, 17, 17)
        content_layout.setSpacing(10)

        header_panel = QFrame()
        header_panel.setObjectName("headerPanel")
        header = QHBoxLayout(header_panel)
        header.setContentsMargins(16, 9, 12, 9)
        title_stack = QVBoxLayout()
        heading = QLabel("CRUIS'N XTREME")
        heading.setObjectName("heading")
        subheading = QLabel("THE CRUIS'N COLLECTION")
        subheading.setObjectName("subheading")
        technical = QLabel("CHOOSE A GAME  •  PRESS PLAY")
        technical.setObjectName("technicalLine")
        title_stack.addWidget(heading)
        title_stack.addWidget(subheading)
        title_stack.addWidget(technical)
        header.addLayout(title_stack)
        header.addWidget(CheckerStrip(), 1)
        content_layout.addWidget(header_panel)

        card_grid = QGridLayout()
        card_grid.setHorizontalSpacing(12)
        card_grid.setVerticalSpacing(10)
        self.card_grid = card_grid
        for index, game in enumerate(games):
            card = GameCard(game, self)
            self.rows[game.id] = card
            row, column = divmod(index, 2)
            card_grid.addWidget(card, row, column)
            card_grid.setColumnStretch(column, 1)
            card_grid.setRowStretch(row, 1)
        content_layout.addLayout(card_grid, 1)
        outer.addWidget(content, 1)
        outer.addStretch()
        self.setCentralWidget(root)

        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(False)
        self.setStatusBar(status_bar)
        version_label = QLabel(VERSION)
        version_label.setObjectName("versionLabel")
        status_bar.addPermanentWidget(version_label)
        status_bar.showMessage("Select a game to begin")

        self.bridge.state_changed.connect(self.refresh_one)
        self.bridge.error.connect(self.show_error)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll_status)
        self._timer.start(3000)
        self.poll_status()
        QTimer.singleShot(0, self.center_on_screen)
        self.setStyleSheet(STYLE_SHEET)

    def activate_card(self, card: GameCard) -> None:
        if self._active_card is card:
            return
        previous = self._active_card
        self._active_card = card
        if previous is not None:
            previous.set_presentation_active(False)
        card.set_presentation_active(True)

    def deactivate_card(self, card: GameCard) -> None:
        if self._active_card is not card:
            return
        self._active_card = None
        card.set_presentation_active(False)

    def center_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.frameGeometry().center())

    @Slot()
    def refresh_all(self) -> None:
        self.poll_status()
        self.statusBar().showMessage("Status refreshed", 1800)

    @Slot()
    def poll_status(self) -> None:
        for game_id in self.manager.games:
            self.refresh_one(game_id)

    @Slot(str)
    def refresh_one(self, game_id: str) -> None:
        managed = self.manager.games[game_id]
        card = self.rows[game_id]
        config = managed.config
        snapshot = managed.state()

        if snapshot.status is GameStatus.COMING_SOON:
            detail, style_state = config.extras.get("availability_note", "This title is not available yet."), "future"
        elif snapshot.status is GameStatus.RUNNING:
            detail, style_state = f"PID {snapshot.owned_pid} • launched here", "running"
        elif snapshot.status is GameStatus.STOP_REQUESTED:
            detail, style_state = f"PID {snapshot.owned_pid} • stop requested", "stopping"
        elif snapshot.status is GameStatus.RUNNING_EXTERNALLY:
            detail = f"Exact executable match • PID(s) {', '.join(map(str, snapshot.external_pids))}"
            style_state = "external"
        elif snapshot.status is GameStatus.MISSING_BUILD:
            detail, style_state = f"Expected: {config.executable_path or 'No executable configured'}", "missingBuild"
        elif snapshot.status is GameStatus.MISSING_ROM:
            detail, style_state = "Choose your legally obtained ROM in the Play setup.", "missingRom"
        elif snapshot.status is GameStatus.UNSUPPORTED_ROM:
            detail, style_state = "This ROM revision is not supported by the selected build.", "missingRom"
        else:
            detail, style_state = "Supported build and ROM are ready.", "ready"

        card.set_run_state(style_state)
        card.status.setText(f"●  {snapshot.status.value}")
        card.detail.setText(detail)
        card.detail.setToolTip(
            f"Build: {config.executable_path or 'not configured'}\n"
            f"ROM: {config.rom_path or 'not configured'}"
        )
        build_text = "NOT AVAILABLE" if not config.enabled else ("READY" if snapshot.executable_ready else "CHOOSE")
        card.build_indicator.setText(f"BUILD  {build_text}")
        rom_text = "NOT AVAILABLE" if config.rom_path is None else ("READY" if snapshot.rom_ready else "MISSING")
        card.rom_indicator.setText(f"ROM    {rom_text}")
        if snapshot.last_run_at is not None:
            when = snapshot.last_run_at.astimezone().strftime("%b %d, %Y  %I:%M %p")
            exit_text = "running" if snapshot.owned_pid is not None else (str(snapshot.last_exit_code) if snapshot.last_exit_code is not None else "unknown")
            card.history.setText(f"Last run: {when}  •  Exit: {exit_text}")
        else:
            card.history.setText("Never launched")

        busy = snapshot.owned_pid is not None or snapshot.status in {
            GameStatus.RUNNING_EXTERNALLY, GameStatus.STOP_REQUESTED,
        }
        card.launch_button.setEnabled(config.enabled and not busy)
        card.launch_button.setText("RUNNING" if busy else "PLAY")
        card.advanced_button.setEnabled(True)

    def launch(self, game_id: str) -> None:
        managed = self.manager.games[game_id]
        config = managed.config
        if not config.enabled:
            self.show_error(game_id, config.extras.get("availability_note", "This title is not available to play yet."))
            return
        snapshot = managed.state(refresh_external=False)
        if not snapshot.rom_ready or not snapshot.rom_compatible:
            rom, _ = QFileDialog.getOpenFileName(
                self, f"Choose your {config.display_name} ROM", str(Path.home()),
                "Nintendo 64 ROMs (*.z64 *.n64 *.v64);;Game ROMs (*);;All files (*)",
            )
            if not rom:
                return
            try:
                self._set_game_path(game_id, "rom", Path(rom))
            except ValueError as exc:
                self.show_error(game_id, str(exc))
                return
        if (
            managed.config.executable_path is None
            or not managed.config.executable_path.is_file()
            or not os.access(managed.config.executable_path, os.X_OK)
        ):
            executable, _ = QFileDialog.getOpenFileName(
                self, f"Choose {config.display_name} executable", str(Path.home()), "Applications and executables (*)",
            )
            if not executable:
                return
            self._set_game_path(game_id, "executable", Path(executable))
        if managed.config.working_directory is None or not managed.config.working_directory.is_dir():
            self._update_config(game_id, working_directory=managed.config.executable_path.parent)
        try:
            log = managed.launch()
            self.refresh_one(game_id)
            snapshot = managed.state(refresh_external=False)
            if snapshot.owned_pid is not None:
                self.statusBar().showMessage(f"Running {managed.config.display_name} • PID {snapshot.owned_pid}")
            else:
                self.statusBar().showMessage(f"{managed.config.display_name} exited during startup")
        except Exception as exc:
            self.show_error(game_id, str(exc))
        self.refresh_one(game_id)

    def _update_config(self, game_id: str, **changes) -> None:
        managed = self.manager.games[game_id]
        managed.config = replace(managed.config, **changes)

    def _set_game_path(self, game_id: str, kind: str, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Selected {kind} file does not exist:\n{path}")
        config = self.manager.games[game_id].config
        if kind == "rom":
            expected = config.extras.get("expected_rom_sha256")
            if expected and sha256_file(path) != str(expected).lower():
                raise ValueError(
                    f"Unsupported ROM revision. {config.display_name} requires the supported ROM revision; the selected file's SHA-256 does not match."
                )
            self._update_config(game_id, rom_path=path)
        elif kind == "executable":
            if not os.access(path, os.X_OK):
                raise ValueError(f"Selected executable is not runnable:\n{path}")
            self._update_config(game_id, executable_path=path, working_directory=path.parent)
        else:
            raise ValueError(f"Unknown path type: {kind}")
        self.settings.setValue(f"games/{game_id}/{kind}", str(path))
        if kind == "executable":
            self.settings.setValue(f"games/{game_id}/workingDirectory", str(path.parent))
        self.settings.sync()
        self.refresh_one(game_id)

    def open_advanced(self, game_id: str) -> None:
        managed = self.manager.games[game_id]
        config = managed.config
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{config.display_name} — Advanced")
        dialog.setMinimumWidth(580)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        rom_field = QLineEdit(str(config.rom_path or ""))
        exe_field = QLineEdit(str(config.executable_path or ""))
        args_field = QLineEdit(str(config.extras.get("advanced_arguments", "")))
        for field, label, kind in ((rom_field, "Choose ROM…", "rom"), (exe_field, "Choose executable…", "executable")):
            browse = QPushButton(label)
            def choose(_checked=False, field=field, kind=kind, title=label):
                start = field.text() or str(Path.home())
                selected, _ = QFileDialog.getOpenFileName(dialog, title, start, "All files (*)")
                if selected:
                    field.setText(selected)
            browse.clicked.connect(choose)
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(browse)
            wrapper = QWidget()
            wrapper.setLayout(row)
            form.addRow("ROM:" if kind == "rom" else "Executable:", wrapper)
        form.addRow("Extra arguments:", args_field)
        layout.addLayout(form)
        notice = QLabel("Advanced arguments are appended as separate arguments. Leave blank for normal Play.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        actions = QHBoxLayout()
        stop_button = QPushButton("Stop game")
        stop_button.setEnabled(managed.state(refresh_external=False).can_stop)
        stop_button.clicked.connect(lambda: self.stop(game_id))
        force_button = QPushButton("Force quit…")
        force_button.setEnabled(managed.state(refresh_external=False).can_force_quit)
        force_button.clicked.connect(lambda: self.force_quit(game_id))
        log_button = QPushButton("Open latest log")
        log_button.setEnabled(bool(managed.latest_log and managed.latest_log.exists()))
        log_button.clicked.connect(lambda: self.open_log(game_id))
        actions.addWidget(stop_button)
        actions.addWidget(force_button)
        actions.addWidget(log_button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            if rom_field.text().strip():
                self._set_game_path(game_id, "rom", Path(rom_field.text().strip()))
            if exe_field.text().strip():
                self._set_game_path(game_id, "executable", Path(exe_field.text().strip()))
            extra_args = args_field.text().strip()
            shlex.split(extra_args)
            self._update_config(game_id, extras={**self.manager.games[game_id].config.extras, "advanced_arguments": extra_args})
            self.settings.setValue(f"games/{game_id}/advancedArguments", extra_args)
            self.settings.sync()
        except (ValueError, OSError) as exc:
            self.show_error(game_id, str(exc))

    def stop(self, game_id: str) -> None:
        managed = self.manager.games[game_id]
        if not managed.request_stop():
            self.refresh_one(game_id)
            return
        self.refresh_one(game_id)
        self.statusBar().showMessage(f"Stopping {managed.config.display_name}…")
        threading.Thread(target=managed.stop, daemon=True).start()

    def force_quit(self, game_id: str) -> None:
        managed = self.manager.games[game_id]
        snapshot = managed.state()
        if snapshot.status is GameStatus.RUNNING_EXTERNALLY:
            answer = QMessageBox.question(
                self, "Force Quit External Process",
                f"Force quit the exact {managed.config.display_name} executable process (PID(s): {', '.join(map(str, snapshot.external_pids))})?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        elif not snapshot.can_force_quit:
            self.refresh_one(game_id)
            return
        self.statusBar().showMessage(f"Force quitting {managed.config.display_name}…")
        threading.Thread(target=managed.force_quit, daemon=True).start()

    def open_log(self, game_id: str) -> None:
        log = self.manager.games[game_id].latest_log
        if log and log.exists():
            self.open_path(log)

    def open_game_folder(self, game_id: str) -> None:
        folder = configured_game_folder(self.manager.games[game_id].config)
        if folder is not None:
            self.open_folder(folder, "Game folder")

    def open_save_folder(self, game_id: str) -> None:
        folder = configured_save_folder(self.manager.games[game_id].config)
        if folder is not None:
            self.open_folder(folder, "Save folder")

    def open_folder(self, path: Path, label: str) -> None:
        try:
            open_configured_folder(
                path,
                label,
                lambda folder: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))),
            )
        except FolderShortcutError as exc:
            self.show_error("", str(exc))

    def open_path(self, path: Path) -> None:
        if not path.exists():
            self.show_error("", f"Path does not exist:\n{path}")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.show_error("", f"Could not open:\n{path}")

    @Slot(str, str)
    def show_error(self, _game_id: str, message: str) -> None:
        QMessageBox.critical(self, "Cruis'n Xtreme", message)
        self.statusBar().showMessage("An error occurred; see the dialog for details", 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.manager.any_owned_running():
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle("Game Still Running")
        box.setText("A game is still running. Stop it and exit?")
        stop_button = box.addButton("Stop Game and Exit", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not stop_button:
            event.ignore()
            return
        self.statusBar().showMessage("Stopping running games…")
        if self.manager.stop_all_for_exit():
            event.accept()
        else:
            event.ignore()
            QMessageBox.critical(self, "Could Not Exit Safely", "A launched game could not be stopped. The launcher will remain open.")


STYLE_SHEET = """
QMainWindow, QWidget {
    background: %(background)s;
    color: #eee9dc;
    font-family: "Avenir Next";
    font-size: 13px;
}
#content {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #718097, stop:0.018 #3f526c,
                                stop:0.075 #2b405d, stop:0.22 %(shell)s,
                                stop:0.78 #14223a, stop:0.97 #0b1424, stop:1 #050912);
    border: 4px solid #344a67;
    border-top-color: #8795a8;
    border-left-color: #667c98;
    border-bottom-color: #04070d;
    border-right-color: #080e19;
    border-radius: 16px;
}
#headerPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #516984, stop:0.05 #2c4667,
                                stop:0.24 #203a5b, stop:0.72 #142b49,
                                stop:0.95 #0d1c31, stop:1 #081222);
    border: 3px solid #405b7d;
    border-top-color: #92a2b7;
    border-left-color: #7088a5;
    border-bottom-color: #07101e;
    border-right-color: #0a1627;
    border-radius: 12px;
}
#heading {
    background: transparent;
    color: #ffc54f;
    font-family: "Avenir Next Condensed";
    font-size: 31px;
    font-style: italic;
    font-weight: 900;
    letter-spacing: 1px;
    border-left: 6px solid #e15e31;
    padding-left: 10px;
}
#subheading {
    background: transparent;
    color: #b1bfd0;
    font-family: "DIN Condensed";
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
}
#technicalLine {
    background: transparent;
    color: #71839a;
    font-family: "DIN Condensed";
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 1px;
}
#gameCard {
    background: transparent;
    border: none;
}
#accentBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #d5dbe3, stop:0.18 #8996a7, stop:1 #475467);
    border: 1px solid rgba(225, 235, 245, 90);
    border-radius: 2px;
}
#gameCard[gameId="cruisn_world"] #accentBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #a7efff, stop:0.22 %(world)s, stop:1 %(world_dark)s);
}
#gameCard[gameId="cruisn_exotica"] #accentBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #ffc0cf, stop:0.22 %(exotica)s, stop:1 %(exotica_dark)s);
}
#gameCard[gameId="cruisn_usa"] #accentBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #c4cbd3, stop:0.22 %(usa)s, stop:1 %(usa_dark)s);
}
#gameCard[gameId="velocity"] #accentBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #fff0b8, stop:0.22 %(velocity)s, stop:1 %(velocity_dark)s);
}
#gameTitle {
    background: transparent;
    color: #f4efe3;
    font-family: "Avenir Next Condensed";
    font-size: 35px;
    font-style: italic;
    font-weight: 900;
}
#gameCard[gameId="cruisn_world"] #gameTitle { color: #dff6ff; }
#gameCard[gameId="cruisn_exotica"] #gameTitle { color: #ffe5ea; }
#gameCard[gameId="velocity"] #gameTitle { color: #fff0bf; }
#gameCard[runState="future"] #gameTitle { color: #9da3a8; }
#exhibitLabel {
    background: rgba(5, 10, 18, 125);
    color: #aeb9c6;
    border: none;
    border-radius: 5px;
    padding: 1px 7px;
    font-family: "DIN Condensed";
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
}
#gameCard[gameId="velocity"] #exhibitLabel { color: #e2c875; }
#gameStatus {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(4, 9, 17, 232),
                                stop:0.12 rgba(11, 20, 34, 224),
                                stop:1 rgba(22, 34, 52, 218));
    border: 2px solid #26384e;
    border-top-color: #152236;
    border-bottom-color: #65768c;
    border-left: 4px solid #53c878;
    border-radius: 9px;
    color: #6ee28f;
    padding: 3px 8px;
    font-family: "DIN Alternate";
    font-size: 12px;
    font-weight: 700;
}
#gameCard[runState="running"] {
    background: transparent;
    border: none;
}
#gameCard[runState="running"] #gameStatus {
    border-left-color: #f0bb45;
    color: #ffd66f;
    background: #29251c;
}
#gameCard[runState="stopping"] {
    background: transparent;
    border: none;
}
#gameCard[runState="stopping"] #gameStatus {
    border-left-color: #ef7744;
    color: #ff9a69;
    background: #2b201d;
}
#gameCard[runState="external"] { background: transparent; border: none; }
#gameCard[runState="external"] #gameStatus {
    border-left-color: #d98449;
    color: #f0a064;
}
#gameCard[runState="missingBuild"] { background: transparent; border: none; }
#gameCard[runState="missingBuild"] #gameStatus {
    border-left-color: #cb5962;
    color: #e77a81;
}
#gameCard[runState="missingRom"] { background: transparent; border: none; }
#gameCard[runState="missingRom"] #gameStatus {
    border-left-color: #d18a48;
    color: #e6a35f;
}
#gameCard[runState="future"] {
    background: transparent;
    border: none;
}
#gameCard[runState="future"] #gameStatus {
    border-left-color: #747d86;
    color: #959da4;
    background: #1e2125;
}
#controlTray { background: transparent; border: none; }
#trayGroove {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(0, 0, 0, 170), stop:1 rgba(130, 151, 174, 70));
    border: none;
    border-radius: 1px;
}
#indicator {
    background: transparent;
    color: #98a0a7;
    font-family: "Menlo";
    font-size: 9px;
    font-weight: 700;
}
#detail { background: transparent; color: #c9c5bb; font-size: 10px; }
#history { background: transparent; color: #8e9aaa; font-family: "DIN Alternate"; font-size: 7px; }
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #8091a8, stop:0.08 #536b88,
                                stop:0.48 #3d5573, stop:0.84 #2d415d,
                                stop:1 #18283e);
    border: 2px solid #536b89;
    border-top-color: #8193aa;
    border-left-color: #6c829d;
    border-bottom-color: #101827;
    border-right-color: #162237;
    border-radius: 9px;
    color: #eee9dc;
    padding: 5px 8px;
    font-family: "DIN Alternate";
    font-weight: 700;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #9aabc0, stop:0.10 #647d9b,
                                stop:0.52 #496584, stop:1 #223751);
    border-top-color: #aebdce;
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1a293d, stop:0.30 #293c55, stop:1 #455c79);
    border-top-color: #101a28;
    border-left-color: #152237;
    border-bottom-color: #7e91a8;
    border-right-color: #687d97;
}
#launchButton { padding: 6px; font-size: 14px; letter-spacing: 1px; }
#gameCard[gameId="cruisn_world"] #launchButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #5ed3ee, stop:0.10 #209fc4,
                                stop:0.58 %(world_dark)s, stop:1 #0d4c6a);
    border-top-color: %(world)s;
    border-left-color: #238caf;
}
#gameCard[gameId="cruisn_world"] #launchButton:hover { background: #238fb5; }
#gameCard[gameId="cruisn_exotica"] #launchButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #f08aa0, stop:0.10 #d95270,
                                stop:0.58 %(exotica_dark)s, stop:1 #6e2138);
    border-top-color: %(exotica)s;
    border-left-color: #c34b66;
}
#gameCard[gameId="cruisn_exotica"] #launchButton:hover { background: #b63d59; }
#gameCard[gameId="cruisn_usa"] #launchButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #9ca7b3, stop:0.10 #727e8b,
                                stop:0.58 %(usa_dark)s, stop:1 #303943);
    border-top-color: %(usa)s;
}
#gameCard[gameId="velocity"] #launchButton {
    background: #343638;
    border-top-color: #707070;
}
#stopButton { padding: 6px; font-size: 12px; }
#gameCard[runState="running"] #stopButton {
    background: #a55a20;
    border-top-color: #de8b42;
    color: #fff0d8;
}
#gameCard[runState="stopping"] #utilityButton[actionRole="danger"] {
    background: #892f2d;
    border-color: #c85c50;
    color: #fff0e8;
}
#utilityButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(83, 101, 125, 210),
                                stop:0.12 rgba(35, 50, 70, 218),
                                stop:1 rgba(10, 18, 31, 230));
    border: 1px solid rgba(91, 111, 137, 150);
    color: #b6c0cc;
    padding: 2px;
    font-family: "Avenir Next";
    font-size: 9px;
    font-weight: 600;
}
#utilityButton:hover { color: #fff5df; border-color: #758aa4; background: rgba(52, 68, 91, 235); }
#gameCard[runState="running"] #utilityButton[actionRole="danger"] {
    background: #352727;
    border-color: #68403e;
    color: #eab0aa;
}
#gameCard[runState="external"] #utilityButton[actionRole="danger"] {
    background: #4b3025;
    border-color: #89553a;
    color: #f1b68c;
}
QPushButton:disabled, #gameCard #launchButton:disabled {
    color: #68717c;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #444d58, stop:0.12 #303842, stop:1 #1c222a);
    border-top-color: #56606c;
    border-left-color: #48525e;
    border-bottom-color: #11161c;
    border-right-color: #161c23;
}
#refreshButton { min-width: 86px; padding: 7px 9px; font-size: 10px; letter-spacing: 1px; }
QStatusBar { background: #080d17; border-top: 2px solid #30435e; color: #aab4c2; }
#versionLabel { background: transparent; color: #676e74; padding-right: 8px; font-size: 10px; }
""" % PALETTE


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cruis'n Xtreme")
    window = LauncherWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
