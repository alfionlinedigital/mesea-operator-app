"""Modal-dialog presenters extracted out of the thin view (``ui.py``).

These own the Romanian copy and the messagebox plumbing for two self-contained
flows — the portable single-instance guard and the self-update offer — so the
view stays focused on wiring and state. They import Tk's ``messagebox`` only;
no widget state, which keeps ``ui.py`` under the file-size cap.
"""

from __future__ import annotations

import webbrowser
from tkinter import messagebox

from . import config, install_context, instance_guard, updater


def enforce_single_instance(context: str) -> None:
    """Portable builds have no installer to gate the binary swap, so detect
    other running copies and offer to close them (frees the on-disk exe for a
    self-update and avoids two windows fighting over the same token)."""
    if context != install_context.CONTEXT_PORTABLE:
        return
    try:
        others = instance_guard.find_other_instances()
    except Exception:
        return  # process enumeration is best-effort; never block startup
    if not others:
        return

    names = ", ".join(sorted({o.name or f"PID {o.pid}" for o in others}))
    if not messagebox.askyesno(
        config.APP_NAME,
        f"Alte instanțe Mesea Operator rulează deja ({names}). "
        "Le închizi ca să continui cu această versiune?",
    ):
        return

    results = instance_guard.terminate([o.pid for o in others])
    failed = [pid for pid, closed in results.items() if not closed]
    if failed:
        messagebox.showwarning(
            config.APP_NAME,
            "Nu am putut închide toate instanțele "
            f"(PID: {', '.join(map(str, failed))}). Închide-le manual.",
        )


def prompt_update(up: updater.UpdateInfo) -> None:
    """Offer the user the newer build, opening its download URL in a browser."""
    kind = (
        "instalatorul"
        if up.context == install_context.CONTEXT_INSTALLED
        else "versiunea portabilă"
    )
    if (
        messagebox.askyesno(
            config.APP_NAME,
            f"O versiune nouă este disponibilă ({up.latest_version}). "
            f"Deschizi {kind} în browser?",
        )
        and up.download_url
    ):
        webbrowser.open(up.download_url)
