"""Central configuration constants and overridable endpoints.

Every value can be overridden via an environment variable (same name) so the
app can target staging or a local dev stack without a rebuild — matching the
``MESEA_MCP_URL`` override convention already used by the operator workspace's
``.mcp.json``.
"""

from __future__ import annotations

import os

APP_NAME = "Mesea Operator"

# OAuth client identity (the registered first-party `App` row on the backend).
CLIENT_ID = os.environ.get("MESEA_CLIENT_ID", "mesea-operator")

# Named server-side scope bundle requested at authorize time.
SCOPE_PROFILE = os.environ.get("MESEA_SCOPE_PROFILE", "operator")

# Authorization server endpoints.
# Authorize/consent lives on the 2FA-gated WP admin host; the token + revoke
# endpoints are the machine-to-machine PublicApi endpoints on the public host.
AUTHORIZE_URL = os.environ.get(
    "MESEA_AUTHORIZE_URL",
    "https://manager.mesea.ro/wp-admin/admin.php?page=alfi-oauth-authorize",
)
TOKEN_URL = os.environ.get("MESEA_TOKEN_URL", "https://mesea.ro/api/v1/oauth/token")
REVOKE_URL = os.environ.get("MESEA_REVOKE_URL", "https://mesea.ro/api/v1/oauth/revoke")

# Identity probe — confirms an issued token works without exposing its value.
ME_URL = os.environ.get("MESEA_ME_URL", "https://mesea.ro/api/v1/me")

# Admin-only device directory — backs the demo-device picker (tablet + phone).
DEVICES_URL = os.environ.get("MESEA_DEVICES_URL", "https://mesea.ro/api/v1/devices")

# Operator workspace bundle — the private mesea-operator skills/playbooks,
# served behind the OAuth wall as a gzipped tar. The launcher downloads it with
# the operator token instead of cloning the (private) repo, so account managers
# never need GitHub access.
WORKSPACE_URL = os.environ.get(
    "MESEA_WORKSPACE_URL", "https://mesea.ro/api/v1/operator-workspace"
)

# Default MCP endpoint written into the operator workspace env (the workspace
# .mcp.json reads ${MESEA_MCP_URL:-https://mesea.ro/api/v1/mcp}; we set it
# explicitly so a staging override flows through).
MCP_URL = os.environ.get("MESEA_MCP_URL", "https://mesea.ro/api/v1/mcp")

# This app's own repo, used for self-update checks against GitHub releases.
SELF_UPDATE_REPO = os.environ.get(
    "MESEA_SELF_UPDATE_REPO", "alfionlinedigital/mesea-operator-app"
)

# Bugsink (Sentry-compatible) error-reporting DSN. Embedded so account managers
# report errors out-of-the-box; override to redirect, or set empty to disable.
BUGSINK_DSN = os.environ.get(
    "BUGSINK_DSN", "https://0ad28fb647db48b493ad96f5ea0adbd3@alfidigital.bugsink.com/2"
)

# Named mutex the running app holds so the Windows installer can detect a live
# instance and ask the user to close it. Must stay in sync with the ``AppMutex``
# directive in ``packaging/windows/installer.iss``.
SINGLE_INSTANCE_MUTEX = "MeseaOperatorMutex"

# OS credential-store coordinates (keyring service + the env var Claude reads).
KEYRING_SERVICE = "mesea-operator"
TOKEN_ENV_VAR = "MESEA_API_TOKEN"
MCP_URL_ENV_VAR = "MESEA_MCP_URL"

# Demo-device env vars the setup-demo-devices / demo-onboarding skills read.
DEMO_TABLET_ENV_VAR = "DEMO_TABLET_DEVICE_ID"
DEMO_PHONE_ENV_VAR = "DEMO_PHONE_DEVICE_ID"

# Loopback flow tuning.
CALLBACK_PATH = "/cb"
AUTH_FLOW_TIMEOUT_SECONDS = 300
