"""The commands of the CLI.

The CLI models the API: the name of a command is the name of an operation
of the API, and the name of an option is the name of a parameter of the
API.

The output has three parts and they never mix:

- the body of the answer of the API goes to stdout, so a caller can pipe
  it into a tool that reads JSON;
- the status and the capacity go to stderr, so a person sees them and a
  pipe does not;
- the exit code is 0 when the API answered and 1 when it refused.

A noun of the API can have an operation of its own AND operations under
it, so `parazun product <ASIN>` and `parazun product reviews <ASIN>` are
both commands. The operation of the noun is a hidden command of the group,
and the group sends the first argument to it when the first argument is
not the name of an operation under the noun.
"""

import json
import sys
import webbrowser

import typer
from typer.core import TyperGroup

from . import client, config, oauth

# The name of the hidden command that carries the operation of a noun.
DEFAULT_OPERATION = "get"

app = typer.Typer(
    help="The command line client of the Parazun API.", no_args_is_help=True
)
auth_app = typer.Typer(help="The sign in of the CLI.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


class NounGroup(TyperGroup):
    """The group of the operations of one noun of the API.

    A noun can have an operation of its own AND operations under it, so
    `parazun product <ASIN>` and `parazun product reviews <ASIN>` are both
    commands. The operation of the noun is a hidden command of the group,
    and the group sends the first argument to it when the first argument is
    not the name of an operation under the noun.
    """

    def parse_args(self, ctx, args):
        if not args and self.get_command(ctx, DEFAULT_OPERATION) is not None:
            # No argument at all: the operation of the noun runs with no
            # argument, so the name of the hidden command is the argument.
            args = [DEFAULT_OPERATION]
        return super().parse_args(ctx, args)

    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands:
            operation = self.get_command(ctx, DEFAULT_OPERATION)
            if operation is not None:
                return DEFAULT_OPERATION, operation, args
        return super().resolve_command(ctx, args)


def _option(help_text):
    """An option of the CLI.

    The option has NO default of its own, so the default of the API
    applies to the parameters that the caller did not give. The name of
    the option is the name of the parameter of the API, because Typer
    turns the name of the argument into the name of the option.
    """
    return typer.Option(None, help=help_text)


def _region_callback(value):
    """The marketplace of the answer: the value of the caller, or the environment.

    The value is None when the caller gave nothing and the environment is
    silent, and then the command sends no marketplace and the default of
    the API applies.
    """
    return value if value is not None else config.region()


def region_option():
    """The option of the marketplace.

    Only the command of an operation that HAS a marketplace carries this
    option, so the marketplace is sent only to the operations of the API
    that take one.
    """
    return typer.Option(
        None,
        "--region",
        callback=_region_callback,
        help=(
            "The marketplace of the answer. The default is the default of "
            "the API, or the value of PARAZUN_REGION."
        ),
    )


def _query(region=None, **values):
    """The query of the request.

    Only the parameters that the caller gave are sent, so the default of
    the API applies to the rest.
    """
    query = {name: value for name, value in values.items() if value is not None}
    if region is not None:
        query["region"] = region
    return query


def _status_line(answer):
    """One line that names the status and the capacity of the customer.

    The capacity is the rate limit, the allowance and the credit balance
    that the answer carried, so a caller can read what it can still send
    without provoking a refusal.
    """
    line = "HTTP %d |" % answer.status_code
    for name in sorted(answer.headers):
        line += " %s=%s" % (name, answer.headers[name])
    return line


def _emit(answer):
    """Print the answer of the API.

    The body goes to stdout and the status goes to stderr, so a pipe of
    stdout is the body of the API and nothing else. A refusal ends the
    run with the exit code 1.
    """
    line = _status_line(answer)
    if 200 <= answer.status_code < 300:
        typer.echo(answer.body)
        typer.echo(line, err=True)
        return
    typer.echo(answer.body, err=True)
    typer.echo(line, err=True)
    raise typer.Exit(code=1)


def _fail(message):
    """Print the message and end the run with a failure."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _api_client():
    """The client of the customer of this machine.

    The key of the environment is the credential of a machine caller and the
    token of the sign in is the credential of a person, and the key wins:
    the caller gave the key for this call, and the token is the state of
    the machine, which may hold the account of another customer. A machine
    caller that sets a key must not be metered against that account.
    """
    credentials = config.load()
    key = config.api_key()
    if credentials is None and not key:
        _fail(
            "This machine is not signed in. Run `parazun auth login`, or set "
            "the PARAZUN_API_KEY value of the environment."
        )
    return client.ApiClient(credentials=credentials, key=key)


def _call(path, params=None, method="GET", data=None):
    """Send one request to the API and print the answer."""
    api = _api_client()
    try:
        answer = api.request(method, path, params=params or None, data=data)
    except client.ApiError as error:
        _fail(str(error))
        return
    except Exception as error:  # noqa: BLE001 - the message reaches the caller
        _fail("The request failed: %s" % error)
        return
    _emit(answer)


# ---------------------------------------------------------------- product


product_app = typer.Typer(
    cls=NounGroup,
    help="The product of the API. `parazun product <ASIN>` returns one product.",
    no_args_is_help=True,
)
app.add_typer(product_app, name="product")


@product_app.command(DEFAULT_OPERATION, hidden=True)
def product_get(
    asin: str = typer.Argument(
        ..., metavar="ASIN", help="The ASIN of the product."
    ),
    region: str = region_option(),
):
    """Return the product of an ASIN."""
    _call("/product", _query(region=region, asin=asin))


@product_app.command("offers")
def product_offers(
    asin: str = typer.Argument(
        ..., metavar="ASIN", help="The ASIN of the product."
    ),
    region: str = region_option(),
    zip_code: str = _option("The postal code of the delivery address."),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
):
    """Return the offers of a product."""
    _call(
        "/product/offers",
        _query(region=region, asin=asin, zip_code=zip_code, page=page),
    )


@product_app.command("reviews")
def product_reviews(
    asin: str = typer.Argument(
        ..., metavar="ASIN", help="The ASIN of the product."
    ),
    region: str = region_option(),
    sort_by: str = _option(
        "The sort of the reviews: helpful or recent. The default is the default of the API."
    ),
    reviewer_type: str = _option(
        "The reviews of all the reviewers, or of the buyers. The default is the default of the API."
    ),
    format_type: str = _option(
        "The formats of the reviews. The default is the default of the API."
    ),
    media_type: str = _option(
        "The contents of the reviews. The default is the default of the API."
    ),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
    filter_by_keyword: str = _option("A word that the reviews must carry."),
):
    """Return the reviews of a product."""
    _call(
        "/product/reviews",
        _query(
            region=region,
            asin=asin,
            sort_by=sort_by,
            reviewer_type=reviewer_type,
            format_type=format_type,
            media_type=media_type,
            page=page,
            filter_by_keyword=filter_by_keyword,
        ),
    )


@product_app.command("related")
def product_related(
    asin: str = typer.Argument(
        ..., metavar="ASIN", help="The ASIN of the product."
    ),
    region: str = region_option(),
):
    """Return the ASINs of the products that are related to a product."""
    _call("/product/related-asins", _query(region=region, asin=asin))


@product_app.command("summaries")
def product_summaries(
    asins: list[str] = typer.Argument(
        ..., metavar="ASIN", help="The ASINs of the products."
    ),
    region: str = region_option(),
    format: str = _option(
        "The format of the answer: json or csv. The default is the default of the API."
    ),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
    all: str = typer.Option(
        None,
        "--all",
        help=(
            "Every page of the answer: 1 or 0. The default is the default "
            "of the API."
        ),
    ),
):
    """Return the summaries of a list of products."""
    _call(
        "/product/summaries",
        _query(
            region=region,
            asins=",".join(asins),
            format=format,
            page=page,
            all=all,
        ),
    )


# ----------------------------------------------------------------- search


search_app = typer.Typer(
    cls=NounGroup,
    help="The search of the API. `parazun search <KEYWORD>` returns the results.",
    no_args_is_help=True,
)
app.add_typer(search_app, name="search")


@search_app.command(DEFAULT_OPERATION, hidden=True)
def search_get(
    keywords: list[str] = typer.Argument(
        ..., metavar="KEYWORD", help="The words of the search."
    ),
    region: str = region_option(),
    search_alias: str = _option(
        "The index of the search: aps and the others. The default is the default of the API."
    ),
    node_id: str = _option("The node of the category of the search."),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
):
    """Return the results of a search.

    The words are one argument or several, and the words of the API hold
    them separated by a space.
    """
    _call(
        "/search",
        _query(
            region=region,
            keywords=" ".join(keywords),
            search_alias=search_alias,
            node_id=node_id,
            page=page,
        ),
    )


@search_app.command("aliases")
def search_aliases(
    region: str = region_option(),
):
    """Return the indexes that a search can use."""
    _call("/search/aliases", _query(region=region))


# --------------------------------------------------------------- category


category_app = typer.Typer(
    cls=NounGroup,
    help="The category of the API. `parazun category` returns the categories.",
    no_args_is_help=True,
)
app.add_typer(category_app, name="category")


@category_app.command(DEFAULT_OPERATION, hidden=True)
def category_get(
    region: str = region_option(),
    parent_id: int = _option("The node of the parent of the categories."),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
    size: int = _option(
        "The count of the categories of the answer. The default is the default of the API."
    ),
):
    """Return the categories of a marketplace."""
    _call(
        "/category",
        _query(region=region, parent_id=parent_id, page=page, size=size),
    )


@category_app.command("descendants")
def category_descendants(
    node_id: int = typer.Argument(
        ..., metavar="NODE_ID", help="The node of the category."
    ),
    level: int = _option("The level of the descendants."),
):
    """Return the descendants of a category."""
    _call("/category/descendants", _query(node_id=node_id, level=level))


# -------------------------------------------------------------- rankings


bestseller_app = typer.Typer(
    cls=NounGroup,
    help="The best sellers of the API.",
    no_args_is_help=True,
)
app.add_typer(bestseller_app, name="bestseller")


@bestseller_app.command("by-category")
def bestseller_by_category(
    node_id: int = typer.Argument(
        ..., metavar="NODE_ID", help="The node of the category."
    ),
    region: str = region_option(),
):
    """Return the best sellers of a category."""
    _call("/bestseller/by-category", _query(region=region, node_id=node_id))


@bestseller_app.command("by-department")
def bestseller_by_department(
    alias: str = typer.Argument(
        ..., metavar="ALIAS", help="The alias of the department."
    ),
    region: str = region_option(),
):
    """Return the best sellers of a department."""
    _call("/bestseller/by-department", _query(region=region, alias=alias))


new_releases_app = typer.Typer(
    cls=NounGroup,
    help="The new releases of the API.",
    no_args_is_help=True,
)
app.add_typer(new_releases_app, name="new-releases")


@new_releases_app.command("by-category")
def new_releases_by_category(
    node_id: int = typer.Argument(
        ..., metavar="NODE_ID", help="The node of the category."
    ),
    region: str = region_option(),
):
    """Return the new releases of a category."""
    _call("/new-releases/by-category", _query(region=region, node_id=node_id))


@new_releases_app.command("by-department")
def new_releases_by_department(
    alias: str = typer.Argument(
        ..., metavar="ALIAS", help="The alias of the department."
    ),
    region: str = region_option(),
):
    """Return the new releases of a department."""
    _call("/new-releases/by-department", _query(region=region, alias=alias))


# ------------------------------------------------------- departments, deals


@app.command("departments")
def departments(
    region: str = region_option(),
):
    """Return the departments of a marketplace."""
    _call("/departments", _query(region=region))


@app.command("deals")
def deals(
    region: str = region_option(),
    page: int = _option(
        "The page of the answer. The default is the default of the API."
    ),
):
    """Return the deals of today."""
    _call("/deals", _query(region=region, page=page))


@app.command("seller")
def seller(
    seller_id: str = typer.Argument(
        ..., metavar="SELLER_ID", help="The id of the seller."
    ),
    region: str = region_option(),
    include_products: bool = typer.Option(
        None,
        "--include-products",
        help="The products of the seller. The default is the default of the API.",
    ),
    include_feedback: bool = typer.Option(
        None,
        "--include-feedback",
        help="The feedback of the seller. The default is the default of the API.",
    ),
    products_limit: int = _option(
        "The count of the products of the answer. The default is the default of the API."
    ),
    feedback_limit: int = _option(
        "The count of the feedback of the answer. The default is the default of the API."
    ),
):
    """Return the profile of a seller."""
    _call(
        "/seller",
        _query(
            region=region,
            seller_id=seller_id,
            include_products=include_products,
            include_feedback=include_feedback,
            products_limit=products_limit,
            feedback_limit=feedback_limit,
        ),
    )


# ------------------------------------------------------------- the escape hatch


@app.command("request")
def request(
    path: str = typer.Argument(..., metavar="PATH", help="The path of the API."),
    method: str = typer.Option("GET", "--method", help="The method of the request."),
    param: list[str] = typer.Option(
        [], "--param", help="A parameter of the request, as name=value."
    ),
    data: str = typer.Option(
        None, "--data", help="The body of the request, as JSON."
    ),
):
    """Send one request to any path of the API.

    This is the way to an operation that has no command yet.
    """
    values = {}
    for item in param:
        if "=" not in item:
            _fail("The parameter %s carries no '='. Use name=value." % item)
            return
        name, _, value = item.partition("=")
        values[name] = value

    body = None
    if data:
        try:
            body = json.loads(data)
        except json.JSONDecodeError as error:
            _fail("The body is not JSON: %s" % error)
            return

    _call(path, params=values or None, method=method, data=body)


# ------------------------------------------------------------------- the sign in


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
    if config.api_key():
        typer.echo("Calls use:  the API key of the environment")
    else:
        typer.echo("Calls use:  the token of the sign in")
    if credentials.is_expired():
        if config.api_key():
            typer.echo(
                "The token is past its hour, and the calls do not send it, so "
                "it is not refreshed."
            )
        else:
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
                "on the page of the API keys of the portal (%s/keys/) if it "
                "matters." % credentials.portal_url.rstrip("/"),
                err=True,
            )
            config.remove()
            raise typer.Exit(code=1)

    config.remove()
    typer.echo("Signed out. The credentials are deleted.")


def main():
    """The entry point of the `parazun` command."""
    try:
        app()
    except oauth.OAuthError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
