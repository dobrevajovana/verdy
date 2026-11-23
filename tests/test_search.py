"""Terms searched in the ontologies: which candidates become matches, of what type, in what order."""

import pytest

import verdy
from verdy import embed
from verdy.sources import query_text


def test_only_the_chosen_ontologies(services):
    ms = verdy.match(["Lynx lynx", "Estuaries", "Coastal lagoons"], ["envo"])
    assert {m["ontology"] for m in ms} == {"ENVO"}
    by = {(m["term"], m["match_label"]): m for m in ms}
    assert by[("Estuaries", "estuary")]["match_type"] == "skos:exactMatch"            # plural aside
    assert by[("Coastal lagoons", "lagoon")]["match_type"] == "skos:relatedMatch"
    assert not any(m["term"] == "Lynx lynx" for m in ms)
    assert "wikidata_search" not in services and "gbif_match" not in services       # not chosen, not asked


def test_taxonomies_take_exact_names_only(services):
    ms = verdy.match(["Lynx lynx", "Estuaries"], "ncbitaxon, gbif, wikidata")
    got = {(m["term"], m["ontology"]): m for m in ms}
    assert got[("Lynx lynx", "NCBITaxon")]["match_curie"] == "NCBITaxon:13125"
    assert got[("Lynx lynx", "GBIF")]["match_curie"] == "GBIF:2435240"
    assert got[("Lynx lynx", "Wikidata")]["match_type"] == "skos:exactMatch"          # by its alias
    assert ("Estuaries", "NCBITaxon") not in got                                     # 'estuaries bacterium' is not it
    assert ("Estuaries", "Wikidata") not in got                                      # an alias alone is no near match
    assert verdy.unmatched(["Lynx lynx", "Estuaries"], ms, "ncbitaxon,gbif") == {"ncbitaxon": ["Estuaries"], "gbif": ["Estuaries"]}


def test_parameters_in_cf_and_pato(services):
    ms = verdy.match(["air temperature [K]", "wind speed", "surface air temperature"], ["cf", "pato"])
    got = {(m["term"], m["ontology"], m["match_curie"]): m["match_type"] for m in ms}
    assert got[("air temperature [K]", "CF", "CF:air_temperature")] == "skos:exactMatch"      # units in brackets aside
    assert got[("surface air temperature", "CF", "CF:air_temperature")] == "skos:exactMatch"  # a CF alias
    assert got[("wind speed", "CF", "CF:wind_speed")] == "skos:exactMatch"
    assert got[("air temperature [K]", "PATO", "PATO:0000146")] == "skos:relatedMatch"
    assert next(m for m in ms if m["match_curie"] == "CF:air_temperature")["definition"].startswith("[K]")


def test_leading_codes_units_and_underscores():
    assert query_text("1330 Atlantic salt meadows") == "Atlantic salt meadows"
    assert query_text("air temperature [K]") == "air temperature" and query_text("air_temperature") == "air temperature"
    assert query_text("16S rRNA gene") == "16S rRNA gene"


def test_unknown_or_no_ontology(services):
    with pytest.raises(ValueError, match="nosuch"):
        verdy.match(["Lynx lynx"], ["nosuch"])
    with pytest.raises(ValueError):
        verdy.match(["Lynx lynx"], [])


def test_cache_makes_no_second_request(services):
    verdy.match(["Estuaries"], ["envo"])
    n = len(services)
    verdy.match(["Estuaries"], ["envo"])
    assert len(services) == n


def test_embeddings_rank_by_cosine(services, monkeypatch):
    """With embeddings, cosine similarity ranks candidates; words still decide exact matches."""
    import numpy as np
    monkeypatch.setattr(embed, "available", lambda: True)
    meaning = {"coastal lagoons": [1, 0, 0], "lagoon": [0.9, 0.436, 0], "coastal water": [0.3, 0.954, 0],
               "estuaries": [0, 0, 1], "estuary": [0, 0.1, 0.995], "water": [0, 1, 0], "tap water": [0, 0.99, 0.14]}

    def fake_encode(texts, model=embed.MODEL):
        return [np.array(v) / np.linalg.norm(v) for v in
                (next((meaning[k] for k in meaning if t.lower().split(".")[0].strip() == k), [0.577, 0.577, 0.577])
                 for t in texts)]
    monkeypatch.setattr(embed, "encode", fake_encode)
    ms = verdy.match(["Coastal lagoons", "Estuaries", "Lynx lynx"], ["envo", "ncbitaxon"])
    lag = [m for m in ms if m["term"] == "Coastal lagoons"]
    assert lag[0]["match_label"] == "lagoon" and lag[0]["match_type"] == "skos:closeMatch"   # cosine 0.9 >= 0.70
    assert lag[0]["confidence"] == 0.9 and lag[0]["cosine"] == 0.9
    assert (lag[0]["method"], lag[0]["why"]) == ("cosine", "cosine 0.9 (word overlap 0.5)")
    assert all(m["match_label"] != "coastal water" for m in lag)          # cosine 0.3, overlap 0.33: dropped
    assert next(m for m in ms if m["term"] == "Estuaries")["match_type"] == "skos:exactMatch"
    lynx = next(m for m in ms if m["term"] == "Lynx lynx")
    assert lynx["ontology"] == "NCBITaxon" and lynx["cosine"] is None      # taxonomies: exact names only
    strict = verdy.match(["Coastal lagoons"], ["envo"], min_cosine=0.95)
    assert strict[0]["match_label"] == "lagoon" and strict[0]["match_type"] == "skos:relatedMatch"   # kept on words only
    words = verdy.match(["Coastal lagoons"], ["envo"], embeddings=False)
    assert words[0]["cosine"] is None and words[0]["match_type"] == "skos:relatedMatch"
    tap = verdy.match(["water"], ["envo"])[0]                             # says more than the term: words only
    assert tap["match_label"] == "tap water" and tap["cosine"] > 0.95
    assert (tap["match_type"], tap["confidence"]) == ("skos:relatedMatch", 0.5) and "says more" in tap["why"]
    assert tap["method"] == "ontology name"


def test_embeddings_need_the_extra(services):
    with pytest.raises(ValueError, match="verdy\\[embeddings\\]"):
        verdy.match(["Estuaries"], ["envo"], embeddings=True)


def test_ontology_ids_typed_in_values_come_first(services):
    names = ["soil [ENVO:00001998]", "marine biome ENVO: 01000024", "lake (ENVO_00001998)", "estuary ENVO:99999999"]
    got = {}
    for m in verdy.match(names, ["envo"]):
        got.setdefault(m["term"], []).append(m)
    soil = got["soil [ENVO:00001998]"]                       # the ID fits its words: it settles the term
    assert [(m["match_curie"], m["match_type"], m["confidence"], m["method"], m["why"]) for m in soil] == [
        ("ENVO:00001998", "skos:exactMatch", 1.0, "ID", "ID in the text")]
    marine = got["marine biome ENVO: 01000024"][0]           # the ID's label says more than the text
    assert (marine["match_type"], marine["confidence"]) == ("skos:relatedMatch", 0.75) and "benthic" in marine["why"]
    lake = got["lake (ENVO_00001998)"]                       # the ID is something else than the text
    assert (lake[0]["confidence"], lake[0]["searched_for"]) == (0.5, "lake") and "not what the term says" in lake[0]["why"]
    estuary = got["estuary ENVO:99999999"]                   # an ID OLS4 does not know: the words are searched
    assert [m["match_curie"] for m in estuary] == ["ENVO:00000045"]
    assert (estuary[0]["method"], estuary[0]["why"]) == ("ontology name", "the label or a synonym is the term")
    assert verdy.match(["soil [ENVO:00001998]"], ["pato"]) == []     # an ENVO ID says nothing about PATO
    assert query_text("marine biome ENVO: 00000447") == "marine biome"


def test_rank_is_best_first_and_a_typed_id_wins_a_tie(services):
    ms = verdy.match(["estuary ENVO:00001998", "estuary ENVO:00000045"], ["envo"])
    wrong = sorted((m["rank"], m["match_label"], m["confidence"]) for m in ms if m["term"] == "estuary ENVO:00001998")
    assert wrong == [(1, "estuary", 1.0), (2, "soil", 0.5)]          # the better match first, the wrong ID still there
    right = [m for m in ms if m["term"] == "estuary ENVO:00000045"]
    assert [(m["rank"], m["why"]) for m in right] == [(1, "ID in the text")]   # a fitting ID settles it: no search
    from verdy.match import _ranked                                  # equal confidence: the typed ID (listed first) stays first
    tie = _ranked([{"confidence": 1.0, "why": "ID in the text"}, {"confidence": 1.0, "why": ""}])
    assert [(m["rank"], m["why"]) for m in tie] == [(1, "ID in the text"), (2, "")]
