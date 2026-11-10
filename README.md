# ImpactU MCP server

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude (and other MCP clients) query
[ImpactU](https://impactu.colav.co), Colombia's open research information system built by Colav at the Universidad
de Antioquia: about 2.9 million research products, 1.5 million people, 55,000 institutions and 7,600 research groups.

Once deployed at `https://mcp.impactu.colav.co/mcp`, anyone can add it to Claude as a **custom connector**, including
users on the Free plan (which allows one custom connector). It needs no account or key: ImpactU's query API is public.

## Use it

- **Claude (web, desktop, mobile; any plan, Free included):** Settings → Connectors → Add custom connector, URL
  `https://impactu-mcp.onrender.com/mcp` (temporary server; it must end in `/mcp`), no OAuth.
- **Claude Code plugin** (the connector plus the `impactu-mcp-connector` skill to deploy, test and maintain it):

  ```bash
  claude plugin marketplace add colav-playground/impactu-mcp
  claude plugin install impactu-mcp@colav
  ```

- **Skill only, in Claude (web/desktop):** download
  [`dist/impactu-mcp-connector.zip`](https://github.com/colav-playground/impactu-mcp/raw/main/dist/impactu-mcp-connector.zip)
  and upload it in Settings → Capabilities → Skills. Rebuild it after editing the skill:
  `cd skills && zip -qr -X ../dist/impactu-mcp-connector.zip impactu-mcp-connector`.

## Tools

All tools are read-only.

| Tool | What it does |
| --- | --- |
| `autocomplete` | Find ids by name: person, institution, faculty, department, group or journal |
| `search_products` | Search all products by keywords and filters (years, type, open access, countries, number of authors, group category) |
| `list_products` | Products of one person, institution, faculty, department, group or journal |
| `get_product` | One product: types per source, journal and its Scimago quartile that year, citations, open access, abstract, ids, groups, authors |
| `find_product_by_doi` | Products with a DOI |
| `get_product_authors` | Full author list in byline order, paged, optionally only Colombian authors |
| `search_people`, `get_person` | Researchers: affiliations over time, products, citations, h-index, Minciencias category, ORCID/Scholar/OpenAlex ids |
| `search_affiliations`, `get_affiliation` | Institutions, faculties, departments and groups, optionally with their internal units |
| `search_sources`, `get_source` | Journals: publisher, ISSN, Scimago quartile, Publindex |
| `get_indicator` | ImpactU's ready-made indicators (citations per year, quartiles, co-authorship by country, h-index by group, APC, ...) |
| `get_filter_options` | Valid filter values with counts |
| `get_database_info` | Totals and date of the last data update |

ImpactU records can weigh several MB (one physics paper lists thousands of authors), so the server never passes them
through: it asks the API for summaries, keeps the useful fields, picks each value by data source, rebuilds abstracts
from their inverted index, pages lists (at most 25 per page) and caps every answer well below 60 kB. National ID
numbers are dropped even if the API ever returns them.

## Run it locally

```bash
git clone https://github.com/colav-playground/impactu-mcp.git && cd impactu-mcp
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/impactu-mcp                     # http://127.0.0.1:8000/mcp
```

Try it with the MCP Inspector (`npx @modelcontextprotocol/inspector`, transport "Streamable HTTP",
URL `http://127.0.0.1:8000/mcp`), or with Claude Code:

```bash
claude mcp add --transport http impactu http://127.0.0.1:8000/mcp
```

## Tests

```bash
.venv/bin/pytest -m "not live"                         # offline tests of the record reducers
.venv/bin/pytest -m live                               # starts the server and calls every tool on the real API (~30 s)
IMPACTU_MCP_URL=https://mcp.impactu.colav.co/mcp .venv/bin/pytest -m live   # test a deployed server
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `IMPACTU_API_BASE` | `https://api.dev.impactu.colav.co` | ImpactU API the tools call. The documented routes are on dev today; switch to production once it serves them. |
| `MCP_PUBLIC_HOSTS` | (empty) | Public host names, e.g. `mcp.impactu.colav.co`. Other `Host` headers get 421 (DNS-rebinding protection). |
| `HOST`, `PORT`, `WORKERS` | `127.0.0.1`, `8000`, `1` | Where uvicorn listens and how many processes it runs |
| `IMPACTU_TIMEOUT` | `90` | Seconds per API request |
| `IMPACTU_CACHE_TTL`, `IMPACTU_CACHE_SIZE` | `600`, `2000` | In-memory cache of API answers, per worker |
| `IMPACTU_MAX_CONCURRENCY` | `8` | Simultaneous API requests per worker |

The server is stateless (`stateless_http`, JSON responses), so several workers or replicas can run behind a load balancer
without sticky sessions.

## Deploying

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions to publish it at `https://mcp.impactu.colav.co`.

For a free test deployment without a server, use Render's free plan (the instance sleeps when idle):

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/colav-playground/impactu-mcp)
