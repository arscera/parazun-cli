"""The commands of the CLI.

The sign in uses the OAuth device grant. The terminal shows an address and
a code, the customer allows the device in a browser, and the terminal polls
for the token.

The API key of the environment is honoured as well, so a machine caller
needs no browser and no sign in.
"""

import json
import sys
import webbrowser

import typer

from . import client, config, oauth

app = typer.Typer(
    help="The command line client of the Parazun API.",
    no_args_is_help=True,
)
auth_app = typer.Typer(help="The sign in of the CLI.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


def _fail(message: str, code: int = 1):
    """Print the message and end the run with a failure."""
    typer.echo(message, err=True)
    raise typer.Exit(code=code)


@auth_app.command("login")
def login(
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Do not open a browser. The address and the code are printed.",
    ),
    scope: str = typer.Option(
        "api",
        "--scope",
        help="The scope of the token. One name: the API has no fine scopes.",
    ),
):
    """Sign in with the OAuth device grant.

    The terminal shows an address and a code. The customer signs in to the
    portal and allows the device, and the terminal signs itself in.
    """
    portal = config.portal_url()
    client_id = config.client_id()

    try:
        device = oauth.request_device_code(portal, client_id, scope=scope)
    except oauth.OAuthError as error:
        _fail("The sign in could not start: %s" % error)
        return

    typer.echo("Open this address and allow the device:")
    typer.echo("")
    typer.echo("  %s" % device.verification_uri_complete)
    typer.echo("")
    typer.echo("The code is %s." % device.user_code)

    if not no_browser:
        try:
            webbrowser.open(device.verification_uri_complete)
        except Exception:  # noqa: BLE001 - a browser is a convenience
            pass

    typer.echo("")
    typer.echo("Waiting for the device...")

    try:
        body = oauth.poll_for_token(
            portal,
            client_id,
            device.device_code,
            interval=device.interval,
            timeout=float(device.expires_in),
        )
    except oauth.OAuthError as error:
        _fail("The sign in failed: %s" % error)
        return

    credentials = config.Credentials(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", ""),
        expires_at=config.expiry(body.get("expires_in", 3600)),
        api_url=config.api_url(),
        portal_url=portal,
        client_id=client_id,
    )
    path = config.store(credentials)
    typer.echo("Signed in. The credentials are in %s." % path)


@auth_app.command("status")
def status():
    """Show the state of the sign in of this machine."""
    credentials = config.load()
    if credentials is None:
        typer.echo("This machine is not signed in. Run `parazun auth login`.")
        raise typer.Exit(code=1)

    typer.echo("File:       %s" % config.credentials_path())
    typer.echo("Client:     %s" % credentials.client_id)
    typer.echo("API:        %s" % credentials.api_url)
    typer.echo("Portal:     %s" % credentials.portal_url)
    typer.echo("Expires at: %s" % credentials.expires_at)
    if credentials.is_expired():
        typer.echo("The token is past its hour. The next request refreshes it.")
    else:
        typer.echo("The token is alive.")


@auth_app.command("logout")
def logout():
    """Sign this machine out and delete the credentials."""
    credentials = config.load()
    if credentials is None:
        typer.echo("This machine is not signed in.")
        return

    if credentials.refresh_token:
        try:
            oauth.revoke(
                credentials.portal_url,
                credentials.client_id,
                credentials.refresh_token,
            )
        except oauth.OAuthError as error:
            typer.echo(
                "The provider refused the revocation: %s" % error,
                err=True,
            )
            typer.echo(
                "The file was deleted, but the token may live on. Revoke it "
                "at the portal if it matters.",
                err=True,
            )
            config.remove()
            raise typer.Exit(code=1)

    config.remove()
    typer.echo("Signed out. The credentials are deleted.")


@app.command("request")
def request(
    path: str = typer.Argument(..., help="The path of the API, with its query."),
    method: str = typer.Option("GET", "--method", help="The method of the request."),
    param: list[str] = typer.Option(
        [], "--param", help="A query parameter, as name=value. It can be used twice."
    ),
    data: str = typer.Option(
        None, "--data", help="The body of the request, as JSON."
    ),
):
    """Send one request to the API with the credential of this machine.

    The credential is the OAuth token of the sign in, or the API key of the
    PARAZUN_API_KEY value of the environment.
    """
    credentials = config.load()
    key = config.api_key()
    if credentials is None and not key:
        _fail(
            "This machine is not signed in. Run `parazun auth login`, or set "
            "the PARAZUN_API_KEY value of the environment."
        )
        return

    params = {}
    for item in param:
        if "=" not in item:
            _fail("The parameter %s carries no '='. Use name=value." % item)
            return
        name, _, value = item.partition("=")
        params[name] = value

    body = None
    if data:
        try:
            body = json.loads(data)
        except json.JSONDecodeError as error:
            _fail("The body is not JSON: %s" % error)
            return

    api = client.ApiClient(credentials=credentials, key=key)
    try:
        answer = api.request(method, path, params=params or None, data=body)
    except client.ApiError as error:
        _fail(str(error))
        return
    except Exception as error:  # noqa: BLE001 - the message reaches the caller
        _fail("The request failed: %s" % error)
        return

    for name, value in sorted(answer.headers.items()):
        typer.echo("%s: %s" % (name, value))
    typer.echo("Status: %s" % answer.status_code)
    typer.echo(answer.body)

    if answer.status_code >= 400:
        raise typer.Exit(code=1)


def main():
    """The entry point of the `parazun` command."""
    try:
        app()
    except oauth.OAuthError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
