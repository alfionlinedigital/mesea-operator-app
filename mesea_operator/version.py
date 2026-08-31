"""Single-source version resolution for the Mesea Operator.

The version is edited in exactly ONE place: ``[project].version`` in
``pyproject.toml``. Nothing else hardcodes it. At runtime the value is
resolved, in order of preference:

1. **Installed distribution metadata** — ``importlib.metadata.version`` reads
   what pip wrote into ``*.dist-info`` from pyproject. This is the path for
   pip users, developers (``pip install -e .``), and CI.
2. **A build-time-baked module** — ``_baked_version.py``, which the PyInstaller
   spec writes from pyproject just before freezing. A frozen binary ships no
   ``dist-info`` metadata, so this is the only source available inside it.
3. **pyproject.toml, parsed directly** — the fallback for a bare source
   checkout that was never installed (e.g. running ``python -m mesea_operator``
   straight from a clone). pyproject *is* the single source, so reading it is
   authoritative, not a guess.

Kept Tk-free like the rest of the package (only ``ui.py`` imports Tk), so the
``--version`` smoke path and unit tests stay importable on headless machines.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

#: The distribution name as declared in ``[project].name``.
_DIST_NAME = "mesea-operator"

#: Repo root when running from a source checkout: ``<root>/mesea_operator/version.py``.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def read_pyproject_version(root: str | Path) -> str:
    """Return ``[project].version`` from ``<root>/pyproject.toml``.

    Used both at runtime (tier 3) and at build time by the PyInstaller spec to
    bake the frozen fallback — one parser, one source of truth.
    """
    text = Path(root, "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # Python 3.10 ships no tomllib
        return _scan_project_version(text)
    return tomllib.loads(text)["project"]["version"]


def _scan_project_version(text: str) -> str:
    """Minimal ``[project].version`` reader for interpreters without tomllib."""
    in_project = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version"):
            _, _, rhs = line.partition("=")
            return rhs.strip().strip("'\"")
    raise KeyError("[project].version not found in pyproject.toml")


def _baked_version() -> str | None:
    """Return the version baked into a frozen build, or ``None`` if absent."""
    try:
        from mesea_operator._baked_version import VERSION
    except ModuleNotFoundError:
        return None
    return VERSION


def _resolve() -> str:
    try:
        return importlib.metadata.version(_DIST_NAME)
    except importlib.metadata.PackageNotFoundError:
        pass
    baked = _baked_version()
    if baked is not None:
        return baked
    return read_pyproject_version(_REPO_ROOT)


__version__ = _resolve()
