"""Mock 10 request functions in sources.py, answering from fake_data.py, and the ``services``
fixture that swaps them in."""

import pytest
from fake_data import (ANCESTORS, CF, ENA, GBIF, GOLD, NATURA2000_HABITATS, NATURA2000_SPECIES, OLS_ONTOLOGIES,
                       OLS_SEARCH, OLS_TERMS, WIKIDATA, WIKIDATA_DECOY)

from verdy import embed, gold, sources


def ena_search(result, fields, keys, accessions):
    """The ``result`` records (sample, read_run, study) whose ``keys`` hold one of ``accessions``, with only
    ``fields``; "" for a field the record has no value in, as ENA does."""
    asked = {a.upper() for a in accessions}
    rows = []
    for record in ENA[result]:
        if any(str(record.get(key, "")).upper() in asked for key in keys):
            rows.append({field: record.get(field, "") for field in fields})
    return rows


def ols_terms(obo_id):
    if obo_id not in OLS_TERMS:
        return []
    return [OLS_TERMS[obo_id]]


def ols_ancestors(ontology, iri):
    return ANCESTORS.get(iri, [])


def ols_search(q, ontology, exact, fields, **options):
    return OLS_SEARCH.get((ontology, q.lower()), [])


def ols_ontology(name):
    if name not in OLS_ONTOLOGIES:
        return {}
    return {"title": name, "preferredPrefix": OLS_ONTOLOGIES[name]}


def ols_all_terms(ontology):
    """GOLD's classes (the only ontology verdy reads whole)."""
    terms = []
    for iri, label, links in GOLD:
        terms.append({"iri": iri, "label": label, "annotation": links})
    return terms


def gbif_match(name):
    return GBIF.get(name, {"matchType": "NONE"})


def wikidata_search(name):
    return WIKIDATA.get(name, WIKIDATA_DECOY)


def natura2000_layer(layer, fields):
    """Layer 5 holds the habitat types, layer 6 the species."""
    if layer == 5:
        return NATURA2000_HABITATS
    return NATURA2000_SPECIES


def cf_table():
    return CF


FAKES = {"ena_search": ena_search, "ols_terms": ols_terms, "ols_ancestors": ols_ancestors, "ols_search": ols_search,
         "ols_ontology": ols_ontology, "ols_all_terms": ols_all_terms, "gbif_match": gbif_match,
         "wikidata_search": wikidata_search, "natura2000_layer": natura2000_layer, "cf_table": cf_table}


def no_embeddings():
    return False


def no_requests(url, **params):
    raise AssertionError(f"A request the tests do not fake: {url}")


@pytest.fixture
def services(monkeypatch, tmp_path):
    """Fake web services and an empty cache for each test. Returns the names of the request functions
    called, in order ("ena_search", "ols_terms", ...), so a test can count what was asked."""
    monkeypatch.setattr(sources, "CACHE", tmp_path / "cache")      # a fresh cache: nothing left from another test
    monkeypatch.setattr(sources, "_cf_terms", None)                 # read the CF table and build GOLD again
    monkeypatch.setattr(gold, "_model", None)
    monkeypatch.setattr(embed, "available", no_embeddings)          # words only, unless a test turns embeddings on
    monkeypatch.setattr(sources, "_json", no_requests)              # a request function left unfaked fails loudly
    calls = []

    def recorded(name, fake):
        """The fake, noting its name in ``calls`` each time it is called."""
        def call(*args, **kwargs):
            calls.append(name)
            return fake(*args, **kwargs)
        return call

    for name, fake in FAKES.items():
        monkeypatch.setattr(sources, name, recorded(name, fake))
    return calls
