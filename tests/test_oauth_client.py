"""Unit tests for PKCE generation and authorize-URL construction."""

import base64
import hashlib

from mesea_operator import config, oauth_client


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = oauth_client.generate_pkce()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert challenge == expected
    assert "=" not in challenge  # base64url, unpadded


def test_pkce_verifier_length_and_charset():
    verifier, _ = oauth_client.generate_pkce()
    assert 43 <= len(verifier) <= 128
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(verifier) <= allowed


def test_pkce_is_random_per_call():
    assert oauth_client.generate_pkce()[0] != oauth_client.generate_pkce()[0]


def test_authorize_url_contains_required_params():
    url = oauth_client._build_authorize_url("http://127.0.0.1:5000/cb", "CHAL", "STATE")
    assert url.startswith(config.AUTHORIZE_URL)
    for fragment in (
        "client_id=mesea-operator",
        "code_challenge=CHAL",
        "code_challenge_method=S256",
        "state=STATE",
        "response_type=code",
        "scope=operator",
        "redirect_uri=http%3A%2F%2F127.0.0.1%3A5000%2Fcb",
    ):
        assert fragment in url


def test_authorize_url_keeps_single_separator_when_base_has_query():
    # config.AUTHORIZE_URL already contains `?page=...`, so we must append with &.
    url = oauth_client._build_authorize_url("http://127.0.0.1:1/cb", "C", "S")
    assert url.count("?") == 1
