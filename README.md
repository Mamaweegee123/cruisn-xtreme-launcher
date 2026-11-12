# Cruis'n Xtreme Launcher

An experimental, source-only developer preview for an unofficial community launcher that organizes local Cruis'n game builds. The launcher does not contain game code, ROMs, game executables, saves, or game artwork. It does not make any title playable by itself.

## What the launcher does

The registry presents four entries: Cruis'n USA, Cruis'n World, Cruis'n Exotica, and Cruis'n Velocity. USA and Exotica are disabled; Velocity remains disabled pending an interactive gameplay test. World is the primary supported title and is enabled in the registry, but Play becomes available only after the user selects a compatible executable and a supported ROM. No game is launched or qualified by this source release.

Users must provide their own legally obtained compatible ROM and game executable. For World, the registry checks the configured ROM against the supported SHA-256 identifier. ROMs, executable files, and saves are never included. The sanitized registry uses no developer-home paths. User selections and logs are stored in per-user locations by the launcher.

## Run from source

Requires Python 3 compatible with the declared PySide6 version. The GUI imports PySide6 QtCore, QtGui, and QtWidgets. See [SETUP.md](SETUP.md). From `Launcher/`, run `./setup.sh`, then `./run.command`. The requirements files are dependency declarations; third-party packages retain their own licenses.

Headless tests can run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

GUI tests require PySide6 and a supported Qt platform. This candidate's GUI was not validated in the preparation environment. Standalone macOS packaging is unverified; the optional PyInstaller recipe has not been run.

## License scope

The root [MIT License](LICENSE) applies only to eligible first-party launcher source, tests, build helpers, and original project documentation listed in [LICENSE_SCOPE.md](LICENSE_SCOPE.md). It does not license the registry's game titles/hash, third-party dependencies, trademarks, ROMs, game assets, game executables, or any other game-derived material. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Trademarks and dependencies

Cruis'n names and marks are used only to identify the games this community tool is intended to organize. They belong to their respective rights holders. This project is unofficial and is not affiliated with, endorsed by, or sponsored by those rights holders. Qt/PySide6 and PyInstaller are separate third-party projects; their terms remain applicable. The launcher source does not bundle them.

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and [CONTRIBUTING.md](CONTRIBUTING.md) before working with this candidate.
