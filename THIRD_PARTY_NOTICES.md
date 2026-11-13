# Third-party dependency notices

No third-party library source or binary package is bundled in this source candidate. These declared dependencies retain their own license terms; the project MIT license does not replace them.

- **PySide6/Qt:** runtime GUI dependency in `Launcher/requirements.txt` (`PySide6>=6.8,<7`). The code imports QtCore, QtGui, and QtWidgets. GUI tests use QtTest. This dependency is installed separately by the user; exact resolved package/module versions are not pinned. Review the applicable Qt/PySide terms before redistributing a packaged app.
- **PyInstaller:** build-time dependency in `Launcher/requirements-build.txt` (`PyInstaller==6.22.2`). It is not imported by normal source startup. Review its license and bootloader notices before distributing an app produced by it.
- **Game executables and SDL2-compat:** not included. Each runtime and its dependencies are independently supplied and licensed.

This file is a dependency summary, not a substitute for upstream license texts or notices. No dependency license text is copied into this candidate because no dependency implementation is included.

This is a source-only distribution. Any future packaged application is a separate distribution: review its resolved Qt/PySide6 modules and PyInstaller bootloader/components, include their required notices, and comply with their applicable terms. No packaged application is included here.
