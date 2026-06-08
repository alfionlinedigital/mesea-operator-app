"""Entry point: ``python -m mesea_operator`` and the PyInstaller target.

Supports ``--version`` without importing Tk so CI / smoke checks can verify
the build on headless runners.
"""

from __future__ import annotations

import sys

from . import __version__


def main() -> None:
    if "--version" in sys.argv:
        print(__version__)
        return
    from .ui import main as ui_main  # imported lazily so --version needs no Tk

    ui_main()


if __name__ == "__main__":
    main()
