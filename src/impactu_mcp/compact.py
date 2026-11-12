"""Turn ImpactU records into small dicts a model can read.

ImpactU records keep one variant per data source (titles, citations, types, ids), and a single
product can weigh several MB. These helpers keep the useful fields and pick each value by source.
"""
import datetime as dt

COT = dt.timezone(dt.timedelta(hours=-5))  # ImpactU dates are Unix seconds at Colombian midnight
TYPE_SOURCES = ("impactu", "scienti", "minciencias", "openalex")
AFF_LEVELS = {"group": "group", "faculty": "faculty", "department": "department"}
# national id numbers are never passed on, even if the API ever returns them
# (Kahi names them "Cédula de Ciudadanía", "Cédula de Extranjería", "Pasaporte", "Passport", "Tarjeta de Identidad").
PRIVATE_ID_SOURCES = {"cc", "ce", "ti", "cedula", "cédula", "passport", "pasaporte", "document", "doc", "nit", "dni",
                      "cédula de ciudadanía", "cédula de extranjería", "tarjeta de identidad", "documento extranjero"}


def ids(items):
    """{source: id} from an external_ids list, without national id numbers."""
    return {x["source"]: x.get("id") for x in items or []
            if isinstance(x, dict) and x.get("source") and x["source"].lower() not in PRIVATE_ID_SOURCES}


def date(ts):
    if not isinstance(ts, (int, float)) or ts < 0:
        return None
    return dt.datetime.fromtimestamp(ts, COT).date().isoformat()


def by_source(items, key, sources):
    """Value of `key` in the first item whose `source` is in `sources`, in that order."""
    items = [x for x in items or [] if isinstance(x, dict)]
    for s in sources:
        for x in items:
            if x.get("source") == s and x.get(key) not in (None, ""):
                return x[key]
    return None


def counts(items):
    """{source: count} from a citations_count list."""
    return {x["source"]: x.get("count") for x in items or [] if isinstance(x, dict) and x.get("source")}


def ext_id(items, source):
    for x in items or []:
        if isinstance(x, dict) and x.get("source") == source and x.get("id"):
            return x["id"]
    return None


def abstract_text(w, limit=3000):
    """The abstract as plain text, rebuilding OpenAlex-style inverted indexes."""
    text = w.get("abstract") if isinstance(w.get("abstract"), str) else None
    if not text:
        for pref in ("openalex", "dspace", "scholar", "europepmc", None):
            for a in w.get("abstracts") or []:
                if not isinstance(a, dict) or (pref and a.get("source") != pref):
                    continue
                body = a.get("abstract")
                if isinstance(body, str) and body.strip():
                    text = body
                elif isinstance(body, dict) and body:
                    pos = sorted((p, word) for word, ps in body.items() for p in (ps or []))
                    text = " ".join(word for _, word in pos)
                if text:
                    break
            if text:
                break
    if text and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


def journal_rank(src, year):
    """Scimago quartile and SJR of the journal in the publication year, if recorded."""
    out = {}
    for r in (src or {}).get("ranking") or []:
        if not isinstance(r, dict) or not isinstance(year, int):
            continue
        start, end = date(r.get("from_date")), date(r.get("to_date"))
        if not (start and end and start[:4] <= str(year) <= end[:4]):
            continue
        if r.get("source") == "scimago Best Quartile":
            out["scimago_quartile"] = r.get("rank")
        elif r.get("source") == "scimago":
            out["scimago_sjr"] = r.get("rank")
    return out


def author(a, max_affiliations=3):
    affs = []
    for f in (a.get("affiliations") or [])[:max_affiliations]:
        if isinstance(f, dict) and f.get("name"):
            affs.append({"id": f.get("id"), "name": f.get("name")})
    return {"id": a.get("id"), "name": a.get("full_name"), "affiliations": affs}


def product(w, max_authors=5, with_abstract=False):
    src = w.get("source") or {}
    year = w.get("year_published")
    out = {
        "id": w.get("id"),
        "title": w.get("title") or by_source(w.get("titles"), "title", ("openalex", "scienti", "minciencias", "dspace")),
        "year": year,
        "type": by_source(w.get("product_types"), "name", TYPE_SOURCES),
        "doi": w.get("doi") or ext_id(w.get("external_ids"), "doi"),
        "journal": src.get("name") or by_source(src.get("names"), "name", ("openalex", "scimago", "publindex", "doaj")),
        "citations": counts(w.get("citations_count")),
        "open_access": (w.get("open_access") or {}).get("open_access_status"),
        "authors_count": w.get("authors_count"),
        "authors": [author(a) for a in (w.get("authors") or [])[:max_authors] if isinstance(a, dict)],
    }
    out.update(journal_rank(src, year))
    groups = [{"id": g.get("id"), "name": g.get("name")} for g in w.get("groups") or [] if isinstance(g, dict)]
    if groups:
        out["groups"] = groups[:5]
    if with_abstract:
        out["abstract"] = abstract_text(w)
    return {k: v for k, v in out.items() if v not in (None, [], {})}


def product_detail(w, max_authors=20):
    out = product(w, max_authors=max_authors, with_abstract=True)
    bib = w.get("bibliographic_info") or {}
    out.update({
        "date_published": date(w.get("date_published")),
        "language": w.get("language"),
        "volume": bib.get("volume"), "issue": bib.get("issue"),
        "pages": "-".join(str(p) for p in (bib.get("start_page"), bib.get("end_page")) if p) or None,
        "open_access_url": (w.get("open_access") or {}).get("url"),
        "topic": ((w.get("primary_topic") or {}).get("display_name")),
        "types_by_source": {t["source"]: t.get("name") for t in w.get("product_types") or [] if isinstance(t, dict) and t.get("source")},
        "external_ids": ids(w.get("external_ids")),
        "minciencias_classification": [r.get("rank") for r in w.get("ranking") or [] if isinstance(r, dict) and r.get("source") == "minciencias"],
        "citations_by_year": {c.get("year"): c.get("cited_by_count") for c in w.get("citations_by_year") or [] if isinstance(c, dict)},
    })
    return {k: v for k, v in out.items() if v not in (None, [], {}, "")}


def latest_rank(items, sources=("minciencias", "scienti")):
    best = None
    for r in items or []:
        if isinstance(r, dict) and r.get("source") in sources and r.get("rank"):
            when = r.get("date") or r.get("from_date") or 0
            if best is None or when >= best[0]:
                best = (when, r["rank"])
    return best[1] if best else None


def person(p):
    affs = []
    for f in p.get("affiliations") or []:
        if not isinstance(f, dict) or not f.get("name"):
            continue
        affs.append({k: v for k, v in {
            "id": f.get("id"), "name": f.get("name"),
            "level": next((AFF_LEVELS[t.get("type")] for t in f.get("types") or [] if isinstance(t, dict) and t.get("type") in AFF_LEVELS), "institution"),
            "start": date(f.get("start_date")), "end": "current" if f.get("end_date") == -1 else date(f.get("end_date")),
        }.items() if v})
    out = {
        "id": p.get("id"), "name": p.get("full_name"),
        "products_count": p.get("products_count"), "citations": counts(p.get("citations_count")),
        "h_index": p.get("h_index"), "minciencias_category": latest_rank(p.get("ranking")),
        "affiliations": affs[:10],
        "external_ids": ids(p.get("external_ids")),
    }
    return {k: v for k, v in out.items() if v not in (None, [], {})}


def affiliation(a):
    names = a.get("names") or []
    out = {
        "id": a.get("id") or a.get("_id"),
        "name": a.get("name") or by_source(names, "name", ("ror", "openalex", "scienti", "minciencias", "staff")),
        "types": sorted({t.get("type") for t in a.get("types") or [] if isinstance(t, dict) and t.get("type")})[:6],
        "country": by_source(a.get("addresses"), "country", ("ror", "openalex", None)) or next((x.get("country") for x in a.get("addresses") or [] if isinstance(x, dict)), None),
        "products_count": a.get("products_count"), "citations": counts(a.get("citations_count")),
        "h_index": a.get("h_index"), "minciencias_category": latest_rank(a.get("ranking")),
        "part_of": [{"id": r.get("id"), "name": r.get("name")} for r in a.get("relations") or [] if isinstance(r, dict) and r.get("name")][:5],
        "external_ids": ids(a.get("external_ids")),
    }
    return {k: v for k, v in out.items() if v not in (None, [], {})}


def source(s):
    pub = s.get("publisher") or {}
    out = {
        "id": s.get("id"),
        "name": s.get("name") or by_source(s.get("names"), "name", ("openalex", "scimago", "publindex", "doaj")),
        "publisher": pub.get("name") if isinstance(pub, dict) else pub,
        "issn": sorted({x.get("id") for x in s.get("external_ids") or [] if isinstance(x, dict) and x.get("source") in ("issn", "issn_l", "pissn", "eissn")}),
        "colombian_products": s.get("products_count"),
        "global_products": s.get("global_products_count"), "global_citations": s.get("global_citations_count"),
        "open_access_status": s.get("open_access_status"),
        "latest_scimago_quartile": latest_rank(s.get("ranking"), ("scimago Best Quartile",)),
        "latest_publindex": latest_rank(s.get("ranking"), ("publindex",)),
    }
    return {k: v for k, v in out.items() if v not in (None, [], {})}


def map_rows(plot):
    """A GeoJSON map plot as {name, code, count} rows with a count, largest first.

    The shapes weigh ~300 kB and tell a model nothing; sorting first means a trimmed list drops the smallest counts.
    """
    rows = []
    for f in plot.get("features") or []:
        p = (f.get("properties") or {}) if isinstance(f, dict) else {}
        if p.get("count"):
            rows.append({"name": p.get("name") or p.get("NOMBRE_DPT"), "code": p.get("country_code") or p.get("DPTO"),
                         "count": p["count"]})
    return sorted(rows, key=lambda r: -r["count"])


def page_meta(meta, page, size):
    meta = meta or {}
    total = meta.get("count")
    return {"total": total, "page": page, "page_size": size,
            "has_more": bool((meta.get("cursor") or {}).get("next")) or (isinstance(total, int) and page * size < total)}
