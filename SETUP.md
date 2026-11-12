# Setup

## Requirements

- Python 3 with a PySide6 wheel compatible with that Python version.
- PySide6 6.8 or newer, below 7, from `Launcher/requirements.txt`.
- Optional packaging only: PyInstaller 6.22.2 from `Launcher/requirements-build.txt`.

The launcher uses Python standard-library modules for JSON, paths, hashing, process management, settings helpers, and threading. Its GUI uses PySide6 QtCore, QtGui, and QtWidgets. Tests that render widgets also use PySide6.QtTest. PyInstaller is used only by the optional app-bundle script. No dependency was installed during preparation.

## Start from source

From the repository root:

```sh
cd Launcher
./setup.sh
./run.command
```

The setup script creates `Launcher/.venv` and installs the declared PySide6 requirement. No ROM or game executable is bundled. Select the user's own files in the launcher. Cruis'n World requires the supported ROM revision and a compatible local executable.

## Optional packaging

`./build_app.sh` installs the pinned PyInstaller build dependency and runs `CruisnXtreme.spec`. This recipe has not been run or qualified. It does not establish standalone-app redistribution rights, signing, notarization, or dependency compliance. Review Qt/PySide, PyInstaller bootloader, and bundled dependency requirements before distributing a packaged app.
