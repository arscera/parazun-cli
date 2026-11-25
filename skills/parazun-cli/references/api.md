# The contract of the Parazun Amazon Data API

What a caller needs when it calls the API without the CLI, or when it needs
to read the surface of the API for itself.

## The addresses

| The surface | The address |
| --- | --- |
| the API | `https://api.parazun.com` |
| the portal, where the key and the tokens live | `https://portal.parazun.com` |
| the published specification, public and without a key | `https://api.parazun.com/openapi.json` |
| the interface, on the site | `https://parazun.com/docs/` |
| the interface, on the portal | `https://portal.parazun.com/docs/` |
| the keys of a customer | `https://portal.parazun.com/keys/` |
| the plans and the credit packs | `https://portal.parazun.com/subscriptions/pricing/` |

The site holds a COPY of the specification, taken when it builds, so the
specification on the API host is the fresh one. Read that one.

## The credential

One of two headers carries the credential, and the prefix is part of the
value:

```
Authorization: Api-Key <key>
Authorization: Bearer <token>
```

A bare key without the prefix is refused with 401.

- **The API key** belongs to a customer and is created on the page of the
  API keys of the portal. The page lists the keys, the last use of each and
  the devices that signed in to the account.
- **The bearer token** comes from the device grant. It lives one hour, the
  CLI refreshes it on its own, and the refresh token rotates on every
  refresh.

**THE KEY OF THE ENVIRONMENT WINS OVER THE TOKEN OF THE SIGN IN.** The key
is the credential the caller gave for this call, and the token is the state
of the machine, which may hold the account of another customer. A machine
caller that sets a key is metered against the account of the key, and a
client that sends the key does not refresh the token.

**The quota, the rate limit and the credits of a bearer token come from the
USER**, so a token of a customer enters the same admission as the key of
the same customer. There is no change of entitlement.

## The shape of a request

Every live operation is a GET with query parameters. No operation takes a
body, and there is no operation that writes.

The parameters that are on every operation are `region` (whose default is
`US`) and, on the operations that answer a list, `page` (whose default is
`1`). The operation of the descendants of a category takes no marketplace.

## The refusals

Every refusal answers a JSON body of one key, `error`, and the message
names the cause.

| The status | What it means | The body |
| --- | --- | --- |
| 401 | the credential is missing or not valid | `API Key required.`, `Invalid API Key` or `Invalid access token` |
| 402 | the allowance of the plan is used up and the credit balance is empty | the cause, and the answer carries the `X-Quota-*` headers |
| 403 | the credential carries no plan and no allowance for this API | the cause |
| 410 | the listing of the request is retired | a `RetiredListing`: the message, the replacements, the research and the date of the measurement |
| 422 | a parameter does not fit the operation | a `HTTPValidationError`: the detail of the field |
| 429 | the rate limit of the customer is spent | the cause, and the answer carries the `X-RateLimit-*` headers |

**A 410 IS NOT A FAILURE OF THE CALLER.** It means the listing of that
request was retired, and the body names the replacements.

## The headers of the answer

| The header | What it carries |
| --- | --- |
| `X-RateLimit-Limit` | the requests per minute of the plan |
| `X-RateLimit-Remaining` | the requests of the minute that are left |
| `X-RateLimit-Reset` | the seconds until the minute starts again |
| `X-Quota-Limit` | the allowance of the period |
| `X-Quota-Remaining` | the allowance of the period that is left |
| `X-Quota-Reset` | the seconds until the period starts again |
| `X-Credit-Balance` | the credits that are left |

The combined capacity is the remaining allowance plus the credits that are
left, so a client never has to provoke a refusal to learn what it can
still send.

**The status line of the CLI carries every header of those families.** The
client keeps the families `x-ratelimit-`, `x-quota-` and `x-credit` plus
the `Retry-After`, so the rate limit, the allowance and the credit balance
are all in the status line, and a header the API adds later reaches it
without a change in the client.

## The plans and the limits

| The plan | The allowance of the period | The requests per minute |
| --- | --- | --- |
| Free | 300 | 20 |
| Pro | 20,000 | 100 |
| Ultra | 75,000 | 150 |
| Mega | 300,000 | 200 |

The credit packs add to the allowance of the period: a pack of $4 holds
20,000 requests, a pack of $20 holds 75,000 and a pack of $100 holds
300,000.

The plans on the site are $0, $20, $60 and $200 a month.

## The retired paths

The API no longer serves these, and the CLI has no command for them:

- `/most-gifted/by-category`
- `/most-gifted/by-department`
- `/most-wished-for/by-category`
- `/most-wished-for/by-department`
- `/movers-and-shakers/by-department`

`/bestseller` is deprecated in favour of `/bestseller/by-category` and
`/bestseller/by-department`. The parameter `books_new` of the search is
deprecated and not functional.

**A command for a path that the API no longer serves is a command that
fails**, and a caller that learns it remembers the failure and not the API.

## The data

The catalogue of the answers is the `components.schemas` of the
specification. The shapes that carry most of the use:

| The shape | The keys |
| --- | --- |
| `Product` | `asin`, `title`, `subtitle`, `brand`, `price` (amount, currency, list price), `images`, `features`, `description`, `overview`, `categories`, `best_seller_rank`, `availability`, `prime`, `amazons_choice`, `reviews` (the average and the count), `author`, `info`, `variants`, `comparison`, `sold_by`, `ships_from` |
| `ProductSummary` | `asin`, `title`, `price`, `list_price`, `currency`, `availability`, `avg_rating`, `num_ratings`, `best_seller`, `prime`, `image`, `utc_date` |
| `RecommendedSearchResult` | `asin`, `title`, `price`, `images`, `position`, `badge`, `sponsored`, `recommended`, `prime`, `reviews`, `variants`, `availability` |
| `Review` | `review_id`, `title`, `review_text`, `rating`, `review_date`, `reviewer`, `verified_purchase`, `num_helpful`, `images`, `video_url`, `specs` |
| `ProductCategory` | `node_id`, `name`, `link` |
| `Department` | `alias`, `name`, `link` |
| `ProductRank` | `rank`, `asin`, `title`, `price`, `reviews` |
| `DealResult` | `asin`, `title`, `image`, `percentage_discount_off`, `last_updated` |
| `RetiredListing` | `error`, `message`, `list_type`, `replacements`, `research`, `measured_on` |
