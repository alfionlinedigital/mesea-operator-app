"""Tk dialog to find and pick the AM's demo tablet + phone device IDs.

Opened from the main window. A search box re-queries ``devices.fetch_devices``
on a worker thread (results posted back via ``root.after`` so Tk never blocks),
and two comboboxes select the tablet and phone from the results. Save persists
the chosen IDs to ``device_store`` (keyring), to be injected into the launched
Claude session at the next launch via the settings-env bridge.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import config, device_store, devices


def _device_label(d: dict) -> str:
    """A human row label tolerant of DeviceResponse field renames."""
    name = d.get("device_name") or d.get("name") or "(fără nume)"
    serial = d.get("serial") or d.get("serial_number")
    return f"{name} — {serial}" if serial else str(name)


class DevicePickerDialog:
    def __init__(self, parent: tk.Misc, token: str) -> None:
        self._token = token
        self._devices: list[dict] = []

        self.win = tk.Toplevel(parent)
        self.win.title("Dispozitive demo")
        self.win.transient(parent)
        self.win.geometry("460x320")
        self.win.minsize(420, 300)

        frame = ttk.Frame(self.win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Caută după nume sau serie:").pack(anchor="w")
        self.search_var = tk.StringVar()
        search = ttk.Entry(frame, textvariable=self.search_var)
        search.pack(fill="x", pady=(2, 4))
        search.bind("<Return>", lambda _e: self._reload())

        self.unassigned_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Doar dispozitive neasignate",
            variable=self.unassigned_var,
            command=self._reload,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(frame, text="Tabletă:").pack(anchor="w")
        self.tablet_box = ttk.Combobox(frame, state="readonly")
        self.tablet_box.pack(fill="x", pady=(2, 8))

        ttk.Label(frame, text="Telefon:").pack(anchor="w")
        self.phone_box = ttk.Combobox(frame, state="readonly")
        self.phone_box.pack(fill="x", pady=(2, 8))

        self.status = ttk.Label(frame, text="", foreground="grey", wraplength=420)
        self.status.pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="Reîncarcă", command=self._reload).pack(side="left")
        ttk.Button(btns, text="Salvează", command=self._save, style="Accent.TButton").pack(
            side="right"
        )

        self._preselect = device_store.load()
        self._reload()

    # --- data loading (worker thread → Tk via after) -------------------------
    def _reload(self) -> None:
        q = self.search_var.get().strip() or None
        unassigned = True if self.unassigned_var.get() else None
        self.status.config(text="Se încarcă…")

        def work() -> None:
            try:
                found = devices.fetch_devices(self._token, q=q, unassigned=unassigned)
            except devices.DevicesError as exc:
                self._post(lambda: self._on_error(str(exc)))
                return
            self._post(lambda: self._populate(found))

        threading.Thread(target=work, daemon=True).start()

    def _post(self, fn) -> None:
        """Marshal a callback onto the Tk loop, tolerating a dialog closed mid-fetch."""
        try:
            self.win.after(0, fn)
        except tk.TclError:
            pass  # window was destroyed while the worker was in flight

    def _on_error(self, message: str) -> None:
        self.status.config(text=f"Eroare: {message}")

    def _populate(self, found: list[dict]) -> None:
        self._devices = found
        labels = [_device_label(d) for d in found]
        self.tablet_box["values"] = labels
        self.phone_box["values"] = labels
        self._restore_selection(self.tablet_box, self._preselect.tablet_id)
        self._restore_selection(self.phone_box, self._preselect.phone_id)
        self.status.config(
            text=f"{len(found)} dispozitive." if found else "Niciun dispozitiv găsit."
        )

    def _restore_selection(self, box: ttk.Combobox, device_id: str | None) -> None:
        if not device_id:
            return
        for i, d in enumerate(self._devices):
            if str(d.get("id")) == str(device_id):
                box.current(i)
                return

    # --- save ----------------------------------------------------------------
    def _selected_id(self, box: ttk.Combobox) -> str | None:
        idx = box.current()
        if idx < 0 or idx >= len(self._devices):
            return None
        raw = self._devices[idx].get("id")
        return str(raw) if raw is not None else None

    def _save(self) -> None:
        # Fall back to the previously-saved id when a box has no current
        # selection — e.g. the saved device was filtered out of the active
        # search — so saving a change to one slot can't silently wipe the other.
        tablet_id = self._selected_id(self.tablet_box) or self._preselect.tablet_id
        phone_id = self._selected_id(self.phone_box) or self._preselect.phone_id
        device_store.store(tablet_id, phone_id)
        messagebox.showinfo(
            config.APP_NAME,
            "Dispozitivele demo au fost salvate. Vor fi folosite la următoarea pornire.",
            parent=self.win,
        )
        self.win.destroy()
