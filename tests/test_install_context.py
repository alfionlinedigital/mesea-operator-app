"""Unit tests for installed/portable detection and asset redirection."""

import pytest

from mesea_operator import install_context as ic


def test_unfrozen_run_is_portable():
    # A dev `python -m` run is never a packaged artifact, regardless of OS.
    assert ic.detect_context(frozen=False, exe_path="/anything", platform="linux") == ic.CONTEXT_PORTABLE
    assert (
        ic.detect_context(frozen=False, exe_path=r"C:\Program Files\Mesea Operator\x.exe", platform="win32")
        == ic.CONTEXT_PORTABLE
    )


# --- Windows -----------------------------------------------------------------
def test_windows_installed_when_exe_under_registry_install_location():
    ctx = ic.detect_context(
        frozen=True,
        platform="win32",
        exe_path=r"C:\Users\me\AppData\Local\Programs\Mesea Operator\mesea-operator.exe",
        win_install_location=r"C:\Users\me\AppData\Local\Programs\Mesea Operator",
    )
    assert ctx == ic.CONTEXT_INSTALLED


def test_windows_installed_via_program_files_fallback_without_registry():
    ctx = ic.detect_context(
        frozen=True,
        platform="win32",
        exe_path=r"C:\Program Files\Mesea Operator\mesea-operator.exe",
        win_install_location=None,
    )
    assert ctx == ic.CONTEXT_INSTALLED


def test_windows_portable_from_downloads():
    ctx = ic.detect_context(
        frozen=True,
        platform="win32",
        exe_path=r"C:\Users\me\Downloads\mesea-operator-windows.exe",
        win_install_location=None,
    )
    assert ctx == ic.CONTEXT_PORTABLE


def test_windows_portable_even_if_an_installed_copy_exists_elsewhere():
    # Registry points at the *installed* dir, but we're running the Downloads
    # copy — classify by the running exe, not by mere presence of an install.
    ctx = ic.detect_context(
        frozen=True,
        platform="win32",
        exe_path=r"C:\Users\me\Downloads\mesea-operator-windows.exe",
        win_install_location=r"C:\Program Files\Mesea Operator",
    )
    assert ctx == ic.CONTEXT_PORTABLE


# --- macOS -------------------------------------------------------------------
def test_macos_installed_inside_app_bundle():
    ctx = ic.detect_context(
        frozen=True,
        platform="darwin",
        exe_path="/Applications/Mesea Operator.app/Contents/MacOS/mesea-operator",
    )
    assert ctx == ic.CONTEXT_INSTALLED


def test_macos_portable_bare_binary():
    ctx = ic.detect_context(
        frozen=True, platform="darwin", exe_path="/Users/me/Downloads/mesea-operator-macos"
    )
    assert ctx == ic.CONTEXT_PORTABLE


# --- Linux -------------------------------------------------------------------
def test_linux_installed_from_system_prefix():
    assert (
        ic.detect_context(frozen=True, platform="linux", exe_path="/usr/bin/mesea-operator")
        == ic.CONTEXT_INSTALLED
    )


def test_linux_portable_from_home():
    assert (
        ic.detect_context(
            frozen=True, platform="linux", exe_path="/home/me/Downloads/mesea-operator-linux"
        )
        == ic.CONTEXT_PORTABLE
    )


# --- asset redirection -------------------------------------------------------
@pytest.mark.parametrize(
    "context,platform,expected",
    [
        (ic.CONTEXT_INSTALLED, "win32", "windows-setup.exe"),
        (ic.CONTEXT_PORTABLE, "win32", "windows.exe"),
        (ic.CONTEXT_INSTALLED, "darwin", "macos.dmg"),
        (ic.CONTEXT_PORTABLE, "darwin", "macos"),
        (ic.CONTEXT_INSTALLED, "linux", "linux.deb"),
        (ic.CONTEXT_PORTABLE, "linux", "linux"),
    ],
)
def test_asset_suffix_matrix(context, platform, expected):
    assert ic.asset_suffix(context, platform) == expected


def test_portable_suffix_never_matches_installer_asset():
    # endswith()-based selection in updater must not pick the setup/.dmg/.deb
    # when the portable suffix is in play.
    assert not "mesea-operator-windows-setup.exe".endswith(ic.asset_suffix(ic.CONTEXT_PORTABLE, "win32"))
    assert not "mesea-operator-macos.dmg".endswith(ic.asset_suffix(ic.CONTEXT_PORTABLE, "darwin"))
    assert not "mesea-operator-linux.deb".endswith(ic.asset_suffix(ic.CONTEXT_PORTABLE, "linux"))
