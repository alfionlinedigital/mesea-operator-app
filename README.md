# Mesea Operator

Desktop launcher for Mesea **account managers**. It runs the OAuth login,
stores your access token in the OS credential store (Windows Credential
Manager / macOS Keychain / Linux SecretService), bridges it into Claude
Code's config, keeps the `mesea-operator` workspace up to date, and starts
Claude — so you go from a clean machine to "ready to demo" without ever
typing a token.

Built with Python + Tk (ttk + [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme)),
shipped as a single self-contained executable for Windows, macOS, and Linux.

## Install (account managers)

Each release ships **two channels** per OS — pick whichever you prefer; both
run the same app:

| OS | Installed (recommended) | Portable (single file) |
| --- | --- | --- |
| Windows | `mesea-operator-windows-setup.exe` | `mesea-operator-windows.exe` |
| macOS | `mesea-operator-macos.dmg` | `mesea-operator-macos` |
| Linux/Debian | `mesea-operator-linux.deb` | `mesea-operator-linux` |

1. Download a build for your OS from the [latest release](https://github.com/alfionlinedigital/mesea-operator-app/releases/latest).
2. Run it. (Unsigned for now — Windows SmartScreen / macOS Gatekeeper will
   warn the first time; choose "Run anyway" / right-click → Open.)
3. Click **Conectează-te**, log in with your Mesea account (2FA), and approve
   the access scopes. Done — click **Pornește Mesea Operator** to start.

You never paste or see a token; it's minted by the login and stored encrypted.

### Updates know how you installed

The app detects whether it's running as an **installed** copy or a **portable**
binary and points you at the matching download when a new release is out — the
installer if you installed, the bare binary if you're portable (so you never
end up with two managed copies). To make the swap clean:

- **Installer** — re-running the Windows setup while the app is open detects the
  running instance (via a named mutex) and asks you to close it first.
- **Portable** — launching a portable build detects other running copies and
  offers to close them, freeing the on-disk file to be replaced.

## How auth works (no token ever touches the chat)

OAuth 2.0 Authorization Code + PKCE (RFC 8252 native-app flow):

```
app → PKCE + loopback listener → browser → manager.mesea.ro login + 2FA + consent
    → ?code=… to 127.0.0.1 → POST /api/v1/oauth/token (code + verifier)
    → access token → OS credential store
```

At launch the token is written into `~/.claude/settings.json` so Claude's MCP
transport can use it, and **scrubbed when Claude exits** (and on next launch,
as a crash-safe net).

## Configuration overrides

All endpoints default to production and are overridable via environment
variables (for staging / local dev): `MESEA_MCP_URL`, `MESEA_AUTHORIZE_URL`,
`MESEA_TOKEN_URL`, `MESEA_REVOKE_URL`, `MESEA_ME_URL`, `MESEA_WORKSPACE_URL`.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate   # (Debian: apt install python3-venv python3-tk)
pip install -r requirements.txt pytest
python -m pytest tests/ -q       # unit + e2e OAuth-flow tests (no backend needed)
python -m mesea_operator         # run the app (needs Tk)
```

Tk is imported only by `mesea_operator/ui.py`; every other module is
importable and testable without Tk (CI runs the suite on Linux).

## Build locally

```bash
pip install pyinstaller
pyinstaller packaging/mesea_operator.spec --noconfirm
# → dist/mesea-operator(.exe)
```

CI (`.github/workflows/release.yml`) builds all three OSes on tag push and
attaches the binaries to the GitHub release.

## Status

OAuth client, credential storage, Claude bridge, workspace sync, self-update,
and the cross-platform release pipeline are in place. Full end-to-end login
goes live once the backend OAuth endpoints (`/api/v1/oauth/*`) are deployed.
Code signing is a planned follow-up (needs org certs as repo secrets).
