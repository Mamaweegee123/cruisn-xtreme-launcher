from __future__ import annotations

import sys
from pathlib import Path


def launcher_workspace() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def games_config_path() -> Path:
    return bundled_resource_root() / "games.json"


def bundled_resource_root() -> Path:
    """Return the source tree in development and PyInstaller data root when frozen."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def artwork_asset_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (bundled_resource_root() / path).resolve()


def logo_asset_path(value: str | None) -> Path | None:
    return artwork_asset_path(value)
