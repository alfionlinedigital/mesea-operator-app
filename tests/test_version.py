"""Single-source version resolution — pyproject is the only editable source.

These tests guard MES-131's core guarantee: ``mesea_operator.__version__``
tracks ``pyproject.toml`` with no second hardcoded copy to drift, and the
runtime resolver falls through installed-metadata → frozen-bake → pyproject in
that order.
"""

from __future__ import annotations

import importlib.metadata
import sys
import types
from pathlib import Path

import pytest

import mesea_operator
from mesea_operator import version as v

ROOT = Path(__file__).resolve().parent.parent
BAKED_FILE = ROOT / "mesea_operator" / "_baked_version.py"


def _package_not_found(name: str):
    raise importlib.metadata.PackageNotFoundError(name)


def test_pyproject_version_is_read_from_project_table():
    ver = v.read_pyproject_version(ROOT)
    assert ver
    assert ver[0].isdigit()


def test_package_version_matches_the_single_source():
    # The whole point: no drift between __version__ and pyproject.
    assert mesea_operator.__version__ == v.read_pyproject_version(ROOT)


def test_scan_project_version_ignores_other_tables():
    text = "\n".join(
        [
            "[build-system]",
            'requires = ["setuptools>=68"]',
            "",
            "[project]",
            'name = "mesea-operator"',
            'version = "9.9.9"',
            "",
            "[tool.pytest.ini_options]",
            'version = "0.0.0"',
        ]
    )
    assert v._scan_project_version(text) == "9.9.9"


def test_scan_project_version_missing_raises():
    with pytest.raises(KeyError):
        v._scan_project_version('[project]\nname = "mesea-operator"\n')


def test_resolve_prefers_installed_metadata(monkeypatch):
    monkeypatch.setattr(v.importlib.metadata, "version", lambda name: "1.2.3")
    assert v._resolve() == "1.2.3"


def test_resolve_falls_back_to_baked_when_not_installed(monkeypatch):
    monkeypatch.setattr(v.importlib.metadata, "version", _package_not_found)
    monkeypatch.setattr(v, "_baked_version", lambda: "4.5.6")
    assert v._resolve() == "4.5.6"


def test_resolve_falls_back_to_pyproject_last(monkeypatch):
    monkeypatch.setattr(v.importlib.metadata, "version", _package_not_found)
    monkeypatch.setattr(v, "_baked_version", lambda: None)
    assert v._resolve() == v.read_pyproject_version(ROOT)


def test_baked_version_reads_generated_module(monkeypatch):
    fake = types.ModuleType("mesea_operator._baked_version")
    fake.VERSION = "7.8.9"
    monkeypatch.setitem(sys.modules, "mesea_operator._baked_version", fake)
    assert v._baked_version() == "7.8.9"


def test_baked_version_absent_in_a_plain_source_checkout():
    if BAKED_FILE.exists():
        pytest.skip("a local PyInstaller build left a generated _baked_version.py")
    assert v._baked_version() is None
