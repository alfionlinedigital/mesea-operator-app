"""End-to-end test of the OAuth client against a stub authorization server.

No real backend: a local HTTP server plays the token endpoint, and a fake
"browser" performs the consent→redirect to the loopback listener. This drives
the *actual* run_authorization_flow — PKCE generation, the loopback capture,
state validation, and the token exchange — proving the full client path and
that PKCE round-trips (the verifier the client sends hashes to the challenge
the client presented).
"""

import base64
import hashlib
import http.server
import json
import threading
import urllib.parse
import urllib.request

import pytest

from mesea_operator import config, oauth_client


class _StubAS:
    """Stub authorization server: holds issued codes + serves the token endpoint."""

    def __init__(self):
        self.codes: dict[str, dict] = {}
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                outer._handle_token(self, form)

            def log_message(self, *_a):
                return

        self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _handle_token(self, handler, form):
        code = form.get("code")
        verifier = form.get("code_verifier", "")
        record = self.codes.pop(code, None)  # one-time use
        ok = False
        if record is not None:
            expected = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            ok = expected == record["challenge"] and form.get("redirect_uri") == record["redirect_uri"]
        if ok:
            payload = {
                "access_token": "msk_live_e2e_token",
                "token_type": "Bearer",
                "expires_at": "2026-09-05T12:00:00+00:00",
            }
            handler.send_response(200)
        else:
            payload = {"error": "invalid_grant"}
            handler.send_response(400)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(payload).encode())

    @property
    def token_url(self):
        return f"http://127.0.0.1:{self.port}/token"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *a):
        self._server.shutdown()
        self._server.server_close()


def _fake_browser(*, issue_code=True, send_state="echo", as_server=None):
    """Return an open_browser(url) that simulates consent + loopback redirect."""

    def opener(url):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        redirect_uri = params["redirect_uri"][0]
        challenge = params["code_challenge"][0]
        state = params["state"][0] if send_state == "echo" else send_state

        def hit():
            if issue_code:
                code = "authcode-123"
                as_server.codes[code] = {"challenge": challenge, "redirect_uri": redirect_uri}
                q = urllib.parse.urlencode({"code": code, "state": state})
            else:
                q = urllib.parse.urlencode({"error": "access_denied", "state": state})
            try:
                urllib.request.urlopen(f"{redirect_uri}?{q}", timeout=5).read()
            except Exception:
                pass

        # Fire asynchronously so the loopback server (started after open_browser
        # returns) can accept and handle it.
        threading.Thread(target=hit, daemon=True).start()

    return opener


@pytest.fixture(autouse=True)
def _fast_timeout(monkeypatch):
    monkeypatch.setattr(config, "AUTH_FLOW_TIMEOUT_SECONDS", 15)


def test_full_flow_happy_path(monkeypatch):
    with _StubAS() as stub:
        monkeypatch.setattr(config, "TOKEN_URL", stub.token_url)
        result = oauth_client.run_authorization_flow(
            open_browser=_fake_browser(as_server=stub)
        )
    assert result.access_token == "msk_live_e2e_token"
    assert result.token_type == "Bearer"
    assert result.expires_at.startswith("2026-09-05")


def test_flow_rejects_state_mismatch(monkeypatch):
    with _StubAS() as stub:
        monkeypatch.setattr(config, "TOKEN_URL", stub.token_url)
        with pytest.raises(oauth_client.OAuthError, match="State mismatch"):
            oauth_client.run_authorization_flow(
                open_browser=_fake_browser(as_server=stub, send_state="WRONG")
            )


def test_flow_surfaces_authorization_denied(monkeypatch):
    with _StubAS() as stub:
        monkeypatch.setattr(config, "TOKEN_URL", stub.token_url)
        with pytest.raises(oauth_client.OAuthError, match="denied"):
            oauth_client.run_authorization_flow(
                open_browser=_fake_browser(as_server=stub, issue_code=False)
            )


def test_replayed_code_is_rejected(monkeypatch):
    """The AS enforces one-time codes: replaying a consumed code returns 400."""
    import urllib.error

    with _StubAS() as stub:
        monkeypatch.setattr(config, "TOKEN_URL", stub.token_url)
        # First exchange consumes the code.
        oauth_client.run_authorization_flow(open_browser=_fake_browser(as_server=stub))

        # Replay the same code directly against the token endpoint.
        data = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": "authcode-123",
                "code_verifier": "whatever",
                "client_id": config.CLIENT_ID,
                "redirect_uri": "http://127.0.0.1:1/cb",
            }
        ).encode()
        req = urllib.request.Request(stub.token_url, data=data, method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400
