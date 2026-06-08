"""Frozen-app entry point.

PyInstaller runs the target script as a top-level module with no package
context, which breaks relative imports inside a package's ``__main__.py``.
This thin root script imports the package by absolute name, so the frozen
binary and ``python -m mesea_operator`` share the same code path.
"""

from mesea_operator.__main__ import main

if __name__ == "__main__":
    main()
