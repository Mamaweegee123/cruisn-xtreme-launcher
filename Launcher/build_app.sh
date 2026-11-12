#!/bin/sh
set -eu
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    printf '%s\n' "Launcher environment is missing. Run ./setup.sh first." >&2
    exit 1
fi

.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller --clean --noconfirm CruisnXtreme.spec

printf '%s\n' "Built: $(pwd)/dist/Cruis'n Xtreme.app"
