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
    logs,
    oauth_client,
    prompts,
    startup,
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
        self.status.pack(anchor="w", pady=(6, 2))
        # Dedicated workspace-state line (separate from the account/connection line).
        self.ws_status = ttk.Label(wrap, text="", foreground="grey", wraplength=420)
        self.ws_status.pack(anchor="w", pady=(0, 14))

        self.launch_btn = ttk.Button(wrap, text="Pornește Mesea Operator", command=self.on_launch)
        self.launch_btn.pack(fill="x", pady=4)
        self.launch_btn.config(style="Accent.TButton")

        self.resume_btn = ttk.Button(
            wrap, text="Reia o conversație", command=self.on_resume
        )
        self.resume_btn.pack(fill="x", pady=4)

        # Locked until the startup probe confirms the stored token is valid —
        # a present credential alone must never unlock a launch (fail-open gap).
        self._set_launch_enabled(False)

        self.auth_btn = ttk.Button(wrap, text="Conectează-te", command=self.on_authorize)
        self.auth_btn.pack(fill="x", pady=4)

        self.devices_btn = ttk.Button(wrap, text="Dispozitive demo", command=self.on_devices)
        self.devices_btn.pack(fill="x", pady=4)

        self.signout_btn = ttk.Button(wrap, text="Deconectare", command=self.on_signout)
        self.signout_btn.pack(fill="x", pady=4)

        # Always available (no token needed) — opens the on-disk developer log.
        ttk.Button(wrap, text="Loguri dezvoltator", command=logs.open_logs).pack(fill="x", pady=4)

        ttk.Label(wrap, text=f"v{__version__}", foreground="grey").pack(side="bottom", anchor="e")

        # Safety: scrub any token / demo-device IDs left in settings.json by a
        # prior crashed run before they can leak into an unrelated session.
        claude_bridge.scrub_token(claude_bridge.settings_path())
        claude_bridge.scrub_demo_devices(claude_bridge.settings_path())
        self._refresh_from_store()
        self.root.after(150, lambda: prompts.enforce_single_instance(self._context))
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
        """Toggle the account-level chrome (sign-out / devices / auth label).

        Launch + resume are deliberately NOT touched here: a stored credential
        is not proof the token still works, so they stay locked until the
        startup probe confirms the token (``_set_launch_enabled``). This keeps
        the fail-open window — buttons live ~200ms before validation — closed.
        """
        self.signout_btn.state(["!disabled"] if connected else ["disabled"])
        self.devices_btn.state(["!disabled"] if connected else ["disabled"])
        self.auth_btn.config(text="Reautentificare" if connected else "Conectează-te")
        if not connected:
            self._set_launch_enabled(False)

    def _set_launch_enabled(self, enabled: bool) -> None:
        """Enable launch + resume only when the token is DEFINITIVELY valid."""
        self.launch_btn.state(["!disabled"] if enabled else ["disabled"])
        self.resume_btn.state(["!disabled"] if enabled else ["disabled"])

    # --- background startup --------------------------------------------------
    def _startup_tasks(self) -> None:
        """Validate the stored token and check for updates on one worker thread.

        Ordering is deterministic: the token outcome is applied first (a blocked
        token takes precedence over an update prompt), then — and only once — an
        available update is surfaced afterwards, so the two dialogs can never
        stack in an undefined order. Launch + resume are enabled ONLY on a
        definitively valid token; an unreachable server fails closed quietly.
        """

        def work() -> None:
            cred = credential_store.load()
            outcome = startup.evaluate_token(cred.access_token if cred else None)
            self.root.after(0, lambda: self._apply_token_outcome(outcome, cred))
            up = updater.check_for_update(context=self._context)
            if up.available:
                self.root.after(0, lambda: prompts.prompt_update(up))

        threading.Thread(target=work, daemon=True).start()

    def _apply_token_outcome(
        self, outcome: startup.TokenOutcome, cred: credential_store.StoredCredential | None
    ) -> None:
        """Marshal the worker's token verdict onto the Tk main loop (main-thread)."""
        if outcome is startup.TokenOutcome.VALID:
            self._set_launch_enabled(True)
            if cred:
                threading.Thread(
                    target=lambda: self._sync_workspace(cred.access_token), daemon=True
                ).start()
        elif outcome is startup.TokenOutcome.INVALID:
            self._block_invalid_token()
        elif outcome is startup.TokenOutcome.UNREACHABLE:
            self._set_launch_enabled(False)
            self.status.config(
                text="Nu am putut verifica sesiunea (server indisponibil). "
                "Verifică conexiunea și apasă „Reautentificare” pentru a reîncerca."
            )
        # NONE: not signed in — _refresh_from_store already set the prompt.

    def _sync_workspace(self, token: str) -> None:
        """Refresh the workspace in the background, reporting EVERY outcome on the
        dedicated workspace-status line (checking / updated / up-to-date / stale)."""
        self.root.after(0, lambda: self.ws_status.config(text="Se verifică workspace-ul…"))
        ws = workspace.ensure_workspace(token)
        message = startup.workspace_status_message(ws)
        self.root.after(0, lambda: self.ws_status.config(text=message))

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
                claude_bridge.scrub_session()
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
                claude_bridge.scrub_session()
                self._set_status("Claude s-a închis. Token-ul a fost retras din config.")
                self.root.after(0, self._refresh_from_store)

        threading.Thread(target=work, daemon=True).start()

    def _stage_session_env(self, token: str) -> None:
        """Stage the token + chosen demo-device IDs into the Claude settings env."""
        chosen = device_store.load()
        claude_bridge.stage_session(token, config.MCP_URL, chosen.tablet_id, chosen.phone_id)

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
        claude_bridge.scrub_session()
        self._refresh_from_store()


def main() -> None:
    root = tk.Tk()
    sv_ttk.set_theme("light")
    OperatorApp(root)
    root.mainloop()
