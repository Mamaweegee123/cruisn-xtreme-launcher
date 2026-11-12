# MIT license scope

The root `LICENSE` applies only to the following 19 launcher source, test, and build-helper files and the original owner-directed documentation listed below. All 19 source files were hash-matched to the reviewed current launcher overlay. The license does not apply to any excluded file merely because it is in this candidate directory.

## Source, tests, and build helpers

```text
Launcher/.gitignore
Launcher/CruisnXtreme.spec
Launcher/app.py
Launcher/build_app.sh
Launcher/launcher_core.py
Launcher/launcher_paths.py
Launcher/launcher_shortcuts.py
Launcher/run.command
Launcher/setup.sh
Launcher/tests/fixtures/external_fixture.c
Launcher/tests/fixtures/graceful_game.sh
Launcher/tests/test_artwork_panel.py
Launcher/tests/test_folder_shortcuts.py
Launcher/tests/test_launcher_core.py
Launcher/tests/test_launcher_paths.py
Launcher/tests/test_logo_presentation.py
Launcher/tests/test_n64_presentation.py
Launcher/tests/test_state_machine.py
Launcher/tests/test_xtreme_hub.py
```

## Owner-directed documentation

The owner-directed, newly prepared launcher documentation in `README.md`, `SETUP.md`, `KNOWN_ISSUES.md`, `CONTRIBUTING.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE_SCOPE.md`, and `Launcher/assets/README.md` is proposed under the same MIT terms. These texts were prepared with substantial Codex assistance and should receive the owner's final review before upload. `EXCLUDED_FILES.md`, `PUBLICATION_STATUS.md`, `FILE_MANIFEST.tsv`, and `LAUNCHER_FILE_REVIEW.tsv` are private review records and are **not** part of the public license scope.

## Excluded from this grant

`Launcher/games.json` is included as a sanitized operational registry but is outside this license grant: it contains game titles, the supported World ROM hash identifier, and factual compatibility/configuration data. No trademark or game-content rights are granted. The two `Launcher/requirements*.txt` files are dependency declarations and are outside the grant. Qt/PySide6, PyInstaller, Python, game executables, ROMs, saves, game-derived code/data, and any third-party component retain their own terms or are not included.

This scope records the intended file boundary. It does not claim rights in names, marks, ROMs, game assets, or upstream libraries, and it is not a legal opinion on whether any data is copyrightable.
