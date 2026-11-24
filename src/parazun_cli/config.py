"""The store of the credentials of the CLI.

The file holds the access token and the refresh token of the customer. It
is a secret, so the file is readable by the owner alone: the directory is
made with the mode 0700 and the file with the mode 0600.

The file lives at `~/.config/parazun/credentials.json`. The
PARAZUN_CONFIG_DIR value of the environment changes the directory, so a
test and a real run never share the file.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DIRECTORY = Path.home() / ".config" / "parazun"
CREDENTIALS_NAME = "credentials.json"

DEFAULT_API_URL = "https://api.parazun.com"
DEFAULT_PORTAL_URL = "https://portal.parazun.com"
DEFAULT_CLIENT_ID = "parazun-cli"


def config_directory() -> Path:
    """The directory that holds the credentials file."""
    value = os.getenv("PARAZUN_CONFIG_DIR", "").strip()
    if value:
        return Path(value).expanduser()
    return DEFAULT_DIRECTORY


def credentials_path() -> Path:
    """The path of the credentials file."""
    return config_directory() / CREDENTIALS_NAME


def api_url() -> str:
    """The address of the API."""
    value = os.getenv("PARAZUN_API_URL", "").strip()
    return value.rstrip("/") if value else DEFAULT_API_URL


def portal_url() -> str:
    """The address of the portal, where the provider of the tokens lives."""
    value = os.getenv("PARAZUN_PORTAL_URL", "").strip()
    return value.rstrip("/") if value else DEFAULT_PORTAL_URL


def client_id() -> str:
    """The id of the public client of the CLI."""
    value = os.getenv("PARAZUN_CLIENT_ID", "").strip()
    return value if value else DEFAULT_CLIENT_ID


def region() -> str | None:
    """The marketplace of the answer, when the environment names one.

    The value is None when the environment is silent, and then the
    command sends no marketplace and the default of the API applies.
    """
    return os.getenv("PARAZUN_REGION", "").strip() or None


def api_key() -> str | None:
    """The API key of the environment, when there is one."""
    value = os.getenv("PARAZUN_API_KEY", "").strip()
    return value if value else None


def expiry(seconds: int) -> str:
    """The moment a token dies, in the form that the store holds."""
    from datetime import timedelta

    moment = datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
    return moment.isoformat()


@dataclass
class Credentials:
    """The tokens of one customer and the addresses they belong to."""

    access_token: str
    refresh_token: str
    expires_at: str
    api_url: str
    portal_url: str
    client_id: str

    def is_expired(self) -> bool:
        """True when the access token is past its hour.

        A token that expires in the next minute counts as expired, so the
        CLI refreshes it before the request and not during it.
        """
        try:
            moment = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment <= datetime.now(timezone.utc)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Credentials":
        data = json.loads(text)
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            api_url=data.get("api_url", DEFAULT_API_URL),
            portal_url=data.get("portal_url", DEFAULT_PORTAL_URL),
            client_id=data.get("client_id", DEFAULT_CLIENT_ID),
        )


def load() -> Credentials | None:
    """Read the credentials of the customer, or None when there are none."""
    path = credentials_path()
    if not path.exists():
        return None
    try:
        return Credentials.from_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError, OSError):
        # A file that cannot be read is a file that cannot be used. The
        # caller tells the customer to sign in again.
        return None


def store(credentials: Credentials) -> Path:
    """Write the credentials of the customer and keep the file a secret.

    The file is written through a temporary file in the same directory and
    then moved over the old one, so a crash cannot leave a half written
    file behind, and the mode of the file is 0600 from the first moment.
    """
    directory = config_directory()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)

    path = credentials_path()
    handle, temporary = tempfile.mkstemp(dir=str(directory), prefix=".credentials-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(credentials.to_json())
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return path


def remove() -> bool:
    """Delete the credentials file. True when a file was there."""
    path = credentials_path()
    if not path.exists():
        return False
    path.unlink()
    return True
