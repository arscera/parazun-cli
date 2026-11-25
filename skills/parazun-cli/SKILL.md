---
name: parazun-cli
description: Install the Parazun CLI, sign it in, and call the Parazun Amazon Data API from a shell or from an agent. Use when a task needs Amazon product, search, category, review, offer, seller, deal, best-seller or new-release data through parazun.com, when the `parazun` command must be signed in with the device grant or with an API key, when a call is refused or the exit code is 1, or when a caller needs the raw API contract (the paths, the credential headers, the rate limits, the refusals and the plans).
---

# The Parazun CLI and the Parazun Amazon Data API

The Parazun Amazon Data API answers questions about Amazon: a product, a
search, a category tree, the reviews of a product, the offers of a product,
a seller, the deals of the day, the best sellers of a category, the new
releases of a category.

The CLI is the command line client of that API. **The CLI models the API**:
the name of a command is the name of an operation of the API, and the name
of an option is the name of a parameter of the API. A caller who knows the
path of the API finds the command, and a caller who knows the command finds
the path.

The published specification of the API is the ground truth of the surface.
Read it with the script of this skill instead of trusting a copy of it:
`scripts/api_surface.py`.

## Quickstart

### 1. Install the CLI

Three routes. Pick one.

| Route | Command | When |
| --- | --- | --- |
| the repository | `uv tool install git+https://github.com/arscera/parazun-cli.git` | a machine that runs the agent. The binary lands in the tool directory of the user |
| a clone | `uv tool install .` from the root of a clone | a customer with the source |
| the published repository | `uv tool install git+https://github.com/arscera/parazun-cli.git` | a customer, once the repository is public |

The command is `parazun`. It needs Python 3.10 or later.

**In this checkout, use the virtual environment of the repository**:
`./.venv/bin/parazun`. The `uv tool install` route puts the
binary in the tool directory of the user, which is outside the checkout,
and a command that names a path outside the checkout is refused. Set
`UV_TOOL_DIR` to a directory inside the checkout when the route has to be
used here.

### 2. Sign in

Two credentials exist. Use the one that fits the caller.

- **A person at a terminal** signs in with the device grant:
  `parazun auth login`. The command prints an address and a code, opens a
  browser when it can, and the customer allows the device in the portal. The
  browser can be on ANOTHER machine, so the sign in works over SSH.
- **A machine or an agent** carries an API key in the environment:
  `PARAZUN_API_KEY=<key>`. No sign in, no browser, no token.

The API key of a customer is on the page of the API keys of the portal:
`https://portal.parazun.com/keys/`.

### 3. Make the first call

```
parazun product B00FLYWNYQ
parazun search "coffee grinder"
parazun product reviews B00FLYWNYQ --sort-by recent
```

The body of the answer of the API goes to stdout, so a pipe reads JSON and
nothing else:

```
parazun product B00FLYWNYQ | jq -r .title
```

### 4. Check the setup

`scripts/check_setup.py` of this skill checks the install, the credential
and one live call, and prints one line per check. Run it from the root of
the checkout.

### 5. Discover the ids the commands need

The commands take ids, and the API is where they come from.

| The id | The command that finds it |
| --- | --- |
| the ASIN of a product | `parazun search "coffee grinder"` — every result carries `asin` |
| the node id of a category | `parazun category` — every category carries `node_id` |
| the tree under a category | `parazun category descendants <NODE_ID>` |
| the alias of a department | `parazun departments` — every department carries `alias` |
| the id of a seller | `parazun product offers <ASIN>` — every offer names the seller |

## Install

`uv tool install <path>` builds the wheel and puts the `parazun` command on
the path of the tool directory. `pip install .` in a virtual environment of
your own works the same way.

The project has two dependencies and no more: `httpx` and `typer`.

**The GitHub route needs the repository to be public.** A customer who
cannot reach the repository installs the client from a clone, and the skill
of the repository comes with the clone.

## Sign in

### The device grant

`parazun auth login` runs the device grant of RFC 8628:

1. the terminal asks the provider for a device code,
2. the provider answers a verification address and a user code,
3. the customer opens the address, signs in to the portal and allows the
   device,
4. the terminal polls the token endpoint and gets the pair of tokens,
5. the terminal writes the credentials and says where.

The flow needs no browser on the machine of the terminal and no open port,
so it works on a server. Pass `--no-browser` to print the address and the
code without opening one.

### The credentials

The credentials live in `~/.config/parazun/credentials.json`. The directory
has the mode 0700 and the file has the mode 0600, so the file is readable
by the owner alone. `PARAZUN_CONFIG_DIR` moves the directory, which is how
a test and a real run never share the file.

The access token lives one hour. The CLI refreshes it on its own, before a
request that would use an expired token and once more when the API refuses
a token with 401. **A client that sends the API key does not refresh the
token**, because it does not send it. **The refresh token rotates on every
refresh**, so the file is written again each time.

`parazun auth status` prints the state of the sign in of the machine, names
the file, and names the credential the calls of that machine will use.
`parazun auth logout` revokes the token at the portal and deletes the file.

**A device can be signed out without the CLI.** The page of the API keys of
the portal lists the devices that signed in to the account and revokes one
of them. The CLI says so when the portal revoked a device and the refresh
answers `invalid_grant`: the sign in of that device is over, and
`parazun auth login` signs it in again.

### The values of the environment

| Name | What it is | Default |
| --- | --- | --- |
| `PARAZUN_API_URL` | the address of the API | `https://api.parazun.com` |
| `PARAZUN_PORTAL_URL` | the address of the portal, where the tokens come from | `https://portal.parazun.com` |
| `PARAZUN_CLIENT_ID` | the id of the public client | `parazun-cli` |
| `PARAZUN_API_KEY` | an API key, for a machine caller | none |
| `PARAZUN_REGION` | the marketplace of the answer | the default of the API |
| `PARAZUN_CONFIG_DIR` | the directory of the credentials file | `~/.config/parazun` |

`PARAZUN_REGION` is the only parameter the environment can name. Every
other option of every command has NO default of its own, so a parameter
that the caller did not give is not sent and the default of the API applies.

## The commands

The table of every command, with the path of the API and the parameters of
each, is in `references/commands.md`. The commands that carry most of the
use:

| The command | What it answers |
| --- | --- |
| `parazun product <ASIN>` | the product of an ASIN |
| `parazun product offers <ASIN>` | the offers of a product |
| `parazun product reviews <ASIN>` | the reviews of a product |
| `parazun product related <ASIN>` | the ASINs of the related products |
| `parazun product summaries <ASIN>...` | the summaries of a list of products |
| `parazun search <KEYWORD>` | the results of a search |
| `parazun search aliases` | the indexes a search can use |
| `parazun category` | the categories of a marketplace |
| `parazun category descendants <NODE_ID>` | the descendants of a category |
| `parazun departments` | the departments of a marketplace |
| `parazun deals` | the deals of today |
| `parazun bestseller by-category <NODE_ID>` | the best sellers of a category |
| `parazun bestseller by-department <ALIAS>` | the best sellers of a department |
| `parazun new-releases by-category <NODE_ID>` | the new releases of a category |
| `parazun new-releases by-department <ALIAS>` | the new releases of a department |
| `parazun seller <SELLER_ID>` | the profile of a seller |
| `parazun request <PATH>` | any path of the API. The escape hatch |
| `parazun auth login` / `status` / `logout` | the sign in of the machine |

`parazun --help` and `parazun <command> --help` name every option of every
command.

**The words of a search are several arguments.** `parazun search coffee
grinder` sends the two words. The command joins them with a space, because
the parameter of the API is one string.

## The output contract

One contract for every command that calls the API.

| The channel | The content |
| --- | --- |
| stdout | the body of the API, exactly as the API answered it |
| stderr | one line: the status and the capacity of the customer |
| the exit code | 0 when the API answered 2xx, 1 for every other answer |

**The body goes to stdout and nothing else does.** A body with a header
line in front of it is not JSON, and a pipe into `jq` gets nothing. A
refusal is not a body: it goes to stderr and the exit code is 1.

The body is not reformatted. The CLI does not sort the keys and does not
pretty-print. A caller that wants a summary pipes the answer into `jq`.

## The traps

Each one of these was measured, not read.

**1. The path of `parazun request` must start with a slash.** The client
joins the base address and the path with no separator, so a path without a
slash asks for the host `api.parazun.comproduct` and the failure is a
name-resolution error that says nothing about the path. **In this checkout
a command string that carries a leading slash is refused by the exec
guard**, so call the escape hatch from a script.

**2. The API key of the environment wins over the token of the sign in.**
The key is the credential the caller gave for this call, and the token is
the state of the machine, which may hold the account of another customer.
A machine caller that sets a key is metered against the account of the
key, never against the account of a session it never asked for. A client
that sends the key does not refresh the token either. To use the token of
the sign in, remove the key from the environment.

**3. `PARAZUN_API_URL` is ignored on a signed-in machine.** The base address
of a signed-in client comes from the credentials file, not from the
environment. Sign in again with the address set, or use a fresh
`PARAZUN_CONFIG_DIR`.

**4. The CLI sends only the parameters that the caller gave.** The default
of a parameter lives in the API, and a copy of it in a script drifts
silently. Read the default from the specification, not from a copy.

**5. `--all` takes the value of the API, not a boolean.** The parameter is
the enumeration `["1","0"]`, so the option takes `1` or `0`. A flag sends
`true` and `false` and the API answers 422.

**6. `--region` is not on every command.** The operation of the descendants
of a category has no marketplace, and the API ignores or refuses a
marketplace it does not have.

**7. The status line carries the capacity of the customer.** The API sends
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`,
`X-Quota-Limit`, `X-Quota-Remaining`, `X-Quota-Reset` and
`X-Credit-Balance` on every admitted answer, and `Retry-After` on a
refusal of the rate limit, and the CLI keeps every header of those
families. Read the allowance and the credit balance from the status line
when a plan has to be measured.

**8. A retired path and a deprecated path have no command.** The retired
ones are the `most-gifted` and `most-wished-for` paths and
`movers-and-shakers`; the deprecated one is `bestseller` without a variant.
The parameter `books_new` of the search is deprecated and not functional.

**9. The refresh token rotates.** A copy of the credentials file is a copy
of a token that is already dead. Let the CLI write the file.

## The API without the CLI

The API answers a plain HTTP GET. The credential is one of two headers:

```
Authorization: Api-Key <key>
Authorization: Bearer <token>
```

Every live operation is a GET with query parameters, and the body of the
answer is JSON. The refusals are 401, 402, 403, 410, 422 and 429, and each
one names its cause in the body.

- the specification: `https://api.parazun.com/openapi.json` (public, no key)
- the interface: `https://parazun.com/docs/` and `https://portal.parazun.com/docs/`
- the key of a customer: `https://portal.parazun.com/keys/`

The refusals, the headers of the answer, the plans and the limits are in
`references/api.md`.

## The resources of this skill

| The resource | What it is for |
| --- | --- |
| `references/commands.md` | every command, the path of the API, the parameters, the defaults and the enumerations |
| `references/api.md` | the contract of the API: the credential, the refusals, the headers, the plans, the limits |
| `scripts/api_surface.py` | read the published specification and print the live surface |
| `scripts/check_setup.py` | check the install, the credential and one live call |
