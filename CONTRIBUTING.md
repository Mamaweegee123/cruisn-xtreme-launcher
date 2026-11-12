# Contributing

Keep changes limited to launcher setup, presentation, and process management. Do not add ROMs, saves, game executables, extracted assets, credentials, or unreviewed artwork. Keep process arguments as argument arrays and do not invoke commands through shell interpolation.

Do not enable an experimental title because a binary exists. Document a supported build and ROM revision and qualify actual gameplay separately before changing availability. Changes to a game runtime belong in that runtime's own project and review.

Run tests with `python3 -m unittest discover -s tests`. GUI tests require PySide6; use `QT_QPA_PLATFORM=offscreen` where the host supports Qt's offscreen platform. The Cruis'n World registry entry includes a known ROM hash check, but never place a commercial ROM in a test fixture or contribution.
