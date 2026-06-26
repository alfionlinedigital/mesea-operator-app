"""Entry point: ``python -m mesea_operator`` and the PyInstaller target.

Supports ``--version`` without importing Tk so CI / smoke checks can verify
the build on headless runners.
"""

from __future__ import annotations

import sys

from mesea_operator import __version__  # absolute import: works under `-m` AND frozen


def main() -> None:
    if "--version" in sys.argv:
        print(__version__)
        return
    # File logging + error reporting come up before the UI so a startup failure
    # is recorded. Both degrade gracefully and never block launch.
    from mesea_operator import errors, logs

    logs.setup_logging()
    errors.init_error_reporting(__version__)
    from mesea_operator.ui import main as ui_main  # lazy so --version needs no Tk

    ui_main()


if __name__ == "__main__":
    main()
