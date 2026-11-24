"""The tests of the CLI.

The tests never touch the network. The provider and the API are answered by
a fake transport, so every step of the flow is measured and no request
leaves the machine.
"""

import json
import os
import stat

import httpx
import pytest

from parazun_cli import client, config, oauth


@pytest.fixture(autouse=True)
def a_private_config_dir(tmp_path, monkeypatch):
    """Every test writes its credentials into its own directory."""
    monkeypatch.setenv("PARAZUN_CONFIG_DIR", str(tmp_path / "config"))


def _fake_transport(monkeypatch, handler):
    """Make every httpx client answer with the handler."""
    original = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def _credentials(**overrides):
    values = {
        "access_token": "the-access-token",
        "refresh_token": "the-refresh-token",
        "expires_at": config.expiry(3600),
        "api_url": "https://api.parazun.test",
        "portal_url": "https://portal.parazun.test",
        "client_id": "parazun-cli",
    }
    values.update(overrides)
    return config.Credentials(**values)


def test_the_credentials_file_is_a_secret():
    """The file is readable by the owner alone."""
    path = config.store(_credentials())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_the_credentials_survive_a_read():
    """What is written is what is read."""
    config.store(_credentials())
    stored = config.load()
    assert stored.access_token == "the-access-token"
    assert stored.client_id == "parazun-cli"


def test_a_token_that_is_past_its_hour_is_expired():
    """The token of an hour ago is expired."""
    assert _credentials(expires_at=config.expiry(-1)).is_expired()
    assert not _credentials(expires_at=config.expiry(3600)).is_expired()


def test_the_device_code_is_read_from_the_answer_of_the_provider(monkeypatch):
    """The provider answers the code, the interval and the address."""

    def handler(request):
        assert request.url.path.endswith("/identity/o/api/device/code")
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        return httpx.Response(
            200,
            json={
                "device_code": "the-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://portal.parazun.test/identity/o/device",
                "verification_uri_complete": "https://portal.parazun.test/identity/o/device?code=ABCD-EFGH",
                "interval": 5,
                "expires_in": 300,
            },
        )

    _fake_transport(monkeypatch, handler)
    device = oauth.request_device_code("https://portal.parazun.test", "parazun-cli")
    assert device.user_code == "ABCD-EFGH"
    assert device.device_code == "the-device-code"
    assert device.interval == 5


def test_the_poll_waits_for_the_customer(monkeypatch):
    """The provider answers that it waits, and then it answers the token."""
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) < 3:
            return httpx.Response(400, json={"error": "authorization_pending"})
        return httpx.Response(
            200,
            json={
                "access_token": "the-access-token",
                "refresh_token": "the-refresh-token",
                "expires_in": 3600,
            },
        )

    _fake_transport(monkeypatch, handler)
    body = oauth.poll_for_token(
        "https://portal.parazun.test", "parazun-cli", "the-device-code", interval=0
    )
    assert body["access_token"] == "the-access-token"
    assert len(calls) == 3


def test_the_poll_gives_up_when_the_customer_denies_the_device(monkeypatch):
    """A denial ends the wait."""

    def handler(request):
        return httpx.Response(400, json={"error": "access_denied"})

    _fake_transport(monkeypatch, handler)
    with pytest.raises(oauth.OAuthError):
        oauth.poll_for_token(
            "https://portal.parazun.test", "parazun-cli", "the-device-code", interval=0
        )


def test_the_message_of_a_refusal_names_the_code_of_the_provider(monkeypatch):
    """A provider that answers without a description still names the cause.

    The answer of the provider was `{"error": "invalid_grant"}` and the
    message of the client was "the provider refused the request", so the
    operator read a message that named nothing.
    """

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    _fake_transport(monkeypatch, handler)
    with pytest.raises(oauth.OAuthError) as failure:
        oauth.poll_for_token(
            "https://portal.parazun.test", "parazun-cli", "the-device-code", interval=0
        )
    assert "invalid_grant" in str(failure.value)
    assert failure.value.error == "invalid_grant"


def test_the_description_of_the_provider_is_the_message(monkeypatch):
    """A provider that answers with a description uses it."""

    def handler(request):
        return httpx.Response(
            400, json={"error": "invalid_client", "error_description": "the client is unknown"}
        )

    _fake_transport(monkeypatch, handler)
    with pytest.raises(oauth.OAuthError) as failure:
        oauth.poll_for_token(
            "https://portal.parazun.test", "parazun-cli", "the-device-code", interval=0
        )
    assert "the client is unknown" in str(failure.value)


def test_the_refresh_answers_a_new_pair(monkeypatch):
    """The provider rotates the refresh token, so the answer carries a new one."""

    def handler(request):
        assert request.url.path.endswith("/identity/o/api/token")
        return httpx.Response(
            200,
            json={
                "access_token": "the-new-access-token",
                "refresh_token": "the-new-refresh-token",
                "expires_in": 3600,
            },
        )

    _fake_transport(monkeypatch, handler)
    body = oauth.refresh_access_token(
        "https://portal.parazun.test", "parazun-cli", "the-refresh-token"
    )
    assert body["access_token"] == "the-new-access-token"
    assert body["refresh_token"] == "the-new-refresh-token"


def test_the_body_of_the_request_is_json(monkeypatch):
    """A body that is an object is sent as JSON, because the API reads JSON."""
    seen = {}

    def handler(request):
        seen["content"] = request.content
        seen["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=_credentials())
    api.request("POST", "/search", data={"q": "coffee grinder"})
    assert json.loads(seen["content"]) == {"q": "coffee grinder"}
    assert "application/json" in seen["content_type"]


def test_the_client_sends_the_bearer_header(monkeypatch):
    """The token travels in the header of the request."""
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=_credentials())
    answer = api.request("GET", "/product/")
    assert answer.status_code == 200
    assert seen["authorization"] == "Bearer the-access-token"


def test_the_client_sends_the_api_key_when_there_is_no_token(monkeypatch):
    """The key of the environment is the credential of a machine caller."""
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(key="the-api-key")
    api.request("GET", "/product/")
    assert seen["authorization"] == "Api-Key the-api-key"


def test_the_client_refreshes_a_refused_token(monkeypatch):
    """A token that the API refuses is refreshed once, and the new one is kept."""
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/identity/o/api/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "the-new-access-token",
                    "refresh_token": "the-new-refresh-token",
                    "expires_in": 3600,
                },
            )
        if len(seen) == 1:
            return httpx.Response(401, json={"error": "Invalid access token"})
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=_credentials())
    answer = api.request("GET", "/product/")
    assert answer.status_code == 200

    # The new token is written down, because the refresh token is rotated.
    stored = config.load()
    assert stored.access_token == "the-new-access-token"
    assert stored.refresh_token == "the-new-refresh-token"
