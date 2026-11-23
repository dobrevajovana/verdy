"""The web requests in sources.py: what each one asks for, and what it reads from the answer.

Only ``sources._json`` (the function that sends a request) is replaced: it keeps the address and parameters
it was given and returns a canned answer. Every other test file fakes these request functions themselves.
"""

import pytest

from verdy import sources
from verdy.constants import ART17, CF_TABLE, ENA_API, GBIF_MATCH, OBO, OLS, WIKIDATA_API


@pytest.fixture
def answer(monkeypatch):
    """``asked = answer(reply)``: every request now gets ``reply`` (or, given several, the next one each time).
    ``asked`` fills with a (url, params) pair per request."""
    asked = []

    def use(*replies):
        replies = list(replies)

        def fake_json(url, **params):
            asked.append((url, params))
            if len(replies) > 1:
                return replies.pop(0)
            return replies[0]

        monkeypatch.setattr(sources, "_json", fake_json)
        return asked

    return use


def test_ena_search(answer):
    rows = [{"sample_accession": "SAMN13091181", "host_tax_id": "9913"}]
    asked = answer(rows)
    got = sources.ena_search("sample", ("sample_accession", "host_tax_id"),
                             ("sample_accession", "secondary_sample_accession"), ["SAMN13091181", "SRS5634417"])
    assert got == rows
    assert asked == [(ENA_API + "/search", {
        "_post": True, "result": "sample", "format": "json", "limit": 0, "fields": "sample_accession,host_tax_id",
        "query": 'sample_accession="SAMN13091181" OR secondary_sample_accession="SAMN13091181"'
                 ' OR sample_accession="SRS5634417" OR secondary_sample_accession="SRS5634417"'})]
    answer({})                                                  # ENA's empty answer: nothing found
    assert sources.ena_search("sample", ("sample_accession",), ("sample_accession",), ["SAMD999"]) == []


def test_ols_terms(answer):
    entry = {"iri": OBO + "ENVO_00002046", "label": "activated sludge", "ontology_name": "envo"}
    asked = answer({"_embedded": {"terms": [entry]}})
    assert sources.ols_terms("ENVO:00002046") == [entry]
    assert asked == [(OLS + "/terms", {"obo_id": "ENVO:00002046"})]
    answer({})                                                  # OLS4 does not know the ID
    assert sources.ols_terms("ENVO:99999999") == []


def test_ols_ancestors(answer):
    asked = answer({"_embedded": {"terms": [{"obo_id": "ENVO:00002044", "label": "sludge"}, {"obo_id": "ENVO:1"}]}})
    assert sources.ols_ancestors("envo", OBO + "ENVO_00002046") == [
        {"id": "ENVO:00002044", "label": "sludge"}, {"id": "ENVO:1", "label": ""}]
    # The IRI encoded twice: ':' is %3A then %253A, '/' is %2F then %252F.
    encoded = "http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FENVO_00002046"
    assert asked == [(f"{OLS}/ontologies/envo/terms/{encoded}/hierarchicalAncestors", {"size": 500})]


def test_ols_search(answer):
    docs = [{"obo_id": "NCBITaxon:9913", "label": "Bos taurus"}]
    asked = answer({"response": {"docs": docs}})
    assert sources.ols_search("cow", "ncbitaxon", True, "obo_id,label", queryFields="label,synonym") == docs
    assert asked == [(OLS + "/search", {"q": "cow", "ontology": "ncbitaxon", "exact": "true", "rows": 10,
                                        "fieldList": "obo_id,label", "queryFields": "label,synonym"})]


def test_ols_ontology(answer):
    asked = answer({"config": {"title": "Environment Ontology", "preferredPrefix": "ENVO"}})
    assert sources.ols_ontology("envo") == {"title": "Environment Ontology", "preferredPrefix": "ENVO"}
    assert asked == [(OLS + "/ontologies/envo", {})]
    answer({})                                                  # not in OLS4
    assert sources.ols_ontology("nosuch") == {}


def test_ols_all_terms_reads_every_page(answer):
    first = {"_embedded": {"terms": [{"iri": "a"}]}, "page": {"totalPages": 2}}
    second = {"_embedded": {"terms": [{"iri": "b"}]}, "page": {"totalPages": 2}}
    asked = answer(first, second)
    assert sources.ols_all_terms("gold") == [{"iri": "a"}, {"iri": "b"}]
    assert asked == [(OLS + "/ontologies/gold/terms", {"size": 500, "page": 0}),
                     (OLS + "/ontologies/gold/terms", {"size": 500, "page": 1})]


def test_gbif_match(answer):
    match = {"usageKey": 2435240, "canonicalName": "Lynx lynx", "matchType": "EXACT"}
    asked = answer(match)
    assert sources.gbif_match("Lynx lynx") == match
    assert asked == [(GBIF_MATCH, {"name": "Lynx lynx", "verbose": "true"})]


def test_wikidata_search(answer):
    items = [{"id": "Q43375", "label": "Eurasian lynx", "aliases": ["Lynx lynx"]}]
    asked = answer({"search": items})
    assert sources.wikidata_search("Lynx lynx") == items
    assert asked == [(WIKIDATA_API, {"action": "wbsearchentities", "search": "Lynx lynx", "language": "en",
                                     "limit": 7, "format": "json", "type": "item"})]


def test_natura2000_layer(answer):
    habitat = {"reference_habitatlist.habitat_code": "1130", "reference_habitatlist.label": "Estuaries"}
    asked = answer({"features": [{"attributes": habitat}]})
    fields = ["reference_habitatlist.habitat_code", "reference_habitatlist.label"]
    assert sources.natura2000_layer(5, fields) == [habitat]
    assert asked == [(ART17 + "/5/query", {"where": "1=1", "outFields": ",".join(fields),
                                           "returnDistinctValues": "true", "returnGeometry": "false", "f": "json"})]
    answer({"error": {"code": 400}})                            # the service answered, but with no rows
    assert sources.natura2000_layer(5, fields) is None


def test_cf_table(monkeypatch):
    asked = []

    class Reply:
        content = b"<standard_name_table/>"

        def raise_for_status(self):
            pass

    def fake_get(url, **options):
        asked.append(url)
        return Reply()

    monkeypatch.setattr(sources.requests, "get", fake_get)
    assert sources.cf_table() == b"<standard_name_table/>"
    assert asked == [CF_TABLE]


@pytest.mark.parametrize("request_", [
    lambda: sources.ena_search("sample", ("sample_accession",), ("sample_accession",), ["SAMN1"]),
    lambda: sources.ols_terms("ENVO:1"),
    lambda: sources.ols_ancestors("envo", OBO + "ENVO_1"),
    lambda: sources.ols_search("x", "envo", False, "iri"),
    lambda: sources.ols_ontology("envo"),
    lambda: sources.ols_all_terms("gold"),
    lambda: sources.gbif_match("x"),
    lambda: sources.wikidata_search("x"),
    lambda: sources.natura2000_layer(5, ["a"]),
])
def test_no_answer_is_none(answer, request_):
    """A service that did not answer gives None, never an empty answer, so it is not cached and is asked again."""
    answer(None)
    assert request_() is None
