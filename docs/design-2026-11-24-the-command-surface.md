# The command surface of the Parazun CLI

**Date:** 2026-11-24
**Status:** the contract for the build. Every decision below is stated with
its reason, so a reader can disagree with a decision and change it.

## The problem

The CLI is a thin wrapper. Every call is the same call with a different
path:

```
parazun request "/product/?asin=B00FLYWNYQ&region=US"
parazun request "/search?keywords=coffee%20grinder"
```

The caller has to know the path of the API, the name of every parameter,
and the type of every parameter. An agent that reads the documentation of
the API can make the call, but the CLI does not help it: the CLI gives no
name to the operations of the API, so the agent has to build the query
string itself.

The CLI should model the API. The name of a command should be the name of
the operation of the API, and the name of an option should be the name of
the parameter of the API.

## The ground truth

The published specification of the API is
`https://api.parazun.com/openapi.json`. It holds 22 paths.

**16 of them are live.** Five are retired (`/most-gifted/by-category`,
`/most-gifted/by-department`, `/most-wished-for/by-category`,
`/most-wished-for/by-department` and `/movers-and-shakers/by-department`)
and one is deprecated (`/bestseller`, in favour of `/bestseller/by-category`).

**THE RETIRED AND THE DEPRECATED PATHS GET NO COMMAND.** A command for a
path that the API no longer serves is a command that fails, and a customer
that learns it will remember the failure and not the API.

Every live operation is a GET with query parameters. No operation takes a
body. The `region` parameter is on every live operation but the one that
is scoped to the tree of a category, and its default is `US`. The `page`
parameter is on the six operations that answer a list.

## The command surface

| The command | The path of the API | The parameters of the command |
| --- | --- | --- |
| `parazun product <ASIN>` | `/product` | `--region` |
| `parazun product offers <ASIN>` | `/product/offers` | `--region`, `--zip-code`, `--page` |
| `parazun product reviews <ASIN>` | `/product/reviews` | `--region`, `--sort-by`, `--reviewer-type`, `--format-type`, `--media-type`, `--page`, `--filter-by-keyword` |
| `parazun product related <ASIN>` | `/product/related-asins` | `--region` |
| `parazun product summaries <ASIN>...` | `/product/summaries` | `--region`, `--format`, `--page`, `--all` |
| `parazun search <KEYWORD>` | `/search` | `--region`, `--search-alias`, `--node-id`, `--page` |
| `parazun search aliases` | `/search/aliases` | `--region` |
| `parazun category` | `/category` | `--region`, `--parent-id`, `--page`, `--size` |
| `parazun category descendants <NODE_ID>` | `/category/descendants` | `--level` |
| `parazun departments` | `/departments` | `--region` |
| `parazun deals` | `/deals` | `--region`, `--page` |
| `parazun bestseller by-category <NODE_ID>` | `/bestseller/by-category` | `--region` |
| `parazun bestseller by-department <ALIAS>` | `/bestseller/by-department` | `--region` |
| `parazun new-releases by-category <NODE_ID>` | `/new-releases/by-category` | `--region` |
| `parazun new-releases by-department <ALIAS>` | `/new-releases/by-department` | `--region` |
| `parazun seller <SELLER_ID>` | `/seller` | `--region`, `--include-products`, `--include-feedback`, `--products-limit`, `--feedback-limit` |
| `parazun request <PATH>` | any path | `--method`, `--param`, `--data` |
| `parazun auth login` | the device grant | `--no-browser`, `--scope` |
| `parazun auth status` | none | none |
| `parazun auth logout` | the revocation | none |

### The rules of the surface

**THE HIERARCHY OF THE COMMANDS IS THE HIERARCHY OF THE PATHS.** `/product`,
`/product/reviews` and `/product/offers` are three operations of one noun,
so they are one command group. `/search` and `/search/aliases` are two
operations of one noun, so they are one command group. A caller who knows
the path finds the command, and a caller who knows the command finds the
path.

**A NOUN WITH AN OPERATION OF ITS OWN IS A GROUP WITH A HIDDEN COMMAND.**
`parazun product <ASIN>` and `parazun product offers <ASIN>` are both
commands, so the group of the noun carries the operation of the noun as a
hidden command, and the group sends the first argument to it when the
first argument is not the name of an operation under the noun. The
mechanism is one class, `NounGroup`, and it uses the two public hooks of
the group: the parsing of the arguments and the resolution of the command.
No attribute of the framework is used that the framework does not use
itself.

**THE RANKING OPERATIONS KEEP THE TWO VARIANTS.** `/bestseller` has one
operation by category and one by department, and the two take different
arguments, so they are two commands under one group. The names are the
words of the path, so the surface teaches the API.

**THE NAME OF AN OPTION IS THE NAME OF THE PARAMETER**, with the hyphen of
the API kept: `--sort-by`, `--reviewer-type`, `--format-type`,
`--media-type`, `--filter-by-keyword`, `--zip-code`, `--parent-id`,
`--node-id`, `--search-alias`, `--include-products`,
`--include-feedback`, `--products-limit`, `--feedback-limit`.

**THE PARAMETER NAMES OF THE API ARE NOT ALWAYS SINGULAR.** `/search` takes
`keywords` and `/product/summaries` takes `asins`, and both hold one string
with the values separated by a comma. The COMMAND takes the value in the
shape a person would type: `parazun search coffee grinder` and
`parazun product summaries B00FLYWNYQ B000F0Q1SP`. The name of the command
is what the caller thinks of, and the parameter is what the API needs.

**A PARAMETER THAT THE API RETIRED GETS NO OPTION.** The parameter
`books_new` of the search is marked DEPRECATED in the specification and it
is no longer functional, so the CLI has no option for it. The same rule
holds for the retired paths: an option that the API no longer serves is an
option that fails.

**`--region` IS ON EVERY COMMAND THAT TAKES IT**, and its value is the value
of the caller, or the value of `PARAZUN_REGION` of the environment, or
nothing at all. **ONLY THE COMMAND OF AN OPERATION THAT HAS A MARKETPLACE
CARRIES THE OPTION**, so the marketplace is sent only to the operations of
the API that take one: `/category/descendants` has none, and a marketplace
that the API does not have is a parameter the API ignores or refuses.

**`parazun request` STAYS.** It is the escape hatch: an operation of the
API that has no command yet is reachable on the day it ships, and a caller
that needs a parameter this surface does not name is not blocked. It is the
same call it is today.

## The parameters the CLI sends

**THE CLI SENDS ONLY THE PARAMETERS THAT THE CALLER GAVE.** A parameter that
the caller did not give is not sent, so the default of the API applies.

The reason is that the default of a parameter lives in the API, and a copy of
it in the CLI is a second copy of a value that the API owns. The copy drifts
when the API changes, and the drift is silent: the caller asks for the newest
behaviour and the CLI sends the old value.

So every option of every command has NO default of its own. The option that
the caller did not use is left out of the query, and the API answers with its
own default.

**`--region` IS THE ONE THAT THE ENVIRONMENT NAMES.** The value of
`PARAZUN_REGION` of the environment is sent when the caller did not name a
region, and no region is sent when the environment is silent. The environment
is a way for the caller to give a value, so the rule holds.

**THE HELP OF AN OPTION NAMES THE DEFAULT OF THE API AND NOT A COPY OF
IT.** The published specification of the API names every default, and the
CLI holds no copy of any of them.

## The output contract

**ONE CONTRACT FOR EVERY COMMAND THAT CALLS THE API.**

| The channel | The content |
| --- | --- |
| stdout | the body of the API, exactly as the API answered it |
| stderr | one line: the status and the rate limit headers the API sent |
| the exit code | 0 when the API answered 2xx, 1 for every other answer |

**THE BODY GOES TO STDOUT AND NOTHING ELSE DOES.** The CLI exists for the
agents of the customers, and an agent reads stdout. A body with a header
line in front of it is not JSON, and a caller that pipes the answer into
`jq` gets nothing. The status and the rate limit go to stderr, so a person
sees them and a pipe does not.

**AN ANSWER THAT IS NOT A 2xx IS A REFUSAL**, and its body goes to stderr
with the exit code 1. A 3xx is not an answer the CLI can use, so it is
handled as a refusal.

**A PARAMETER WHOSE VALUE IS AN ENUMERATION OF THE API TAKES THE VALUE OF
THE API.** The parameter `all` of the product summaries is the enumeration
`["1", "0"]`, so the option takes `1` or `0`. A flag of the CLI would send
`true` and `false`, and the API takes neither of them. The value the
caller gives is the value that is sent, untranslated.

**THE HELP MAY NAME THE VALUES OF AN ENUMERATION.** A stale list is a drift
of the documentation and not of the behaviour: the value the caller gives
is the value that is sent, so a value the API adds later works before the
help mentions it. The DEFAULT is a different thing: a copy of a default
would change what the CLI does, so the CLI holds no copy of any default,
and the help of an option points at the default of the API instead of
naming its value.

**THE STATUS LINE IS ONE LINE.** It names the status and every rate limit
header the answer carried:

```
HTTP 200 | x-ratelimit-limit=20 x-ratelimit-remaining=19 x-ratelimit-reset=60
```

**A REFUSAL GOES TO STDERR AND THE EXIT CODE IS 1.** The body of a refusal
is the JSON of the API, and it names the cause, so it is printed on stderr
and never on stdout.

**THE BODY OF THE API IS NOT REFORMATTED.** The CLI does not reformat the
JSON, does not sort the keys and does not pretty-print. The body of the
API is the data of the API, and a change of the CLI must not change the
data. A caller that wants a summary pipes the answer into `jq`.

## The sign in

`parazun auth login`, `parazun auth status` and `parazun auth logout` do
not change. The device grant works, the credentials live in
`~/.config/parazun/credentials.json` with the mode 0600, and the token is
refreshed on its own.

## The shape of the code

| The file | What it holds |
| --- | --- |
| `src/parazun_cli/cli.py` | the Typer app, the command groups, the commands, the output contract |
| `src/parazun_cli/client.py` | the HTTP client, the credential, the refresh. It does not change |
| `src/parazun_cli/config.py` | the credential store and the values of the environment. It gains the region |
| `src/parazun_cli/oauth.py` | the device grant. It does not change |
| `tests/test_cli.py` | the tests of the commands |

**THE PATH OF AN OPERATION IS NAMED IN ONE PLACE.** Every command builds
its own path, and no path is written twice.

**THE MODULES STAY SMALL.** The new commands are thin: each one names its
path, names its parameters, calls the client and hands the answer to the
output. The shared work — the credential, the output, the region default —
lives in one helper each.

## The rules of the build

1. **No new dependency.** The project has `typer` and `httpx`, and it keeps
   them. Python 3.10 or later.
2. **The tests never touch the network.** The tests drive the commands with
   a fake transport, the way the tests do today, and they assert the path
   that the command asked for, the parameters it sent, the body that
   reached stdout, the line that reached stderr and the exit code.
3. **Every live operation has a test.** The test names the command and
   asserts the path and the parameters, so an operation that loses its
   command fails the suite.
4. **The style of the project stays.** A module docstring that says what
   the module is for, a docstring on every command that says what it does,
   and simple English.
5. **The README is rewritten.** It shows the new surface, and it keeps the
   section on the values of the environment.

## What this design does NOT do

- **No configuration file.** The values of the environment are the
  configuration, and a file would be a second place for the same value.
- **No cache.** The API caches what it can cache, and a cache in the CLI
  would answer with stale data.
- **No command for a retired path.**
- **No change to the client, the sign in or the credential store.**
- **No output format of the CLI's own.** The body of the API is the
  output. A summary would be a second shape of the same data, and it would
  have to be kept in step with the API.
