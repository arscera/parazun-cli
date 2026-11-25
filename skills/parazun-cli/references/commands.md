# The commands of the CLI

Every command of the CLI, the path of the API it calls, and the parameters
it sends. The name of a command is the name of an operation of the API, and
the name of an option is the name of a parameter of the API.

Read `scripts/api_surface.py` of this skill for the live surface. The table
below is the shape of the CLI; the script is the shape of the API.

## The table

| The command | The path of the API | The options |
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

**The hierarchy of the commands is the hierarchy of the paths.** `/product`,
`/product/reviews` and `/product/offers` are three operations of one noun,
so they are one command group. `/search` and `/search/aliases` are two
operations of one noun, so they are one command group.

**A noun with an operation of its own is a group with a hidden command.**
`parazun product <ASIN>` and `parazun product offers <ASIN>` are both
commands, so the group of the noun sends the first argument to the
operation of the noun when the first argument is not the name of an
operation under the noun.

**The paths that the API no longer serves have no command.** The retired
paths are `/most-gifted/by-category`, `/most-gifted/by-department`,
`/most-wished-for/by-category`, `/most-wished-for/by-department` and
`/movers-and-shakers/by-department`. The deprecated path is `/bestseller`,
and the variants `/bestseller/by-category` and `/bestseller/by-department`
replace it.

## The parameters and their defaults

The defaults below are the defaults of the API, read from the published
specification. **The CLI holds no copy of any of them** — it sends only the
parameters that the caller gave, so the default of the API applies to the
rest. Read them from the specification when a script needs them, so the
script does not carry a copy that drifts.

| The parameter | The default of the API | The enumeration |
| --- | --- | --- |
| `region` | `US` | the marketplaces of Amazon |
| `page` | `1` | |
| `size` (of the categories) | `1000` | |
| `sort_by` (of the reviews) | `helpful` | `helpful`, `recent` |
| `reviewer_type` (of the reviews) | `all_reviews` | `all_reviews`, `avp_only_reviews` |
| `format_type` (of the reviews) | `all_formats` | `all_formats`, `current_format` |
| `media_type` (of the reviews) | `all_contents` | `all_contents`, `media_reviews_only` |
| `format` (of the summaries) | `json` | the specification names no enumeration; the help of the option names `json` and `csv` |
| `all` (of the summaries) | `1` | `1`, `0` — NOT a boolean |
| `search_alias` (of the search) | `aps` | the aliases of `/search/aliases` |
| `include_products` (of the seller) | `false` | a boolean |
| `include_feedback` (of the seller) | `false` | a boolean |
| `products_limit` (of the seller) | `24` | |
| `feedback_limit` (of the seller) | `5` | |
| `books_new` (of the search) | — | DEPRECATED and not functional, so no option carries it |

**A parameter whose value is an enumeration of the API takes the value of
the API.** The value the caller gives is the value that is sent, and it is
not translated. A flag that sends `true` and `false` is refused with 422
when the API takes `1` and `0`.

## The commands and the shape of the answer

| The command | The shape of the answer |
| --- | --- |
| `product` | a `Product`: the title, the price, the images, the features, the overview, the categories, the best seller rank, the reviews (the average and the count), the author, the information, the offers, the variants and the comparison |
| `product offers` | an `Offers`: the list of the offers, each with the condition, the price, the seller and the place it ships from |
| `product reviews` | a `Reviews`: the reviews, the insights and the summary |
| `product related` | a `RelatedProducts`: the related, the bought together and the sponsored products |
| `product summaries` | a `BulkProducts`: the summaries of the products, with the price, the availability, the rating and the date |
| `search` | a `RecommendedSearchResults`: the results, the page and the statistics of the search |
| `search aliases` | a `SearchAliases`: the aliases a search can use |
| `category` | a `LargePage_ProductCategory_`: the categories with the node id, the name and the link |
| `category descendants` | a `ProductCategoryDescendants`: the descendants of the category |
| `departments` | a `Departments`: the departments with the alias, the name and the link |
| `deals` | a `Deals`: the deals of the day with the discount and the date |
| `bestseller` | a `BestSellers`: the rankings of the category or the department |
| `new-releases` | a `NewReleases`: the rankings of the new releases |
| `seller` | a `Seller`: the name, the id, the link, whether the seller is fulfilled by Amazon, and the products and the feedback when they are asked for |

## The escape hatch

`parazun request <PATH>` reaches any path of the API, including the paths
that have no command yet.

```
parazun request "/product" --param asin=B00FLYWNYQ --param region=US
parazun request "/search" --param keywords=coffee
```

**The path must start with a slash.** The client joins the base address and
the path with no separator, so a path without a slash asks for a host that
does not exist.

`--param` takes `name=value`, and it can be given more than once. `--method`
is `GET` when it is not given. `--data` takes a body as JSON.

In this checkout a command string that carries a leading slash is refused
by a sandbox, so run the escape hatch from a script
instead of from the shell.
