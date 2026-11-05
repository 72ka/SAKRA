#!/bin/sh
# SAKRA - spusteni v Linuxu. Pri prvnim spusteni (a po zmene zavislosti v pyproject.toml) zalozi
# virtualni prostredi .venv a nainstaluje do nej zavislosti; jinak jen spousti aplikaci.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
    exec uv run --extra kamera sakra "$@"
fi
if [ ! -x .venv/bin/python ]; then
    echo "Prvni spusteni: zakladam .venv..."
    python3 -m venv .venv
fi
if [ ! -f .venv/.sakra-zavislosti ] || [ pyproject.toml -nt .venv/.sakra-zavislosti ]; then
    echo "Instaluji zavislosti..."
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -e ".[kamera]"
    touch .venv/.sakra-zavislosti
fi
exec .venv/bin/python -m sakra "$@"
