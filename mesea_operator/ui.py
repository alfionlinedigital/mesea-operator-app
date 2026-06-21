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

from . import (
    __version__,
    api,
    claude_bridge,
    config,
    credential_store,
    device_picker,
    device_store,
    install_context,
    instance_guard,
    oauth_client,
    updater,
    workspace,
)


class OperatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"{config.APP_NAME}")
        root.geometry("480x340")
        root.minsize(440, 320)

        self._token: str | None = None
        self._label: str | None = None
        self._context = install_context.detect_context()

        # Hold the named mutex so the Windows installer can detect this running
        # instance and ask the user to close it before an upgrade (no-op off
        # Windows). Portable builds have no installer gate, so they enforce
        # single-instance themselves below.
        instance_guard.acquire_singleton()

        wrap = ttk.Frame(root, padding=24)
        wrap.pack(fill="both", expand=True)

        ttk.Label(wrap, text=config.APP_NAME, font=("", 18, "bold")).pack(anchor="w")
        self.status = ttk.Label(wrap, text="Se inițializează…", wraplength=420)
        self.status.pack(anchor="w", pady=(6, 18))

        self.launch_btn = ttk.Button(wrap, text="Pornește Mesea Operator", command=self.on_launch)
        self.launch_btn.pack(fill="x", pady=4)
        self.launch_btn.config(style="Accent.TButton")

        self.resume_btn = ttk.Button(
            wrap, text="Reia o conversație", command=self.on_resume
        )
        self.resume_btn.pack(fill="x", pady=4)

        self.auth_btn = ttk.Button(wrap, text="Conectează-te", command=self.on_authorize)
        self.auth_btn.pack(fill="x", pady=4)

        self.devices_btn = ttk.Button(wrap, text="Dispozitive demo", command=self.on_devices)
        self.devices_btn.pack(fill="x", pady=4)

        self.signout_btn = ttk.Button(wrap, text="Deconectare", command=self.on_signout)
        self.signout_btn.pack(fill="x", pady=4)

        ttk.Label(wrap, text=f"v{__version__}", foreground="grey").pack(side="bottom", anchor="e")

        # Safety: scrub any token / demo-device IDs left in settings.json by a
        # prior crashed run before they can leak into an unrelated session.
        claude_bridge.scrub_token(claude_bridge.settings_path())
        claude_bridge.scrub_demo_devices(claude_bridge.settings_path())
        self._refresh_from_store()
        self.root.after(150, self._enforce_single_instance)
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
        self.resume_btn.state(["!disabled"] if connected else ["disabled"])
        self.signout_btn.state(["!disabled"] if connected else ["disabled"])
        self.devices_btn.state(["!disabled"] if connected else ["disabled"])
        self.auth_btn.config(text="Reautentificare" if connected else "Conectează-te")

    # --- single-instance guard (portable) ------------------------------------
    def _enforce_single_instance(self) -> None:
        """Portable builds have no installer to gate the binary swap, so detect
        other running copies and offer to close them (frees the on-disk exe for
        a self-update and avoids two windows fighting over the same token)."""
        if self._context != install_context.CONTEXT_PORTABLE:
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

    # --- background startup --------------------------------------------------
    def _startup_tasks(self) -> None:
        def work() -> None:
            cred = credential_store.load()
            if cred and not api.is_token_valid(cred.access_token):
                self.root.after(0, self._block_invalid_token)
                up = updater.check_for_update(context=self._context)
                if up.available:
                    self.root.after(0, lambda: self._prompt_update(up))
                return
            if cred:
                ws = workspace.ensure_workspace(cred.access_token)
                if ws.status == "error":
                    self._set_status(f"Atenție workspace: {ws.detail}")
            up = updater.check_for_update(context=self._context)
            if up.available:
                self.root.after(0, lambda: self._prompt_update(up))

        threading.Thread(target=work, daemon=True).start()

    def _block_invalid_token(self) -> None:
        """Stored token is expired/revoked: block the main flow and prompt re-auth.

        We disable launch/resume/devices (but keep the auth button live) and tell
        the AM to re-authorize. The token is not cleared so the account label stays
        visible; a successful re-authorization overwrites it.
        """
        self._set_connected(False)
        self.status.config(
            text="Sesiunea a expirat sau a fost revocată. "
            "Apasă „Reautentificare” pentru a te conecta din nou."
        )
        self.auth_btn.config(text="Reautentificare")
        messagebox.showwarning(
            config.APP_NAME,
            "Token-ul tău nu mai este valid (expirat sau revocat). "
            "Reautentifică-te (rulează din nou autentificarea OAuth) "
            "pentru a continua.",
        )

    def _prompt_update(self, up: updater.UpdateInfo) -> None:
        kind = (
            "instalatorul" if up.context == install_context.CONTEXT_INSTALLED else "versiunea portabilă"
        )
        if messagebox.askyesno(
            config.APP_NAME,
            f"O versiune nouă este disponibilă ({up.latest_version}). "
            f"Deschizi {kind} în browser?",
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
        self._launch(resume=False)

    def on_resume(self) -> None:
        """Start Claude Code with ``--resume`` so the AM can pick a prior
        conversation in the operator workspace to continue."""
        self._launch(resume=True)

    def _launch(self, resume: bool) -> None:
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
            self._stage_session_env(cred.access_token)
            return

        self._stage_session_env(cred.access_token)
        self._set_status("Se actualizează workspace-ul…")

        def work() -> None:
            ws = workspace.ensure_workspace(cred.access_token)
            if ws.status == "error":
                self._scrub_session_env()
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
                proc = claude_bridge.launch_claude(exe, str(ws.path), resume=resume)
                proc.wait()
            finally:
                self._scrub_session_env()
                self._set_status("Claude s-a închis. Token-ul a fost retras din config.")
                self.root.after(0, self._refresh_from_store)

        threading.Thread(target=work, daemon=True).start()

    def _stage_session_env(self, token: str) -> None:
        """Write the token + saved demo-device IDs into the Claude settings env."""
        path = claude_bridge.settings_path()
        claude_bridge.write_token(path, token, config.MCP_URL)
        chosen = device_store.load()
        claude_bridge.write_demo_devices(path, chosen.tablet_id, chosen.phone_id)

    def _scrub_session_env(self) -> None:
        path = claude_bridge.settings_path()
        claude_bridge.scrub_token(path)
        claude_bridge.scrub_demo_devices(path)

    def on_devices(self) -> None:
        cred = credential_store.load()
        if not cred:
            messagebox.showwarning(config.APP_NAME, "Conectează-te mai întâi.")
            return
        device_picker.DevicePickerDialog(self.root, cred.access_token)

    def on_signout(self) -> None:
        cred = credential_store.load()
        if cred:
            threading.Thread(target=lambda: api.revoke(cred.access_token), daemon=True).start()
        credential_store.clear()
        self._scrub_session_env()
        self._refresh_from_store()


def main() -> None:
    root = tk.Tk()
    sv_ttk.set_theme("light")
    OperatorApp(root)
    root.mainloop()
