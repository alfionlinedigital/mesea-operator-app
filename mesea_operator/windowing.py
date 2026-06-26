"""Toplevel sizing for the Tk launcher.

A view-layer helper (imports Tk, like ``prompts``): it can only run against a
real window, so it lives outside the headless logic modules.
"""

from __future__ import annotations

import tkinter as tk


def grow_to_fit(root: tk.Misc, min_width: int = 480) -> None:
    """Grow the window — and its minimum size — to fit its content so nothing is
    ever clipped, without shrinking a window the user has already enlarged.

    Call after any change that can make the content taller (e.g. a status line
    wrapping to two lines); it is cheap and idempotent.
    """
    root.update_idletasks()
    width = max(min_width, root.winfo_reqwidth())
    height = root.winfo_reqheight()
    root.minsize(width, height)
    if width > root.winfo_width() or height > root.winfo_height():
        root.geometry(f"{width}x{height}")
