"""sv-ttk desktop UI — the only module that imports Tk.

Thin view: every action delegates to the logic modules (oauth_client,
credential_store, claude_bridge, workspace, updater, api). Long-running work
(OAuth, git, launch) runs on worker threads and posts status back to the Tk
main loop via ``root.after`` so the window never freezes.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import sv_ttk

from . import __version__, api, claude_bridge, config, credential_store, oauth_client, updater, workspace


class OperatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"{config.APP_NAME}")
        root.geometry("480x340")
        root.minsize(440, 320)

        self._token: str | None = None
        self._label: str | None = None

        wrap = ttk.Frame(root, padding=24)
        wrap.pack(fill="both", expand=True)

        ttk.Label(wrap, text=config.APP_NAME, font=("", 18, "bold")).pack(anchor="w")
        self.status = ttk.Label(wrap, text="Se inițializează…", wraplength=420)
        self.status.pack(anchor="w", pady=(6, 18))

        self.launch_btn = ttk.Button(wrap, text="Pornește Mesea Operator", command=self.on_launch)
        self.launch_btn.pack(fill="x", pady=4)
        self.launch_btn.config(style="Accent.TButton")

        self.auth_btn = ttk.Button(wrap, text="Conectează-te", command=self.on_authorize)
        self.auth_btn.pack(fill="x", pady=4)

        self.signout_btn = ttk.Button(wrap, text="Deconectare", command=self.on_signout)
        self.signout_btn.pack(fill="x", pady=4)

        ttk.Label(wrap, text=f"v{__version__}", foreground="grey").pack(side="bottom", anchor="e")

        # Safety: scrub any token left in settings.json by a prior crashed run.
        claude_bridge.scrub_token(claude_bridge.settings_path())
        self._refresh_from_store()
        self.root.after(200, self._startup_tasks)

    # --- state ---------------------------------------------------------------
    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status.config(text=text))

    def _refresh_from_store(self) -> None:
        cred = credential_store.load()
        if cred:
            self._token = cred.access_token
            self._label = cred.account_label
            who = cred.account_label or "cont necunoscut"
            exp = f" · expiră {cred.expires_at[:10]}" if cred.expires_at else ""
            self.status.config(text=f"Conectat ca {who}{exp}")
            self._set_connected(True)
        else:
            self._token = None
            self.status.config(text="Neconectat. Apasă „Conectează-te”.")
            self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        self.launch_btn.state(["!disabled"] if connected else ["disabled"])
        self.signout_btn.state(["!disabled"] if connected else ["disabled"])
        self.auth_btn.config(text="Reautentificare" if connected else "Conectează-te")

    # --- background startup --------------------------------------------------
    def _startup_tasks(self) -> None:
        def work() -> None:
            cred = credential_store.load()
            if cred:
                ws = workspace.ensure_workspace(cred.access_token)
                if ws.status == "error":
                    self._set_status(f"Atenție workspace: {ws.detail}")
            up = updater.check_for_update()
            if up.available:
                self.root.after(0, lambda: self._prompt_update(up))

        threading.Thread(target=work, daemon=True).start()

    def _prompt_update(self, up: updater.UpdateInfo) -> None:
        if messagebox.askyesno(
            config.APP_NAME,
            f"O versiune nouă este disponibilă ({up.latest_version}). O deschizi în browser?",
        ) and up.download_url:
            import webbrowser

            webbrowser.open(up.download_url)

    # --- actions -------------------------------------------------------------
    def on_authorize(self) -> None:
        self.auth_btn.state(["disabled"])
        self._set_status("Se deschide browserul pentru autentificare…")

        def work() -> None:
            try:
                result = oauth_client.run_authorization_flow()
                label = api.fetch_identity(result.access_token)
                credential_store.store(result.access_token, result.expires_at, label)
            except oauth_client.OAuthError as exc:
                self.root.after(0, lambda: messagebox.showerror(config.APP_NAME, str(exc)))
            finally:
                self.root.after(0, self.auth_btn.state, ["!disabled"])
                self.root.after(0, self._refresh_from_store)

        threading.Thread(target=work, daemon=True).start()

    def on_launch(self) -> None:
        cred = credential_store.load()
        if not cred:
            messagebox.showwarning(config.APP_NAME, "Conectează-te mai întâi.")
            return
        exe = claude_bridge.find_claude_executable()
        if not exe:
            messagebox.showinfo(
                config.APP_NAME,
                "Aplicația Claude nu a fost găsită. Token-ul a fost pregătit; "
                "deschide Claude manual și alege folderul mesea-operator.",
            )
            claude_bridge.write_token(claude_bridge.settings_path(), cred.access_token, config.MCP_URL)
            return

        claude_bridge.write_token(claude_bridge.settings_path(), cred.access_token, config.MCP_URL)
        self._set_status("Se actualizează workspace-ul…")

        def work() -> None:
            ws = workspace.ensure_workspace(cred.access_token)
            if ws.status == "error":
                claude_bridge.scrub_token(claude_bridge.settings_path())
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        config.APP_NAME, f"Workspace indisponibil: {ws.detail}"
                    ),
                )
                self.root.after(0, self._refresh_from_store)
                return

            self._set_status("Se pornește Claude…")
            try:
                proc = claude_bridge.launch_claude(exe, str(ws.path))
                proc.wait()
            finally:
                claude_bridge.scrub_token(claude_bridge.settings_path())
                self._set_status("Claude s-a închis. Token-ul a fost retras din config.")
                self.root.after(0, self._refresh_from_store)

        threading.Thread(target=work, daemon=True).start()

    def on_signout(self) -> None:
        cred = credential_store.load()
        if cred:
            threading.Thread(target=lambda: api.revoke(cred.access_token), daemon=True).start()
        credential_store.clear()
        claude_bridge.scrub_token(claude_bridge.settings_path())
        self._refresh_from_store()


def main() -> None:
    root = tk.Tk()
    sv_ttk.set_theme("light")
    OperatorApp(root)
    root.mainloop()
