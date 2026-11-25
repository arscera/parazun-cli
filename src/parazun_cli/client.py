"""The client of the API.

The API takes two credentials: the API key of a customer and the OAuth
access token of the same customer. The CLI uses the token that the device
grant issued, and the API key of the environment is honoured as well, so a
machine caller needs no browser.

**THE KEY OF THE ENVIRONMENT WINS OVER THE TOKEN OF THE SIGN IN.** The key
is the credential the caller gave for THIS call, and the token is the state
of a machine, which may hold the account of another customer. A machine
caller that sets a key must not be metered against the account of a
session it never asked for.

The client refreshes the token when it is past its hour, and it refreshes
it again when the API answers 401. The second refresh covers a token that
was revoked and a machine whose clock is wrong. **A CLIENT THAT SENDS THE
KEY DOES NOT REFRESH A TOKEN IT DOES NOT SEND**, so the refresh belongs to
the credential of the call.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from . import config, oauth

# The header that carries the credential. The API reads `Api-Key` for a key
# and `Bearer` for a token.
KEY_HEADER = "Api-Key"
TOKEN_HEADER = "Bearer"

# The families of the headers that name the capacity of the customer. The
# API sends a rate limit, an allowance and a credit balance on every
# admitted answer, and a Retry-After on a refusal of the rate limit.
#
# The client keeps every header of those families, so a header the API adds
# later reaches the status line without a change here. A copy of the list of
# the names would drift, and it has already drifted: the list named a credit
# balance the API does not send and named no allowance header at all.
CAPACITY_HEADER_PREFIXES = ("x-ratelimit-", "x-quota-", "x-credit")
CAPACITY_HEADER_NAMES = ("retry-after",)


def is_capacity_header(name: str) -> bool:
    """True when the header names the capacity of the customer."""
    name = name.lower()
    return name in CAPACITY_HEADER_NAMES or name.startswith(CAPACITY_HEADER_PREFIXES)


class ApiError(RuntimeError):
    """The API refused a request."""

    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class Answer:
    """The answer of the API."""

    status_code: int
    body: str
    headers: dict


class ApiClient:
    """The client of one customer."""

    def __init__(
        self,
        credentials: config.Credentials | None = None,
        key: str | None = None,
        timeout: float = 120.0,
    ):
        self.credentials = credentials
        self.key = key
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        if self.credentials is not None:
            return self.credentials.api_url.rstrip("/")
        return config.api_url()

    def _uses_token(self) -> bool:
        """True when the token of the sign in is the credential of this client.

        The key of the environment wins over the token, so a client that
        carries a key sends the key and does not touch the token.
        """
        return not self.key and self.credentials is not None

    def _header(self) -> tuple[str, str]:
        """The header that carries the credential.

        The key of the environment wins over the token of the sign in. The
        key is the credential the caller gave for THIS call, and the token
        is the state of a machine, which may hold the account of another
        customer.
        """
        if self.key:
            return KEY_HEADER, self.key
        if self.credentials is not None:
            return TOKEN_HEADER, self.credentials.access_token
        raise ApiError(
            "there is no credential. Run `parazun auth login`, or set the "
            "PARAZUN_API_KEY value of the environment."
        )

    def _refresh(self) -> bool:
        """Get a new access token and write it down.

        The provider rotates the refresh token, so the file is written with
        the new pair. False when there is no refresh token to use.
        """
        if self.credentials is None or not self.credentials.refresh_token:
            return False

        try:
            body = oauth.refresh_access_token(
                self.credentials.portal_url,
                self.credentials.client_id,
                self.credentials.refresh_token,
            )
        except oauth.OAuthError as error:
            if error.error != oauth.INVALID_GRANT:
                raise
            # The refresh token is dead, so the file of the credentials is
            # dead too. A file that holds a secret that cannot be used
            # misleads every later call, so the file is deleted and the
            # caller is told to sign in again.
            config.remove()
            raise oauth.OAuthError(
                "%s The file of the credentials is deleted, because the sign "
                "in of this device is over." % error,
                error=error.error,
                description=error.description,
            ) from error
        expires_at = config.expiry(body.get("expires_in", 3600))
        self.credentials.access_token = body["access_token"]
        self.credentials.refresh_token = body.get(
            "refresh_token", self.credentials.refresh_token
        )
        self.credentials.expires_at = expires_at
        config.store(self.credentials)
        return True

    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        data: Any = None,
        headers: dict | None = None,
    ) -> Answer:
        """Send one request to the API and return the answer.

        A body that is an object or a list is sent as JSON, because the API
        reads JSON. A body that is text is sent as it is, with the header of
        JSON, so a caller can send a body that the CLI did not build.
        """
        if self._uses_token() and self.credentials.is_expired():
            self._refresh()

        name, value = self._header()
        request_headers = {"Authorization": "%s %s" % (name, value)}
        if headers:
            request_headers.update(headers)

        body: dict = {}
        if data is not None:
            if isinstance(data, (dict, list)):
                body["json"] = data
            else:
                body["content"] = data
                request_headers.setdefault("content-type", "application/json")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method.upper(),
                self.base_url + path,
                params=params,
                headers=request_headers,
                **body,
            )

            if (
                response.status_code == 401
                and self._uses_token()
                and self._refresh()
            ):
                # The token was refused. A new one is tried once, so a
                # revoked token does not send the caller in a circle.
                name, value = self._header()
                request_headers["Authorization"] = "%s %s" % (name, value)
                response = client.request(
                    method.upper(),
                    self.base_url + path,
                    params=params,
                    headers=request_headers,
                    **body,
                )

        return Answer(
            status_code=response.status_code,
            body=response.text,
            headers={
                name.lower(): value
                for name, value in response.headers.items()
                if is_capacity_header(name)
            },
        )
