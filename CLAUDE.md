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

1. **Bump the version in the ONE place that owns it — `pyproject.toml`
   `[project].version`.** Nothing else hardcodes the version:
   - `mesea_operator/__init__.py` → `__version__` is resolved at runtime by
     `mesea_operator/version.py` (installed dist metadata → the build-time bake →
     pyproject, in that order), so `--version` and the in-app updater track
     pyproject automatically.
   - `.github/workflows/release.yml` derives `APP_VERSION` (the `.deb` / Windows
     installer name) from pyproject in its `version` job — no `env` to edit.
   - The frozen binary reads a `_baked_version.py` that the PyInstaller spec
     writes from pyproject at build time (gitignored); the macOS bundle's
     `CFBundleShortVersionString` comes from the same value.
2. Merge the bump (squash). It can ride along with the feature PR, or be its own
   `chore(release): bump to X.Y.Z` PR.
3. **Tag the merge commit and push the tag — this is what triggers the release:**
   ```bash
   git tag vX.Y.Z <merge-sha> && git push origin vX.Y.Z
   ```
   `.github/workflows/release.yml` (`on: push: tags: ["v*"]`) first **asserts the
   tag equals the pyproject version** (a mismatch fails the release, so a forgotten
   bump can't ship mislabelled installers), then builds the PyInstaller binaries for
   Windows/macOS/Linux and publishes a GitHub Release with the assets the in-app
   updater pulls from.

Versioning so far is sequential patch bumps under `0.3.x`. The git tag (`vX.Y.Z`)
must match the pyproject version exactly — CI enforces it.
