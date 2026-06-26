"""Import smoke for the Tk view modules.

``ui.py`` / ``windowing.py`` are otherwise never imported by the suite or the
``--version`` smoke, so a renamed or missing symbol there would only surface at
an account manager's launch. Importing them in CI (where Tk + sv-ttk are
installed) catches that early; locally the modules are skipped if Tk/sv-ttk
aren't present.
"""

import importlib

import pytest


@pytest.mark.parametrize("module", ["mesea_operator.ui", "mesea_operator.windowing"])
def test_view_module_imports(module):
    pytest.importorskip("tkinter")
    pytest.importorskip("sv_ttk")
    importlib.import_module(module)
