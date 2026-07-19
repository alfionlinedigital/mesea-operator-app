"""Mesea Operator — account-manager launcher for the Mesea platform.

Runs the OAuth 2.0 Authorization Code + PKCE flow against the Mesea API,
stores the resulting token in the OS credential store, bridges it into
Claude Code's MCP config, and launches the Claude desktop app at the
mesea-operator workspace.

Tk is imported only by ``mesea_operator.ui`` and the entry point, so every
other module (oauth_client, credential_store, claude_bridge, workspace,
updater, config) is importable and unit-testable on machines without Tk.

The version is NOT hardcoded here — it is resolved from the single source
(``pyproject.toml``) by ``mesea_operator.version``. See that module for the
resolution order (installed metadata → frozen bake → pyproject).
"""

from mesea_operator.version import __version__

__all__ = ["__version__"]
