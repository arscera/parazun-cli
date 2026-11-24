"""The OAuth device grant of the CLI.

The device grant is the flow of RFC 8628. The terminal asks the provider
for a device code, the customer allows the device in a browser, and the
terminal polls for the token.

The flow needs no browser on the machine of the terminal and no port that
must be open, so it works on a server. The browser of the customer can be
anywhere.

Two facts of the provider shape the code:

- The token endpoint wants a body of the form
  `application/x-www-form-urlencoded`. A body of another kind is refused
  with an empty answer, so the error names nothing.
- The device grant issues no `id_token`. Only the authorization code grant
  issues one, and the CLI does not need one: the API reads the token row.
"""

import time
from dataclasses import dataclass

import httpx

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REFRESH_GRANT = "refresh_token"

DEVICE_CODE_PATH = "/identity/o/api/device/code"
TOKEN_PATH = "/identity/o/api/token"
REVOKE_PATH = "/identity/o/api/revoke"

# The errors that the provider answers while the customer has not answered
# yet. The poll waits for these two and gives up on every other error.
PENDING = "authorization_pending"
SLOW_DOWN = "slow_down"


class OAuthError(RuntimeError):
    """The provider refused a request, or the customer refused the device."""

    def __init__(self, message: str, error: str = "", description: str = ""):
        super().__init__(message)
        self.error = error
        self.description = description


@dataclass
class DeviceCode:
    """The answer of the provider to a request for a device code."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int
    expires_in: int


def _post_form(client: httpx.Client, url: str, data: dict) -> dict:
    """Post a form and read the answer as JSON.

    The answer of the provider is a JSON document on success and a JSON
    document with an `error` on a refusal. A body that is not JSON means
    that the provider answered something else, so the raw text is in the
    message of the error.
    """
    response = client.post(url, data=data)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        error = body.get("error", "") if isinstance(body, dict) else ""
        description = body.get("error_description", "") if isinstance(body, dict) else ""
        raise OAuthError(
            description or "the provider refused the request",
            error=error,
            description=description,
        )
    return body if isinstance(body, dict) else {}


def request_device_code(
    portal: str, client_id: str, scope: str = "api", timeout: float = 30.0
) -> DeviceCode:
    """Ask the provider for a device code.

    The scope is one name, because the API has no fine grained scopes. A
    token of this client reaches the whole API.
    """
    with httpx.Client(timeout=timeout) as client:
        body = _post_form(
            client,
            portal + DEVICE_CODE_PATH,
            {"client_id": client_id, "scope": scope},
        )

    missing = [
        name
        for name in ("device_code", "user_code", "verification_uri")
        if not body.get(name)
    ]
    if missing:
        raise OAuthError(
            "the provider answered a device code without %s" % ", ".join(missing)
        )

    return DeviceCode(
        device_code=body["device_code"],
        user_code=body["user_code"],
        verification_uri=body["verification_uri"],
        verification_uri_complete=body.get(
            "verification_uri_complete", body["verification_uri"]
        ),
        interval=int(body.get("interval", 5)),
        expires_in=int(body.get("expires_in", 300)),
    )


def poll_for_token(
    portal: str,
    client_id: str,
    device_code: str,
    interval: int = 5,
    timeout: float = 300.0,
    on_wait=None,
) -> dict:
    """Poll for the token until the customer allows the device.

    The provider answers `authorization_pending` while the customer has
    not answered yet, and `slow_down` when the poll is too fast. Every
    other error ends the wait.
    """
    deadline = time.monotonic() + timeout
    wait = max(1, interval)

    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            try:
                return _post_form(
                    client,
                    portal + TOKEN_PATH,
                    {
                        "grant_type": DEVICE_GRANT,
                        "device_code": device_code,
                        "client_id": client_id,
                    },
                )
            except OAuthError as error:
                if error.error == PENDING:
                    pass
                elif error.error == SLOW_DOWN:
                    wait += 5
                else:
                    raise
            if on_wait is not None:
                on_wait(wait)
            time.sleep(wait)

    raise OAuthError(
        "the customer did not answer in time. Run the sign in again.",
        error="expired_token",
    )


def refresh_access_token(
    portal: str, client_id: str, refresh_token: str, timeout: float = 30.0
) -> dict:
    """Get a new access token with the refresh token.

    The provider rotates the refresh token on every refresh, so the answer
    carries a new one and the caller must write it down.
    """
    with httpx.Client(timeout=timeout) as client:
        body = _post_form(
            client,
            portal + TOKEN_PATH,
            {
                "grant_type": REFRESH_GRANT,
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )
    if not body.get("access_token"):
        raise OAuthError("the provider answered a refresh without a token")
    return body


def revoke(portal: str, client_id: str, token: str, timeout: float = 30.0) -> None:
    """Revoke a token at the provider.

    The provider answers 200 for a token that it knows and for a token that
    it does not know, so a token that was already revoked is not an error.
    """
    with httpx.Client(timeout=timeout) as client:
        try:
            _post_form(
                client,
                portal + REVOKE_PATH,
                {"token": token, "client_id": client_id},
            )
        except OAuthError:
            # A revocation that the provider refuses leaves the token
            # alive, so the error is not swallowed. The caller deletes the
            # file and says that the token may live on.
            raise
