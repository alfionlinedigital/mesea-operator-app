"""Unit tests for the pure row-label builder of the demo-device picker.

Only ``_device_label`` is exercised here — it's a pure dict→str function, so no
Tk root is created. Importing the module needs the Tk library present (the suite
already runs with python3-tk installed, per README), but never opens a window.
"""

import pytest

tk = pytest.importorskip("tkinter")  # skip cleanly on a Tk-less runner

from mesea_operator import device_picker  # noqa: E402


def test_label_shows_business_worker_and_mdm():
    label = device_picker._device_label(
        {
            "device_name": "Galaxy Tab",
            "serial_number": "SN123",
            "business_name": "Le Sorelle",
            "worker_name": "Bucătar",
            "mdm_name": "Scalefusion",
        }
    )
    assert "Galaxy Tab" in label
    assert "SN123" in label
    assert "Le Sorelle" in label
    assert "Bucătar" in label
    assert "Scalefusion" in label


def test_label_marks_unassigned_business():
    label = device_picker._device_label({"device_name": "Tab", "mdm_name": "Hexnode"})
    assert "neasignat" in label
    assert "Hexnode" in label


def test_label_marks_missing_mdm():
    label = device_picker._device_label(
        {"device_name": "Tab", "business_name": "Le Sorelle"}
    )
    assert "fără MDM" in label


def test_label_omits_worker_when_absent():
    label = device_picker._device_label(
        {"device_name": "Tab", "business_name": "Le Sorelle", "mdm_name": "MDM"}
    )
    assert "Le Sorelle" in label
    assert " / " not in label  # no worker slash-separator when unassigned to worker


def test_label_tolerates_minimal_device():
    label = device_picker._device_label({})
    assert "(fără nume)" in label
    assert "neasignat" in label
    assert "fără MDM" in label
