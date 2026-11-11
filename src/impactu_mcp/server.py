"""ImpactU MCP server: read-only tools over the public ImpactU API (Colav, Universidad de Antioquia).

Run locally:   impactu-mcp            (streamable HTTP on http://127.0.0.1:8000/mcp)
Environment:   see README.md (IMPACTU_API_BASE, MCP_PUBLIC_HOSTS, HOST, PORT, ...)
"""
import contextlib
import json
import os
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import compact as C
from .api import API_BASE, ApiError, ImpactUClient, seg

__version__ = "0.1.0"

AFF_TYPES = ("institution", "faculty", "department", "group")
EntityType = Literal["person", "institution", "faculty", "department", "group", "source"]
Sort = Literal["citations_desc", "citations_asc", "year_desc", "year_asc", "alphabetical_asc", "alphabetical_desc"]

INDICATORS = {
    "affiliation": [
        "faculties_by_product_type", "departments_by_product_type", "research_groups_by_product_type",
        "citations_by_faculty", "citations_by_department", "citations_by_research_group",
        "apc_expenses_by_faculty", "apc_expenses_by_department", "apc_expenses_by_group",
        "h_index_by_faculty", "h_index_by_department", "h_index_by_research_group",
        "annual_evolution_by_impactu_classification", "annual_citation_count", "annual_articles_open_access",
        "annual_articles_by_top_publishers", "annual_apc_expenses", "most_used_title_words", "articles_by_publisher",
        "products_by_subject", "articles_by_access_route", "active_authors_by_sex", "active_authors_by_age_range",
        "articles_by_scienti_category", "articles_by_scimago_quartile", "articles_by_publishing_institution",
        "products_by_database", "coauthorship_by_country_map", "coauthorship_by_colombian_department_map",
        "institutional_coauthorship_network",
    ],
    "person": [
        "annual_evolution_by_impactu_classification", "annual_citation_count", "annual_apc_expenses",
        "annual_articles_open_access", "annual_articles_by_top_publishers", "most_used_title_words",
        "articles_by_publisher", "products_by_subject", "products_by_database", "articles_by_access_route",
        "articles_by_scienti_category", "articles_by_scimago_quartile", "articles_by_publishing_institution",
        "coauthorship_by_country_map", "coauthorship_by_colombian_department_map", "author_coauthorship_network",
    ],
    "source": ["annual_scimago_quartile"],
}

INSTRUCTIONS = """\
ImpactU (https://impactu.colav.co) is Colombia's open research information system, built by Colav at the
Universidad de Antioquia. It merges OpenAlex, Minciencias' Scienti/CvLAC/GrupLAC, Google Scholar, Scimago,
Publindex, DOAJ, institutional repositories and HR files: about 2.9 million research products, 1.5 million
people, 55,000 institutions and 7,600 research groups.

How to use these tools:
- Resolve names to ids first with `autocomplete` (people, institutions, faculties, departments, groups,
  journals). Ids: person `0000177733` (Scienti/CvLAC code) or an OpenAlex author id; institution = ROR id
  (`03bp5hc83` is Universidad de Antioquia); faculty `03bp5hc83_20`; department `03bp5hc83_2_21620003_3154`;
  group `COL0008423`; journal = 24-hex id; product = the id the search and list tools return (usually the DOI,
  e.g. `10.1103/physrevd.103.095032`; pass it as is, with its slashes).
- For counts and distributions use `get_indicator` (computed by the API) or the `total` of a list with
  page_size=1, instead of paging through products.
- Lists are paged (page_size up to 25). Products show the first authors only; use `get_product_authors`
  for the full author list (some physics papers have thousands of authors).
- Many values come per data source (citations: openalex, scholar). Say which source a number comes from.
  Empty fields mean "not recorded in ImpactU", not "does not exist".
- Valid filter values (product types, countries, rankings) come from `get_filter_options`.
"""

client = ImpactUClient()


@contextlib.asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await client.close()


mcp = MCPServer(
    name="ImpactU",
    title="ImpactU – Colombian research data",
    description="Search Colombian research products, researchers, institutions, groups and journals in ImpactU.",
    instructions=INSTRUCTIONS,
    website_url="https://impactu.colav.co",
    version=__version__,
    lifespan=lifespan,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

PageSize = Annotated[int, Field(ge=1, le=25, description="Results per page (1-25).")]
Page = Annotated[int, Field(ge=1, le=10000, description="Page number, from 1.")]
Years = Annotated[str | None, Field(description="Year range 'MIN,MAX', e.g. '2020,2025'; one year: '2024,2024'.")]
ProductTypes = Annotated[str | None, Field(description="Comma-separated product types as given by get_filter_options, e.g. 'impactu_Artículo de revista'.")]
OpenAccess = Annotated[str | None, Field(description="Open-access status, comma-separated: gold, diamond, green, hybrid, bronze, closed.")]
Countries = Annotated[str | None, Field(description="Co-author country codes, comma-separated, e.g. 'CO,US'.")]
AuthorsCount = Annotated[str | None, Field(description="Number of authors: '5' exact, '-100' up to 100, '101-' 101 or more, '5-8' range.")]
GroupsRanking = Annotated[str | None, Field(description="Minciencias group category, comma-separated: A1, A, B, C, Reconocido.")]


async def call(path, params=None):
    try:
        return await client.get(path, params)
    except ApiError as e:
        raise ToolError(str(e))


def product_filters(years, product_types, open_access, countries, authors_count, groups_ranking=None):
    return {"years": years, "product_types": product_types, "status": open_access, "countries": countries,
            "authors_count": authors_count, "groups_ranking": groups_ranking}


def products_path(entity_type, entity_id):
    if entity_type == "person":
        return f"/person/{seg(entity_id)}/research/products"
    if entity_type == "source":
        return f"/source/{seg(entity_id)}/products"
    return f"/affiliation/{entity_type}/{seg(entity_id)}/research/products"


def product_page(d, page, size, max_authors):
    return {**C.page_meta(d.get("meta"), page, size),
            "products": [C.product(w, max_authors=max_authors) for w in d.get("data") or [] if isinstance(w, dict)]}


@mcp.tool(annotations=READ_ONLY)
async def search_products(
    query: Annotated[str | None, Field(description="Words to search in titles and content. Leave empty to list with filters only.")] = None,
    years: Years = None,
    product_types: ProductTypes = None,
    open_access: OpenAccess = None,
    countries: Countries = None,
    authors_count: AuthorsCount = None,
    groups_ranking: GroupsRanking = None,
    sort: Sort = "citations_desc",
    page: Page = 1,
    page_size: PageSize = 10,
    max_authors: Annotated[int, Field(ge=0, le=20, description="Authors shown per product.")] = 3,
) -> dict:
    """Search all research products in ImpactU (articles, books, chapters, theses, software, ...) by keywords and filters.
    Returns the total number of matches and one page of compact records."""
    params = {"keywords": query, "max": page_size, "page": page, "sort": sort, "view": "summary",
              **product_filters(years, product_types, open_access, countries, authors_count, groups_ranking)}
    return product_page(await call("/search/works", params), page, page_size, max_authors)


@mcp.tool(annotations=READ_ONLY)
async def list_products(
    entity_type: Annotated[EntityType, Field(description="Whose products: person, institution, faculty, department, group or source (journal).")],
    entity_id: Annotated[str, Field(description="Id of that person, affiliation or journal (use autocomplete to find it).")],
    years: Years = None,
    product_types: ProductTypes = None,
    open_access: OpenAccess = None,
    countries: Countries = None,
    authors_count: AuthorsCount = None,
    sort: Sort = "citations_desc",
    page: Page = 1,
    page_size: PageSize = 10,
    max_authors: Annotated[int, Field(ge=0, le=20, description="Authors shown per product.")] = 3,
) -> dict:
    """List the research products of one researcher, institution, faculty, department, research group or journal,
    with filters. `total` gives the number of matching products."""
    params = {"max": page_size, "page": page, "sort": sort, "view": "summary",
              **product_filters(years, product_types, open_access, countries, authors_count)}
    return product_page(await call(products_path(entity_type, entity_id), params), page, page_size, max_authors)


@mcp.tool(annotations=READ_ONLY)
async def get_product(
    product_id: Annotated[str, Field(description="ImpactU product id, as returned by the search and list tools (usually the DOI, e.g. 10.1103/physrevd.103.095032).")],
    max_authors: Annotated[int, Field(ge=0, le=100, description="Authors to include, in byline order.")] = 20,
) -> dict:
    """Get one research product: title, year, type per source, journal and its Scimago quartile that year,
    citations, open access, abstract, external ids (DOI, OpenAlex, Scienti), groups and first authors."""
    d = await call(f"/work/{seg(product_id, keep_slash=True)}", {"view": "full" if max_authors > 10 else "summary"})
    return C.product_detail(d.get("data") or {}, max_authors=max_authors)


@mcp.tool(annotations=READ_ONLY)
async def find_product_by_doi(
    doi: Annotated[str, Field(description="DOI, with or without https://doi.org/, e.g. 10.1103/PhysRevD.103.095032.")],
) -> dict:
    """Find the ImpactU product(s) with a DOI."""
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    try:
        d = await client.get("/work", {"doi": "https://doi.org/" + doi, "view": "summary", "max": 5, "page": 1})
    except ApiError as e:
        if "Not found" in str(e):
            return {"doi": doi, "found": 0, "products": []}
        raise ToolError(str(e))
    items = d.get("data") or []
    return {"doi": doi, "found": len(items), "products": [C.product(w, max_authors=5) for w in items]}


@mcp.tool(annotations=READ_ONLY)
async def get_product_authors(
    product_id: Annotated[str, Field(description="ImpactU product id, as returned by the search and list tools (usually the DOI).")],
    offset: Annotated[int, Field(ge=0, description="First author to return (0 = first in the byline).")] = 0,
    limit: Annotated[int, Field(ge=1, le=200, description="Number of authors to return.")] = 50,
    only_colombian: Annotated[bool, Field(description="Keep only authors with an affiliation in Colombia or a Scienti id.")] = False,
) -> dict:
    """Full author list of a product in byline order, with ids and affiliations (products in lists show only the first authors)."""
    d = await call(f"/work/{seg(product_id, keep_slash=True)}/authors", {"view": "full"})
    authors = [a for a in d.get("data") or [] if isinstance(a, dict)]
    if only_colombian:
        def colombian(a):
            if any(x.get("source") in ("scienti", "minciencias") for x in a.get("external_ids") or [] if isinstance(x, dict)):
                return True
            return "CO" in (a.get("countries") or [])
        authors = [a for a in authors if colombian(a)]
    part = authors[offset: offset + limit]
    return {"total": len(authors), "offset": offset, "returned": len(part),
            "authors": [{"position": offset + i + 1, **C.author(a, max_affiliations=4)} for i, a in enumerate(part)]}


@mcp.tool(annotations=READ_ONLY)
async def autocomplete(
    kind: Annotated[Literal["person", "institution", "faculty", "department", "group", "source"], Field(description="What to look up.")],
    text: Annotated[str, Field(min_length=2, description="Part of the name, e.g. 'diego restrepo', 'antioquia', 'fenomenologia'.")],
) -> dict:
    """Find ids by name: people, institutions, faculties, departments, research groups or journals (sources).
    Use this before the other tools to get the right id."""
    if kind == "person":
        path = f"/completer/person/{seg(text)}"
    elif kind == "source":
        path = f"/completer/sources/{seg(text)}"
    else:
        path = f"/completer/affiliations/{kind}/{seg(text)}"
    d = await call(path)
    out = []
    for x in d if isinstance(d, list) else d.get("data") or []:
        s = x.get("_source") or {}
        item = {"id": x.get("_id"), "name": x.get("full_name") or x.get("name") or s.get("full_name")}
        if s.get("products_count") is not None:
            item["products_count"] = s.get("products_count")
        if s.get("affiliations"):
            item["affiliations"] = [a.get("name") for a in s["affiliations"][:3] if isinstance(a, dict)]
        if s.get("relations"):
            item["part_of"] = s["relations"][:3]
        if s.get("publisher"):
            item["publisher"] = s["publisher"]
        out.append(item)
    return {"kind": kind, "matches": out}


@mcp.tool(annotations=READ_ONLY)
async def search_people(
    query: Annotated[str, Field(description="Name or keywords.")],
    page: Page = 1,
    page_size: PageSize = 10,
    sort: Annotated[str, Field(description="citations_desc (default), products_desc, alphabetical_asc, ...")] = "citations_desc",
) -> dict:
    """Search researchers by name or keywords, with their affiliations, h-index and Minciencias category."""
    d = await call("/search/person", {"keywords": query, "max": page_size, "page": page, "sort": sort, "view": "summary"})
    return {**C.page_meta(d.get("meta"), page, page_size), "people": [C.person(p) for p in d.get("data") or []]}


@mcp.tool(annotations=READ_ONLY)
async def get_person(person_id: Annotated[str, Field(description="Person id, e.g. '0000177733'.")]) -> dict:
    """Profile of a researcher: affiliations over time (institution, faculty, department, group), products,
    citations, h-index, latest Minciencias category and external ids (ORCID, Scholar, OpenAlex, Scienti)."""
    d = await call(f"/person/{seg(person_id)}", {"view": "full"})
    return C.person(d.get("data") or {})


@mcp.tool(annotations=READ_ONLY)
async def search_affiliations(
    affiliation_type: Annotated[Literal["institution", "faculty", "department", "group"], Field(description="Kind of affiliation.")],
    query: Annotated[str | None, Field(description="Name or keywords.")] = None,
    groups_ranking: GroupsRanking = None,
    page: Page = 1,
    page_size: PageSize = 10,
    sort: Annotated[str, Field(description="citations_desc (default), products_desc, alphabetical_asc, ...")] = "citations_desc",
) -> dict:
    """Search institutions, faculties, departments or research groups, with products, citations, h-index and category."""
    d = await call(f"/search/affiliations/{affiliation_type}",
                   {"keywords": query, "groups_ranking": groups_ranking, "max": page_size, "page": page, "sort": sort, "view": "summary"})
    return {**C.page_meta(d.get("meta"), page, page_size), "affiliations": [C.affiliation(a) for a in d.get("data") or []]}


@mcp.tool(annotations=READ_ONLY)
async def get_affiliation(
    affiliation_type: Annotated[Literal["institution", "faculty", "department", "group"], Field(description="Kind of affiliation.")],
    affiliation_id: Annotated[str, Field(description="ROR id for institutions (03bp5hc83), COL code for groups, or the faculty/department id.")],
    include_units: Annotated[bool, Field(description="Also list its faculties, departments and groups (and authors for groups).")] = False,
    max_units: Annotated[int, Field(ge=1, le=500, description="Maximum units listed per kind.")] = 50,
) -> dict:
    """Profile of an institution, faculty, department or research group; optionally its internal units."""
    d = await call(f"/affiliation/{affiliation_type}/{seg(affiliation_id)}", {"view": "full"})
    out = C.affiliation(d.get("data") or {})
    if include_units:
        rel = await call(f"/affiliation/{affiliation_type}/{seg(affiliation_id)}/affiliations")
        for k, v in (rel or {}).items():
            if isinstance(v, list) and v:
                out[f"{k}_count"] = len(v)
                out[k] = [{"id": x.get("id"), "name": x.get("name") or x.get("full_name")} for x in v[:max_units] if isinstance(x, dict)]
    return out


@mcp.tool(annotations=READ_ONLY)
async def search_sources(
    query: Annotated[str, Field(description="Journal or source name, ISSN or keywords.")],
    page: Page = 1,
    page_size: PageSize = 10,
) -> dict:
    """Search journals and other publication sources, with publisher, ISSN, Scimago quartile and Publindex category."""
    d = await call("/search/sources", {"keywords": query, "max": page_size, "page": page, "view": "summary"})
    return {**C.page_meta(d.get("meta"), page, page_size), "sources": [C.source(s) for s in d.get("data") or []]}


@mcp.tool(annotations=READ_ONLY)
async def get_source(source_id: Annotated[str, Field(description="ImpactU source (journal) id, as returned by search_sources or autocomplete.")]) -> dict:
    """Profile of a journal or publication source."""
    d = await call(f"/source/{seg(source_id)}", {"view": "full"})
    return C.source(d.get("data") or {})


def trim(value, max_items):
    """Cap every list in a nested structure at max_items, noting how many were left out."""
    if isinstance(value, list):
        items = [trim(v, max_items) for v in value[:max_items]]
        if len(value) > max_items:
            items.append({"_truncated": f"{len(value) - max_items} more items not shown"})
        return items
    if isinstance(value, dict):
        return {k: trim(v, max_items) for k, v in value.items()}
    return value


@mcp.tool(annotations=READ_ONLY)
async def get_indicator(
    entity_type: Annotated[EntityType, Field(description="person, institution, faculty, department, group or source.")],
    entity_id: Annotated[str, Field(description="Id of the person, affiliation or journal.")],
    indicator: Annotated[str, Field(description=(
        "Indicator name. Affiliations: " + ", ".join(INDICATORS["affiliation"]) + ". Persons: "
        + ", ".join(INDICATORS["person"]) + ". Sources: annual_scimago_quartile. Some apply only to some "
        "affiliation levels (e.g. citations_by_faculty only to institutions)."))],
    years: Years = None,
    product_types: ProductTypes = None,
    open_access: OpenAccess = None,
    countries: Countries = None,
    authors_count: AuthorsCount = None,
    max_items: Annotated[int, Field(ge=5, le=300, description="Maximum entries kept in each list of the result.")] = 60,
) -> dict:
    """Ready-made indicators computed by ImpactU over all matching products (no paging): citations per year,
    open-access articles per year, Scimago quartiles, products by type or subject, co-authorship by country,
    h-index or citations by faculty/department/group, APC expenses, authors by sex and age, and more."""
    family = "person" if entity_type == "person" else "source" if entity_type == "source" else "affiliation"
    if indicator not in INDICATORS[family]:
        raise ToolError(f"Unknown indicator for {entity_type}. Valid: {', '.join(INDICATORS[family])}")
    params = {"plot": indicator, **product_filters(years, product_types, open_access, countries, authors_count)}
    d = await call(products_path(entity_type, entity_id), params)
    return {"entity_type": entity_type, "entity_id": entity_id, "indicator": indicator, "result": trim(d, max_items)}


@mcp.tool(annotations=READ_ONLY)
async def get_filter_options(
    scope: Annotated[Literal["search", "person", "institution", "faculty", "department", "group", "source"],
                     Field(description="'search' for search_products, otherwise the entity whose products you list.")] = "search",
    entity_id: Annotated[str | None, Field(description="Entity id when scope is not 'search'.")] = None,
    query: Annotated[str | None, Field(description="Search words, when scope is 'search'.")] = None,
    max_options: Annotated[int, Field(ge=5, le=200, description="Maximum options listed per filter.")] = 40,
) -> dict:
    """Valid values (with counts) for the product filters: product types, open-access status, countries,
    author and group rankings, institution types, year and author-count ranges."""
    if scope == "search":
        path, params = "/search/works/filters", {"keywords": query}
    else:
        if not entity_id:
            raise ToolError("entity_id is required for this scope.")
        path, params = products_path(scope, entity_id) + "/filters", {}
    d = await call(path, params)
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, list):
            opts = [{kk: o.get(kk) for kk in ("value", "label", "count") if o.get(kk) is not None} for o in v if isinstance(o, dict)]
            out[k] = opts[:max_options] + ([{"_truncated": f"{len(opts) - max_options} more"}] if len(opts) > max_options else [])
        else:
            out[k] = v
    return out


@mcp.tool(annotations=READ_ONLY)
async def get_database_info() -> dict:
    """Totals in ImpactU (products, people, institutions, groups, journals, patents, projects, open access)
    and the date of the last data update."""
    d = await call("/info")
    out = dict(d)
    if "db_update" in out:
        out["db_update_date"] = C.date(out["db_update"])
    out["api_base"] = API_BASE
    return out


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": __version__, "api_base": API_BASE})


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def home(request: Request) -> JSONResponse:
    return JSONResponse({
        "name": "ImpactU MCP server", "version": __version__, "mcp_endpoint": "/mcp",
        "how_to_use": "In Claude: Settings > Connectors > Add custom connector, URL https://mcp.impactu.colav.co/mcp",
        "data": "https://impactu.colav.co", "docs": "https://help.impactu.colav.co",
    })


def build_app():
    hosts = [h.strip() for h in os.environ.get("MCP_PUBLIC_HOSTS", "").split(",") if h.strip()]
    # hosting platforms that announce the public host name themselves (Render, Hugging Face Spaces)
    hosts += [os.environ[v] for v in ("RENDER_EXTERNAL_HOSTNAME", "SPACE_HOST") if os.environ.get(v)]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *hosts, *[f"{h}:*" for h in hosts]],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "https://claude.ai", "https://claude.com",
                         *[f"https://{h}" for h in hosts]],
    )
    inner = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security,
                                    host=os.environ.get("HOST", "127.0.0.1"))
    return probe_friendly(inner)


def probe_friendly(inner):
    """Answer HEAD, OPTIONS and DELETE on /mcp with 200/204 instead of 405.

    Claude's connector check (on Free accounts) probes the URL before connecting and reads a 405 as "this server
    wants sign-in". The server is stateless, so there is no session for a DELETE to end. The bare host also works as
    the endpoint (a connector URL entered without /mcp): everything but GET and HEAD on / goes to /mcp.
    """
    allow = [(b"allow", b"GET, POST, DELETE, HEAD, OPTIONS")]

    async def app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/" and scope["method"] not in ("GET", "HEAD"):
            scope = {**scope, "path": "/mcp", "raw_path": b"/mcp"}
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp" and scope["method"] in ("HEAD", "OPTIONS", "DELETE"):
            if scope["method"] == "HEAD":
                status, headers = 200, [(b"content-type", b"application/json")]
            elif scope["method"] == "DELETE":
                status, headers = 204, []
            else:
                origin = dict(scope["headers"]).get(b"origin", b"*")
                status, headers = 204, [(b"access-control-allow-origin", origin),
                                        (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
                                        (b"access-control-allow-headers", b"*"),
                                        (b"access-control-expose-headers", b"mcp-session-id, mcp-protocol-version"),
                                        (b"access-control-max-age", b"86400"), (b"vary", b"origin")]
            await send({"type": "http.response.start", "status": status, "headers": allow + headers})
            await send({"type": "http.response.body", "body": b""})
            return
        await inner(scope, receive, send)

    return app


app = build_app()


def main():
    import uvicorn

    uvicorn.run("impactu_mcp.server:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")),
                workers=int(os.environ.get("WORKERS", "1")), proxy_headers=True, forwarded_allow_ips="*",
                log_level=os.environ.get("LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
