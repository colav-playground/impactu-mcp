"""Offline tests of the record reducers."""
from impactu_mcp import compact as C


def test_inverted_abstract_is_rebuilt():
    w = {"abstracts": [{"source": "openalex", "abstract": {"matter": [1], "Dark": [0], "halos": [2]}}]}
    assert C.abstract_text(w) == "Dark matter halos"


def test_dates_use_colombian_time():
    assert C.date(1790716409) == "2026-09-29"
    assert C.date(-1) is None


def test_national_ids_are_dropped():
    # Source names as Kahi stores them.
    private = ["cc", "Cédula de Ciudadanía", "Cédula de Extranjería", "Pasaporte", "Passport", "Tarjeta de Identidad"]
    p = {"id": "1", "external_ids": [*({"source": s, "id": "123"} for s in private), {"source": "orcid", "id": "https://orcid.org/x"}]}
    assert C.person(p)["external_ids"] == {"orcid": "https://orcid.org/x"}


def test_map_keeps_counts_without_shapes():
    plot = {"type": "FeatureCollection", "features": [
        {"geometry": {"coordinates": [[1, 2]]}, "properties": {"name": "Peru", "country_code": "PE", "count": 3}},
        {"geometry": {}, "properties": {"name": "Chad", "country_code": "TD", "count": 0}},
        {"geometry": {}, "properties": {"NOMBRE_DPT": "ANTIOQUIA", "DPTO": "05", "count": 9, "AREA": 1.5}},
    ]}
    assert C.map_rows(plot) == [{"name": "ANTIOQUIA", "code": "05", "count": 9}, {"name": "Peru", "code": "PE", "count": 3}]


def test_product_picks_values_by_source():
    w = {"id": "x", "titles": [{"source": "scienti", "title": "B"}, {"source": "openalex", "title": "A"}],
         "product_types": [{"source": "openalex", "name": "article"}, {"source": "impactu", "name": "Artículo de revista"}],
         "citations_count": [{"source": "openalex", "count": 3}, {"source": "scholar", "count": 5}], "year_published": 2020,
         "source": {"name": "J", "ranking": [{"source": "scimago Best Quartile", "rank": "Q1",
                                              "from_date": 1577854800, "to_date": 1609390800}]}}
    p = C.product(w)
    assert (p["title"], p["type"], p["citations"], p["scimago_quartile"]) == ("A", "Artículo de revista", {"openalex": 3, "scholar": 5}, "Q1")
