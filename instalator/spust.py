"""Vstupní bod pro PyInstaller (SAKRA.exe i sakra-cli.exe)."""
import sys

from sakra.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
