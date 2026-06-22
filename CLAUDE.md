# CLAUDE.md — mesea-operator-app

The **Mesea Operator** launcher: a Python/Tk desktop app for account managers. It
runs the OAuth 2.0 + PKCE flow against the Mesea API, stores the token in the OS
credential store, bridges it into Claude Code's MCP config, and launches Claude
Code at the `mesea-operator` workspace.

## Layout & conventions

- `mesea_operator/` — app modules. **Tk is imported ONLY by `ui.py` and the entry
  point.** Every other module (`oauth_client`, `credential_store`, `claude_bridge`,
  `workspace`, `updater`, `startup`, `prompts`, `config`, …) must stay importable
  and unit-testable on headless machines (no tkinter). Keep pure decision logic out
  of `ui.py` (e.g. `startup.py` owns the token-outcome model so it's testable).
- `tests/` — pytest. Run `.venv/bin/python -m pytest -q` (or `python -m pytest -q`).
- `packaging/` — PyInstaller spec (`mesea_operator.spec`) + Windows Inno Setup
  installer (`windows/installer.iss`).
- Keep files ≤ 300 lines — extract a module when one grows (as `startup.py` /
  `prompts.py` were split out of `ui.py`).

## Releasing — cut a new version after merging any change worth shipping

**A merged PR does not reach account managers by itself — you must release.** When
you land a fix or feature here, also bump the version and tag a release:

1. **Bump the version in ALL THREE places** — they must stay in sync (PRs routinely
   bump `__init__.py` + `APP_VERSION` but forget `pyproject.toml`):
   - `pyproject.toml` → `version`
   - `mesea_operator/__init__.py` → `__version__` (what `--version` and the in-app
     updater read)
   - `.github/workflows/release.yml` → `env.APP_VERSION` (names the `.deb` / Windows
     installer)
2. Merge the bump (squash). It can ride along with the feature PR, or be its own
   `chore(release): bump to X.Y.Z` PR.
3. **Tag the merge commit and push the tag — this is what triggers the release:**
   ```bash
   git tag vX.Y.Z <merge-sha> && git push origin vX.Y.Z
   ```
   `.github/workflows/release.yml` (`on: push: tags: ["v*"]`) builds the PyInstaller
   binaries for Windows/macOS/Linux and publishes a GitHub Release with the assets
   the in-app updater pulls from.

Versioning so far is sequential patch bumps under `0.3.x`. The git tag (`vX.Y.Z`)
must match the three version fields exactly.
