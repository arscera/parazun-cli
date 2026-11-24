# parazun-cli

The command line client of the Parazun API.

The CLI signs a customer in with the OAuth device grant and calls the API
with the access token. The API key of the environment is honoured as well,
so a machine caller needs no browser and no sign in.

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

## Use the API

```
parazun request /product/?asin=B00FLYWNYQ
parazun request /product/ --param asin=B00FLYWNYQ --param region=US
parazun request /search --method POST --data '{"q": "coffee grinder"}'
```

The CLI prints the rate limit headers, the status and the body of the
answer.

## The other commands

| Command | What it does |
| --- | --- |
| `parazun auth login` | Sign in with the device grant. |
| `parazun auth status` | Show the state of the sign in of this machine. |
| `parazun auth logout` | Revoke the token and delete the credentials. |
| `parazun request PATH` | Send one request to the API. |

## The values of the environment

| Name | What it is | Default |
| --- | --- | --- |
| `PARAZUN_API_URL` | The address of the API. | `https://api.parazun.com` |
| `PARAZUN_PORTAL_URL` | The address of the portal, where the tokens come from. | `https://portal.parazun.com` |
| `PARAZUN_CLIENT_ID` | The id of the public client. | `parazun-cli` |
| `PARAZUN_API_KEY` | An API key, for a machine caller. | none |
| `PARAZUN_CONFIG_DIR` | The directory of the credentials file. | `~/.config/parazun` |

The API key of the environment wins over the token of the sign in. A
machine that carries a key needs no sign in.

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
