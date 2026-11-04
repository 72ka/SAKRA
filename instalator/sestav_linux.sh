#!/bin/sh
# SAKRA - samostatná složka dist/SAKRA pro Linux (PyInstaller); Python v cílovém počítači pak není potřeba.
set -e
cd "$(dirname "$0")/.."
if command -v uv >/dev/null 2>&1; then
    uv sync
    uv run --with pyinstaller pyinstaller --noconfirm --clean instalator/sakra.spec
else
    [ -x .venv/bin/python ] || python3 -m venv .venv
    .venv/bin/python -m pip install -e . pyinstaller
    .venv/bin/pyinstaller --noconfirm --clean instalator/sakra.spec
fi
echo "Hotovo: dist/SAKRA/SAKRA"
