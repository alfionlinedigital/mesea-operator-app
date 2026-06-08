"""OAuth 2.0 Authorization Code + PKCE client (RFC 8252 native app).

Stdlib only — no third-party HTTP deps — so it bundles cleanly into a
PyInstaller onefile and stays importable without Tk.

Flow:
  1. generate a PKCE verifier/challenge (S256) and a CSRF `state`
  2. bind a loopback listener on 127.0.0.1:<ephemeral>
  3. open the system browser to the authorize URL
  4. capture the redirect (?code=&state=), validate `state`
  5. exchange the code + verifier at the token endpoint
  6. return {access_token, expires_at, token_type}
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass

from . import config


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256.

    Verifier: 43-128 chars of unreserved URL-safe characters (RFC 7636 §4.1).
    Challenge: base64url(sha256(verifier)) without padding (§4.2).
    """
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthError(Exception):
    """Authorization or token-exchange failure surfaced to the UI."""


@dataclass
class TokenResult:
    access_token: str
    expires_at: str | None
    token_type: str = "Bearer"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    # Populated on the server instance by run_authorization_flow.
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != config.CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        self.server.captured = {  # type: ignore[attr-defined]
            "code": params.get("code", [None])[0],
            "state": params.get("state", [None])[0],
            "error": params.get("error", [None])[0],
        }
        ok = self.server.captured["code"] is not None  # type: ignore[attr-defined]
        body = _CLOSE_PAGE_OK if ok else _CLOSE_PAGE_ERR
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_args) -> None:  # silence the default stderr logging
        return


def _build_authorize_url(redirect_uri: str, challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": config.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config.SCOPE_PROFILE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    sep = "&" if "?" in config.AUTHORIZE_URL else "?"
    return f"{config.AUTHORIZE_URL}{sep}{query}"


def _exchange_code(code: str, verifier: str, redirect_uri: str) -> TokenResult:
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": config.CLIENT_ID,
            "redirect_uri": redirect_uri,
        }
    ).encode("ascii")
    req = urllib.request.Request(
        config.TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise OAuthError(f"Token exchange failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"Could not reach the token endpoint: {exc.reason}") from exc

    token = payload.get("access_token")
    if not token:
        raise OAuthError(f"Token response missing access_token: {payload}")
    return TokenResult(
        access_token=token,
        expires_at=payload.get("expires_at"),
        token_type=payload.get("token_type", "Bearer"),
    )


def run_authorization_flow(open_browser=webbrowser.open) -> TokenResult:
    """Drive the full interactive flow and return the issued token.

    `open_browser` is injectable for testing.
    """
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.captured = None  # type: ignore[attr-defined]
    server.timeout = config.AUTH_FLOW_TIMEOUT_SECONDS
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}{config.CALLBACK_PATH}"

    open_browser(_build_authorize_url(redirect_uri, challenge, state))

    # Serve requests until the callback populates `captured` or we time out.
    deadline = threading.Event()

    def _serve() -> None:
        while server.captured is None and not deadline.is_set():  # type: ignore[attr-defined]
            server.handle_request()

    worker = threading.Thread(target=_serve, daemon=True)
    worker.start()
    worker.join(timeout=config.AUTH_FLOW_TIMEOUT_SECONDS)
    deadline.set()
    server.server_close()

    captured = server.captured  # type: ignore[attr-defined]
    if captured is None:
        raise OAuthError("Authorization timed out — no response from the browser.")
    if captured["error"]:
        raise OAuthError(f"Authorization denied: {captured['error']}")
    if captured["state"] != state:
        raise OAuthError("State mismatch — possible CSRF; aborting.")
    if not captured["code"]:
        raise OAuthError("No authorization code returned.")

    return _exchange_code(captured["code"], verifier, redirect_uri)


_CLOSE_PAGE_OK = (
    "<!doctype html><meta charset=utf-8><title>Mesea Operator</title>"
    "<body style='font-family:system-ui;padding:3rem;text-align:center'>"
    "<h2>Conectat ✓</h2><p>Te poți întoarce în aplicația Mesea Operator. "
    "Această fereastră se poate închide.</p></body>"
)
_CLOSE_PAGE_ERR = (
    "<!doctype html><meta charset=utf-8><title>Mesea Operator</title>"
    "<body style='font-family:system-ui;padding:3rem;text-align:center'>"
    "<h2>Autorizare eșuată</h2><p>Închide fereastra și încearcă din nou din aplicație.</p></body>"
)
