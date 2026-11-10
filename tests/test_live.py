"""End-to-end tests: start the server over HTTP and call every tool against the real ImpactU API.

Run: pytest -m live          (needs internet; about 1-2 minutes; gentle, one call at a time)
Set IMPACTU_MCP_URL to test a deployed server instead, e.g. https://mcp.impactu.colav.co/mcp
"""
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import Client

pytestmark = pytest.mark.live

UDEA, GFIF, PERSON = "03bp5hc83", "COL0008423", "0000177733"
MAX_BYTES = 60_000  # every answer must stay small enough for a model's context


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def url():
    if os.environ.get("IMPACTU_MCP_URL"):
        yield os.environ["IMPACTU_MCP_URL"]
        return
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "impactu_mcp.server"], env={**os.environ, "PORT": str(port)})
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(base + "/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield base + "/mcp"
    proc.terminate()
    proc.wait(10)


async def call(url, tool, **args):
    async with Client(url, read_timeout_seconds=180) as c:
        r = await c.call_tool(tool, args)
    text = r.content[0].text if r.content else ""
    assert len(text.encode()) < MAX_BYTES, f"{tool} answer is {len(text)} bytes"
    if r.is_error:
        return {"_error": text}
    return r.structured_content or json.loads(text)


async def test_tools_listed(url):
    async with Client(url) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert c.instructions and "ImpactU" in c.instructions
    assert {"search_products", "get_product", "autocomplete", "get_indicator", "get_database_info"} <= names


async def test_database_info(url):
    d = await call(url, "get_database_info")
    assert d["total_products"] > 1_000_000 and d["db_update_date"]


async def test_autocomplete_person_and_group(url):
    p = await call(url, "autocomplete", kind="person", text="diego restrepo")
    assert any(m["id"] == PERSON for m in p["matches"])
    g = await call(url, "autocomplete", kind="group", text="fenomenologia")
    assert any(m["id"] == GFIF for m in g["matches"])


async def test_search_products(url):
    d = await call(url, "search_products", query="dark matter", years="2020,2025", page_size=5)
    assert d["total"] > 0 and len(d["products"]) == 5
    assert all(p.get("title") and p.get("id") for p in d["products"])


async def test_list_products_and_detail(url):
    d = await call(url, "list_products", entity_type="group", entity_id=GFIF, authors_count="-100", page_size=3)
    assert d["total"] > 100 and d["products"]
    w = await call(url, "get_product", product_id=d["products"][0]["id"])
    assert w["title"] and w["year"]


async def test_product_by_doi(url):
    d = await call(url, "find_product_by_doi", doi="10.17533/udea.iatreia.3440")
    assert d["found"] == 1
    none = await call(url, "find_product_by_doi", doi="10.0000/does-not-exist")
    assert none["found"] == 0


async def test_product_authors_paging(url):
    big = await call(url, "list_products", entity_type="group", entity_id=GFIF, authors_count="1000-", page_size=1)
    pid = big["products"][0]["id"]
    a = await call(url, "get_product_authors", product_id=pid, offset=0, limit=20)
    assert a["total"] >= 1000 and a["returned"] == 20
    co = await call(url, "get_product_authors", product_id=pid, only_colombian=True, limit=200)
    assert 0 < co["total"] < a["total"]


async def test_people_and_affiliations(url):
    p = await call(url, "get_person", person_id=PERSON)
    assert p["name"] and p["affiliations"]
    s = await call(url, "search_people", query="restrepo quintero", page_size=3)
    assert s["people"]
    i = await call(url, "get_affiliation", affiliation_type="institution", affiliation_id=UDEA, include_units=True, max_units=5)
    assert i["name"] == "Universidad de Antioquia" and i.get("faculties")
    g = await call(url, "search_affiliations", affiliation_type="group", query="fenomenologia", page_size=3)
    assert g["affiliations"]


async def test_sources(url):
    s = await call(url, "search_sources", query="physical review d", page_size=3)
    assert s["sources"]
    d = await call(url, "get_source", source_id=s["sources"][0]["id"])
    assert d["name"]


async def test_indicators(url):
    q = await call(url, "get_indicator", entity_type="institution", entity_id=UDEA, indicator="articles_by_scimago_quartile")
    assert q["result"]
    c = await call(url, "get_indicator", entity_type="person", entity_id=PERSON, indicator="annual_citation_count")
    assert c["result"]
    bad = await call(url, "get_indicator", entity_type="person", entity_id=PERSON, indicator="citations_by_faculty")
    assert "_error" in bad


async def test_filter_options(url):
    f = await call(url, "get_filter_options", scope="group", entity_id=GFIF)
    assert f.get("product_types")


async def test_errors_are_messages(url):
    d = await call(url, "get_product", product_id="not-an-id")
    assert "_error" in d
