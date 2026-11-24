# parazun-cli

The command line client of the [Parazun API](https://parazun.com).

The CLI models the API. The name of a command is the name of an operation
of the API, and the name of an option is the name of a parameter of the
API.

```
parazun product B00FLYWNYQ
parazun search "coffee grinder"
parazun product reviews B00FLYWNYQ --sort-by recent
```

## Install

```
uv tool install git+https://github.com/arscera/parazun-cli.git
```

or, from a clone of this repository:

```
uv tool install .
```

The command is `parazun`.

## Sign in

```
parazun auth login
```

The CLI prints an address and a code. It opens a browser when it can. The
customer signs in to the portal and allows the device, and the CLI signs
itself in.

The sign in needs no browser on the machine of the CLI, so it works on a
server over SSH. The browser of the customer can be on another machine.

The credentials are stored in `~/.config/parazun/credentials.json`. The
file is readable by the owner alone. The access token lives one hour, and
the CLI refreshes it on its own, so the customer stays signed in.

## Sign out

```
parazun auth logout
```

The CLI revokes the token at the portal and deletes the file of the
credentials.

A device can also be signed out without the CLI: the page of the API keys
of the portal lists the devices that signed in to the account, and it
revokes one of them. The CLI says so when the portal revoked a device
and the CLI asks for a new token.

## The commands

| The command | What it does |
| --- | --- |
| `parazun product <ASIN>` | The product of an ASIN. |
| `parazun product offers <ASIN>` | The offers of a product. |
| `parazun product reviews <ASIN>` | The reviews of a product. |
| `parazun product related <ASIN>` | The ASINs of the related products. |
| `parazun product summaries <ASIN>...` | The summaries of a list of products. |
| `parazun search <KEYWORD>` | The results of a search. |
| `parazun search aliases` | The indexes that a search can use. |
| `parazun category` | The categories of a marketplace. |
| `parazun category descendants <NODE_ID>` | The descendants of a category. |
| `parazun departments` | The departments of a marketplace. |
| `parazun deals` | The deals of today. |
| `parazun bestseller by-category <NODE_ID>` | The best sellers of a category. |
| `parazun bestseller by-department <ALIAS>` | The best sellers of a department. |
| `parazun new-releases by-category <NODE_ID>` | The new releases of a category. |
| `parazun new-releases by-department <ALIAS>` | The new releases of a department. |
| `parazun seller <SELLER_ID>` | The profile of a seller. |
| `parazun request <PATH>` | Any path of the API. The way to an operation that has no command yet. |
| `parazun auth login` | Sign in with the device grant. |
| `parazun auth status` | The state of the sign in of this machine. |
| `parazun auth logout` | Revoke the token and delete the credentials. |

`parazun --help` and `parazun <command> --help` name every option of every
command.

## The output

The CLI prints three things and they never mix:

- **stdout** carries the body of the answer of the API, exactly as the API
  answered it. A pipe of stdout is the body of the API and nothing else.
- **stderr** carries one line: the status and the rate limit of the answer.
- **the exit code** is 0 when the API answered and 1 when it refused. A
  refusal puts the body of the refusal on stderr.

```
$ parazun product B00FLYWNYQ | jq -r .title
Instant Pot Duo 6 Qt 7-in-1 Electric Pressure Cooker, Stainless Steel
```

## The values of the environment

| Name | What it is | Default |
| --- | --- | --- |
| `PARAZUN_API_URL` | The address of the API. | `https://api.parazun.com` |
| `PARAZUN_PORTAL_URL` | The address of the portal, where the tokens come from. | `https://portal.parazun.com` |
| `PARAZUN_CLIENT_ID` | The id of the public client. | `parazun-cli` |
| `PARAZUN_API_KEY` | An API key, for a machine caller. | none |
| `PARAZUN_REGION` | The marketplace of the answer. | the default of the API |
| `PARAZUN_CONFIG_DIR` | The directory of the credentials file. | `~/.config/parazun` |

The API key of the environment wins over the token of the sign in. A
machine that carries a key needs no sign in.

**THE CLI SENDS ONLY THE PARAMETERS THAT THE CALLER GAVE.** The default of
a parameter lives in the API, so a parameter that the caller did not give
is not sent and the default of the API applies. The `--region` option is
the one that the environment can name, with the value of `PARAZUN_REGION`.

## The rules of the client

- The token is sent as `Authorization: Bearer <token>`.
- The token endpoint wants a body of the form
  `application/x-www-form-urlencoded`.
- The refresh token is rotated on every refresh, so the file is written
  again each time.
- The device grant issues no `id_token`. The API reads the token row, so
  the CLI needs none.

## License

MIT. See [LICENSE](LICENSE).
