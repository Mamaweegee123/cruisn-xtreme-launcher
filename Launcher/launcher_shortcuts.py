from __future__ import annotations

from pathlib import Path
from typing import Callable

from launcher_core import GameConfig


class FolderShortcutError(RuntimeError):
    pass


def configured_game_folder(game: GameConfig) -> Path | None:
    """Use explicit project data first, with the configured runtime directory as fallback."""
    return game.project_path or game.working_directory


def configured_save_folder(game: GameConfig) -> Path | None:
    return game.save_folder


def open_configured_folder(path: Path, label: str, opener: Callable[[Path], bool]) -> None:
    if not path.exists():
        raise FolderShortcutError(f"{label} does not exist:\n{path}")
    if not path.is_dir():
        raise FolderShortcutError(f"{label} is not a directory:\n{path}")
    if not opener(path):
        raise FolderShortcutError(f"Could not open {label.lower()} in Finder:\n{path}")
