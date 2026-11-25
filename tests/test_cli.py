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
from typer.testing import CliRunner

from parazun_cli import cli, client, config, oauth


@pytest.fixture(autouse=True)
def a_private_config_dir(tmp_path, monkeypatch):
    """Every test writes its credentials into its own directory."""
    monkeypatch.setenv("PARAZUN_CONFIG_DIR", str(tmp_path / "config"))


# The real client of httpx, captured before any test replaces it. The
# helper below replaces the client again, and a helper that captured the
# replaced client would answer with the handler of the first call.
REAL_CLIENT = httpx.Client


def _fake_transport(monkeypatch, handler):
    """Make every httpx client answer with the handler."""

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return REAL_CLIENT(*args, **kwargs)

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


def test_the_key_of_the_environment_wins_over_the_token_of_the_sign_in(monkeypatch):
    """The credential the caller gave is the credential of the call.

    The token of the sign in is the state of the machine, and it may hold
    the account of another customer, so a machine caller that sets a key
    must not be metered against that account.
    """
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=_credentials(), key="the-api-key")
    api.request("GET", "/product/")
    assert seen["authorization"] == "Api-Key the-api-key"


def test_the_key_of_the_environment_does_not_refresh_the_token(monkeypatch):
    """A client that sends the key does not touch the token of the machine."""
    asked = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    config.store(_credentials(expires_at=config.expiry(-60)))
    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=config.load(), key="the-api-key")
    api.request("GET", "/product/")

    # The token endpoint was never asked, so the rotated refresh token of
    # the machine was never written.
    assert not [path for path in asked if path.endswith("/identity/o/api/token")]
    assert config.load().refresh_token == "the-refresh-token"


def test_a_refused_key_is_not_retried_with_a_refreshed_token(monkeypatch):
    """A key that the API refuses is refused, and no token is refreshed."""
    asked = []

    def handler(request):
        asked.append(request.url.path)
        if request.url.path.endswith("/identity/o/api/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "the-new-access-token",
                    "refresh_token": "the-new-refresh-token",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(401, json={"error": "Invalid API Key"})

    config.store(_credentials())
    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(credentials=config.load(), key="the-api-key")
    answer = api.request("GET", "/product/")

    assert answer.status_code == 401
    assert asked == ["/product/"]


def test_the_status_line_names_the_capacity_of_the_customer(monkeypatch):
    """The status line carries the allowance and the credit balance.

    The API sends them on every admitted answer so a client can read what
    it can still send without provoking a refusal.
    """
    seen = {}

    def handler(request):
        return httpx.Response(
            200,
            content=b'{"ok": true}',
            headers={
                "content-type": "application/json",
                "x-ratelimit-limit": "20",
                "x-ratelimit-remaining": "19",
                "x-ratelimit-reset": "60",
                "x-quota-limit": "300",
                "x-quota-remaining": "299",
                "x-quota-reset": "3600",
                "x-credit-balance": "4",
                "x-answer-of-a-family-the-client-does-not-know": "1",
            },
        )

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(key="the-api-key")
    answer = api.request("GET", "/product/")
    line = cli._status_line(answer)

    assert "x-ratelimit-limit=20" in line
    assert "x-quota-limit=300" in line
    assert "x-quota-remaining=299" in line
    assert "x-credit-balance=4" in line
    assert "x-answer-of-a-family-the-client-does-not-know" not in line


def test_the_status_line_carries_the_retry_after_of_a_refusal(monkeypatch):
    """A refusal of the rate limit says when to come back."""

    def handler(request):
        return httpx.Response(
            429,
            content=b'{"error": "Rate limit exceeded"}',
            headers={
                "content-type": "application/json",
                "x-ratelimit-limit": "20",
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "60",
                "retry-after": "60",
            },
        )

    _fake_transport(monkeypatch, handler)
    api = client.ApiClient(key="the-api-key")
    answer = api.request("GET", "/product/")
    line = cli._status_line(answer)

    assert "retry-after=60" in line
    assert "x-ratelimit-reset=60" in line


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


# ------------------------------------------------------------- the commands


runner = CliRunner()


def _run(monkeypatch, arguments, status=200, body='{"ok": true}'):
    """Run the CLI with a fake transport and return the result and the request."""
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["method"] = request.method
        return httpx.Response(
            status,
            content=body.encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-ratelimit-limit": "20",
                "x-ratelimit-remaining": "19",
            },
        )

    _fake_transport(monkeypatch, handler)
    monkeypatch.setenv("PARAZUN_API_KEY", "the-api-key")
    result = runner.invoke(cli.app, arguments)
    return result, seen


def test_the_product_command_asks_for_the_product_of_the_asin(monkeypatch):
    """The command of a noun is the operation of the noun."""
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 0
    assert seen["path"] == "/product"
    assert seen["params"] == {"asin": "B00FLYWNYQ"}
    assert json.loads(result.stdout) == {"ok": True}
    assert "HTTP 200" in result.stderr
    assert "x-ratelimit-limit=20" in result.stderr


def test_the_offers_command_asks_for_the_offers_of_the_product(monkeypatch):
    """The operation under the noun is a command under the noun."""
    result, seen = _run(monkeypatch, ["product", "offers", "B00FLYWNYQ"])
    assert result.exit_code == 0
    assert seen["path"] == "/product/offers"
    assert seen["params"] == {"asin": "B00FLYWNYQ"}


def test_the_reviews_command_names_the_parameters_of_the_api(monkeypatch):
    """The name of an option is the name of a parameter of the API."""
    result, seen = _run(
        monkeypatch,
        [
            "product",
            "reviews",
            "B00FLYWNYQ",
            "--sort-by",
            "recent",
            "--reviewer-type",
            "avp_only_reviews",
            "--filter-by-keyword",
            "coffee",
            "--page",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert seen["path"] == "/product/reviews"
    assert seen["params"] == {
        "asin": "B00FLYWNYQ",
        "sort_by": "recent",
        "reviewer_type": "avp_only_reviews",
        "filter_by_keyword": "coffee",
        "page": "2",
    }


def test_the_related_command_asks_for_the_related_asins(monkeypatch):
    """The path of the API is the path of the command."""
    result, seen = _run(monkeypatch, ["product", "related", "B00FLYWNYQ"])
    assert result.exit_code == 0
    assert seen["path"] == "/product/related-asins"
    assert seen["params"] == {"asin": "B00FLYWNYQ"}


def test_the_summaries_command_joins_the_asins(monkeypatch):
    """The parameter of the API takes the values separated by a comma."""
    result, seen = _run(
        monkeypatch, ["product", "summaries", "B00FLYWNYQ", "B000F0Q1SP"]
    )
    assert result.exit_code == 0
    assert seen["path"] == "/product/summaries"
    assert seen["params"] == {"asins": "B00FLYWNYQ,B000F0Q1SP"}


def test_the_search_command_asks_for_the_results_of_the_words(monkeypatch):
    """The search of the API is a command of the CLI."""
    result, seen = _run(monkeypatch, ["search", "coffee grinder"])
    assert result.exit_code == 0
    assert seen["path"] == "/search"
    assert seen["params"] == {"keywords": "coffee grinder"}


def test_the_search_command_takes_the_words_one_by_one(monkeypatch):
    """The words of a search are one argument or several.

    The design names `parazun search coffee grinder`, so the command has to
    take the words without the shell quoting them.
    """
    result, seen = _run(monkeypatch, ["search", "coffee", "grinder"])
    assert result.exit_code == 0
    assert seen["params"] == {"keywords": "coffee grinder"}


def test_the_search_aliases_command_asks_for_the_indexes(monkeypatch):
    """The aliases of the search are a command under the search."""
    result, seen = _run(monkeypatch, ["search", "aliases"])
    assert result.exit_code == 0
    assert seen["path"] == "/search/aliases"


def test_the_category_command_asks_for_the_categories(monkeypatch):
    """A noun whose operation needs no argument runs with no argument."""
    result, seen = _run(monkeypatch, ["category"])
    assert result.exit_code == 0
    assert seen["path"] == "/category"


def test_the_descendants_command_asks_for_the_descendants(monkeypatch):
    """The descendants of a category are a command under the category."""
    result, seen = _run(monkeypatch, ["category", "descendants", "1055398"])
    assert result.exit_code == 0
    assert seen["path"] == "/category/descendants"
    assert seen["params"] == {"node_id": "1055398"}


def test_the_departments_command_asks_for_the_departments(monkeypatch):
    """The departments of a marketplace are a command of their own."""
    result, seen = _run(monkeypatch, ["departments"])
    assert result.exit_code == 0
    assert seen["path"] == "/departments"


def test_the_deals_command_asks_for_the_deals(monkeypatch):
    """The deals of today are a command of their own."""
    result, seen = _run(monkeypatch, ["deals"])
    assert result.exit_code == 0
    assert seen["path"] == "/deals"


def test_the_bestseller_commands_ask_for_the_two_kinds(monkeypatch):
    """The best sellers have one command by category and one by department."""
    result, seen = _run(monkeypatch, ["bestseller", "by-category", "1055398"])
    assert result.exit_code == 0
    assert seen["path"] == "/bestseller/by-category"
    assert seen["params"] == {"node_id": "1055398"}

    result, seen = _run(monkeypatch, ["bestseller", "by-department", "kitchen"])
    assert result.exit_code == 0
    assert seen["path"] == "/bestseller/by-department"
    assert seen["params"] == {"alias": "kitchen"}


def test_the_new_releases_commands_ask_for_the_two_kinds(monkeypatch):
    """The new releases have one command by category and one by department."""
    result, seen = _run(monkeypatch, ["new-releases", "by-category", "1055398"])
    assert result.exit_code == 0
    assert seen["path"] == "/new-releases/by-category"
    assert seen["params"] == {"node_id": "1055398"}

    result, seen = _run(monkeypatch, ["new-releases", "by-department", "kitchen"])
    assert result.exit_code == 0
    assert seen["path"] == "/new-releases/by-department"
    assert seen["params"] == {"alias": "kitchen"}


def test_the_seller_command_asks_for_the_profile(monkeypatch):
    """The profile of a seller is a command of its own."""
    result, seen = _run(monkeypatch, ["seller", "A1B2C3D4E5"])
    assert result.exit_code == 0
    assert seen["path"] == "/seller"
    assert seen["params"] == {"seller_id": "A1B2C3D4E5"}


def test_the_seller_command_sends_the_flags_that_were_given(monkeypatch):
    """A flag that the caller did not give is not sent."""
    result, seen = _run(
        monkeypatch, ["seller", "A1B2C3D4E5", "--include-products"]
    )
    assert result.exit_code == 0
    assert seen["params"] == {"seller_id": "A1B2C3D4E5", "include_products": "true"}


def test_the_request_command_reaches_any_path(monkeypatch):
    """The escape hatch reaches a path that has no command."""
    result, seen = _run(monkeypatch, ["request", "/whatever", "--param", "a=1"])
    assert result.exit_code == 0
    assert seen["path"] == "/whatever"
    assert seen["params"] == {"a": "1"}


def test_the_cli_sends_only_the_parameters_that_the_caller_gave(monkeypatch):
    """The default of the API applies to the parameters that are not sent."""
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 0
    assert seen["params"] == {"asin": "B00FLYWNYQ"}
    assert "region" not in seen["params"]


def test_the_descendants_command_sends_no_marketplace(monkeypatch):
    """The operation of the API has no marketplace, so none is sent.

    The marketplace of the environment must not reach an operation that
    does not have one.
    """
    monkeypatch.setenv("PARAZUN_REGION", "DE")
    result, seen = _run(monkeypatch, ["category", "descendants", "1055398"])
    assert result.exit_code == 0
    assert "region" not in seen["params"]


def test_a_three_hundred_is_not_an_answer_the_cli_accepts(monkeypatch):
    """The exit code is 0 for a 2xx and 1 for every other answer."""
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ"], status=302)
    assert result.exit_code == 1
    assert result.stdout.strip() == ""


def test_the_marketplace_comes_from_the_environment(monkeypatch):
    """The environment names the marketplace of the answer."""
    monkeypatch.setenv("PARAZUN_REGION", "DE")
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 0
    assert seen["params"] == {"asin": "B00FLYWNYQ", "region": "DE"}


def test_the_marketplace_of_the_caller_wins_over_the_environment(monkeypatch):
    """The value of the caller is the value that is sent."""
    monkeypatch.setenv("PARAZUN_REGION", "DE")
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ", "--region", "JP"])
    assert result.exit_code == 0
    assert seen["params"] == {"asin": "B00FLYWNYQ", "region": "JP"}


def test_the_summaries_command_takes_the_value_of_the_api(monkeypatch):
    """The enumeration of the API is 1 and 0, so the option takes a value.

    A flag of the CLI would send "true" and "false", and the API takes
    neither of them.
    """
    result, seen = _run(
        monkeypatch, ["product", "summaries", "B00FLYWNYQ", "--all", "0"]
    )
    assert result.exit_code == 0
    assert seen["params"] == {"asins": "B00FLYWNYQ", "all": "0"}


def test_a_refusal_goes_to_stderr_and_the_exit_code_is_one(monkeypatch):
    """A refusal does not put the body of the refusal on stdout."""
    result, seen = _run(
        monkeypatch,
        ["product", "B00FLYWNYQ"],
        status=402,
        body='{"error": "No active quota."}',
    )
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "No active quota." in result.stderr
    assert "HTTP 402" in result.stderr


def test_the_body_of_the_answer_is_not_reformatted(monkeypatch):
    """The body of the API is the output of the CLI."""
    body = '{"b": 2, "a": [1, {"c": 3}]}'
    result, seen = _run(monkeypatch, ["product", "B00FLYWNYQ"], body=body)
    assert result.exit_code == 0
    assert result.stdout.strip() == body


def test_the_cli_without_a_credential_says_what_to_do(monkeypatch):
    """A machine with no credential is told how to get one."""
    monkeypatch.delenv("PARAZUN_API_KEY", raising=False)

    def handler(request):
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    result = runner.invoke(cli.app, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 1
    assert "parazun auth login" in result.stderr


def test_the_refresh_of_a_revoked_device_says_what_to_do(monkeypatch):
    """A refusal of the refresh names the cause and the way out."""

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    _fake_transport(monkeypatch, handler)
    with pytest.raises(oauth.OAuthError) as failure:
        oauth.refresh_access_token(
            "https://portal.parazun.test", "parazun-cli", "the-refresh-token"
        )
    assert failure.value.error == "invalid_grant"
    assert "signed the device out" in str(failure.value)
    assert "parazun auth login" in str(failure.value)


def test_the_command_of_a_revoked_device_says_what_to_do(monkeypatch):
    """The customer of a device that the portal revoked reads what to do."""
    config.store(_credentials(expires_at=config.expiry(-60)))

    def handler(request):
        if request.url.path.endswith("/identity/o/api/token"):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    result = runner.invoke(cli.app, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "signed the device out" in result.stderr
    assert "parazun auth login" in result.stderr


def test_the_message_of_a_dead_sign_in_names_the_idle_window(monkeypatch):
    """A sign in that died of inactivity names that cause."""
    deadline = 60 * 24 * 3600

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    _fake_transport(monkeypatch, handler)
    with pytest.raises(oauth.OAuthError) as failure:
        oauth.refresh_access_token(
            "https://portal.parazun.test", "parazun-cli", "the-refresh-token"
        )
    assert "idle for too long" in str(failure.value)
    assert "parazun auth login" in str(failure.value)
    assert deadline > 0


def test_the_dead_sign_in_deletes_the_file_of_the_credentials(monkeypatch):
    """A file that holds a secret that cannot be used is deleted."""
    path = config.store(_credentials(expires_at=config.expiry(-60)))

    def handler(request):
        if request.url.path.endswith("/identity/o/api/token"):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"ok": True})

    _fake_transport(monkeypatch, handler)
    result = runner.invoke(cli.app, ["product", "B00FLYWNYQ"])
    assert result.exit_code == 1
    assert not os.path.exists(path)
    assert "The file of the credentials is deleted" in result.stderr
    assert "parazun auth login" in result.stderr


def test_the_logout_names_the_page_of_the_portal(monkeypatch):
    """A token that lives on can be revoked on the page of the portal."""
    config.store(_credentials())

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_request"})

    _fake_transport(monkeypatch, handler)
    result = runner.invoke(cli.app, ["auth", "logout"])
    assert result.exit_code == 1
    assert "https://portal.parazun.test/keys/" in result.stderr


def test_the_status_names_the_credential_of_the_calls(monkeypatch):
    """The status says which credential the calls of this machine use."""
    config.store(_credentials())

    monkeypatch.delenv("PARAZUN_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["auth", "status"])
    assert result.exit_code == 0
    assert "Calls use:  the token of the sign in" in result.stdout

    monkeypatch.setenv("PARAZUN_API_KEY", "the-api-key")
    result = runner.invoke(cli.app, ["auth", "status"])
    assert result.exit_code == 0
    assert "Calls use:  the API key of the environment" in result.stdout


def test_the_status_says_the_truth_about_an_expired_token(monkeypatch):
    """An expired token is refreshed by the calls that send it, and by no other."""
    config.store(_credentials(expires_at=config.expiry(-60)))

    monkeypatch.delenv("PARAZUN_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["auth", "status"])
    assert "The next request refreshes it." in result.stdout

    monkeypatch.setenv("PARAZUN_API_KEY", "the-api-key")
    result = runner.invoke(cli.app, ["auth", "status"])
    assert "it is not refreshed." in result.stdout
    assert "The next request refreshes it." not in result.stdout
