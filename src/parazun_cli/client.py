"""The client of the API.

The API takes two credentials: the API key of a customer and the OAuth
access token of the same customer. The CLI uses the token that the device
grant issued, and the API key of the environment is honoured as well, so a
machine caller needs no browser.

The client refreshes the token when it is past its hour, and it refreshes
it again when the API answers 401. The second refresh covers a token that
was revoked and a machine whose clock is wrong.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from . import config, oauth

# The header that carries the credential. The API reads `Api-Key` for a key
# and `Bearer` for a token.
KEY_HEADER = "Api-Key"
TOKEN_HEADER = "Bearer"

# The headers of the answer that carry the state of the plan.
REPORT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-credits-balance",
)


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

    def _header(self) -> tuple[str, str]:
        """The header that carries the credential."""
        if self.credentials is not None:
            return TOKEN_HEADER, self.credentials.access_token
        if self.key:
            return KEY_HEADER, self.key
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

        body = oauth.refresh_access_token(
            self.credentials.portal_url,
            self.credentials.client_id,
            self.credentials.refresh_token,
        )
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
        """Send one request to the API and return the answer."""
        if self.credentials is not None and self.credentials.is_expired():
            self._refresh()

        name, value = self._header()
        request_headers = {"Authorization": "%s %s" % (name, value)}
        if headers:
            request_headers.update(headers)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method.upper(),
                self.base_url + path,
                params=params,
                data=data,
                headers=request_headers,
            )

            if response.status_code == 401 and self._refresh():
                # The token was refused. A new one is tried once, so a
                # revoked token does not send the caller in a circle.
                name, value = self._header()
                request_headers["Authorization"] = "%s %s" % (name, value)
                response = client.request(
                    method.upper(),
                    self.base_url + path,
                    params=params,
                    data=data,
                    headers=request_headers,
                )

        return Answer(
            status_code=response.status_code,
            body=response.text,
            headers={
                name.lower(): value
                for name, value in response.headers.items()
                if name.lower() in REPORT_HEADERS
            },
        )
