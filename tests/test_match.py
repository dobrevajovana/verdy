"""verdy.match with every web service stubbed.

Run:  python -m pytest -q
"""

import csv
import json
import re

import pytest

import verdy
from verdy import embed, gold, sources

ENVO = "http://purl.obolibrary.org/obo/ENVO_"
TAXON = "http://purl.obolibrary.org/obo/NCBITaxon_"
PATO = "http://purl.obolibrary.org/obo/PATO_"
CF = b"""<?xml version="1.0"?><standard_name_table>
<entry id="air_temperature"><canonical_units>K</canonical_units><description>Air temperature is the bulk temperature of the air.</description></entry>
<entry id="wind_speed"><canonical_units>m s-1</canonical_units><description>Speed is the magnitude of velocity.</description></entry>
<alias id="surface_air_temperature"><entry_id>air_temperature</entry_id></alias>
</standard_name_table>"""


# Real ENA records
AIR, SOIL, COW, CAT, SLUDGE = "SAMEA104135898", "SAMEA104135884", "SAMN13091181", "SAMD00659239", "SAMD00444474"
ENA = {"sample": [
    # air and soil, both in project PRJEB21441
    {"sample_accession": AIR, "secondary_sample_accession": "ERS1794916", "study_accession": "PRJEB21441",
     "scientific_name": "air metagenome", "broad_scale_environmental_context": "urban biome",
     "local_environmental_context": "city", "environmental_medium": "air", "environment_biome": "urban biome",
     "environment_feature": "city", "environment_material": "air", "host_scientific_name": "Not applicable",
     "sample_title": "1521.Chi.1.s.8.1.sequences", "sample_description": "air sample Chi.1",
     "description": "air sample Chi.1"},
    {"sample_accession": SOIL, "secondary_sample_accession": "ERS1794902", "study_accession": "PRJEB21441",
     "scientific_name": "soil metagenome", "broad_scale_environmental_context": "forest biome",
     "local_environmental_context": "forest", "environmental_medium": "soil", "environment_biome": "forest biome",
     "environment_feature": "forest", "environment_material": "soil", "host_scientific_name": "Not applicable",
     "sample_title": "1521.CF3.s.6.1.sequences", "sample_description": "soil sample CF3",
     "description": "soil sample CF3"},
    # cow feces, the host by its taxon ID
    {"sample_accession": COW, "secondary_sample_accession": "SRS5634417", "study_accession": "PRJNA579572",
     "scientific_name": "gut metagenome", "isolation_source": "Cow feces", "host": "Bos taurus",
     "host_scientific_name": "Bos taurus", "host_tax_id": "9913",
     "sample_title": "Metagenome or environmental sample from gut metagenome",
     "sample_description": "Metagenome or environmental sample from gut metagenome",
     "description": "Metagenome or environmental sample from gut metagenome"},
    # feces with no host given (only the title names the cat)
    {"sample_accession": CAT, "secondary_sample_accession": "DRS362558", "study_accession": "PRJDB17088",
     "scientific_name": "feces metagenome", "broad_scale_environmental_context": "subtropical forests",
     "environmental_medium": "feces", "environment_biome": "subtropical forests", "environment_material": "feces",
     "sample_title": "Iriomote cat fecal sample in summer 10", "sample_description": "Keywords: GSC:MIxS MIMS:6.0",
     "description": "Keywords: GSC:MIxS MIMS:6.0"},
    # lab-scale activated sludge; the organism is a worm living in it
    {"sample_accession": SLUDGE, "secondary_sample_accession": "DRS229742", "study_accession": "PRJDB13106",
     "scientific_name": "Monopylephorus rubroniveus", "broad_scale_environmental_context": "activated sludge",
     "local_environmental_context": "lab-scale activated sludge at Ritumeikan University",
     "environmental_medium": "water", "environment_biome": "activated sludge",
     "environment_feature": "lab-scale activated sludge at Ritumeikan University", "environment_material": "water",
     "sample_title": "Monopylephorus rubroniveus WR", "sample_description": "Keywords: GSC:MIxS MIGS:6.0",
     "description": "Keywords: GSC:MIxS MIGS:6.0"}],
    "read_run": [{"run_accession": "ERR2012938", "experiment_accession": "ERX2072610", "sample_accession": AIR}],
    "study": [{"study_accession": "PRJEB21441", "secondary_study_accession": "ERP023684",
               "study_title": "Samples presented at EMP conference June 2011 Shenzhen"}]}

TERMS = {"ENVO:00001998": {"iri": ENVO + "00001998", "label": "soil", "ontology_name": "envo", "synonyms": []},
         "ENVO:01000024": {"iri": ENVO + "01000024", "label": "marine benthic biome", "ontology_name": "envo"},
         "ENVO:00000045": {"iri": ENVO + "00000045", "label": "estuary", "ontology_name": "envo"},
         "NCBITaxon:9913": {"iri": TAXON + "9913", "label": "Bos taurus", "ontology_name": "ncbitaxon",
                            "synonyms": ["cow", "domestic cattle"]}}
UBERON = "http://purl.obolibrary.org/obo/UBERON_"
TERMS.update({"UBERON:0001988": {"iri": UBERON + "0001988", "label": "feces", "ontology_name": "uberon",
                                 "synonyms": ["faeces", "stool", "dung"]},
              "UBERON:0000059": {"iri": UBERON + "0000059", "label": "large intestine", "ontology_name": "uberon"},
              "ENVO:00002005": {"iri": ENVO + "00002005", "label": "air", "ontology_name": "envo"},
              "ENVO:00002046": {"iri": ENVO + "00002046", "label": "activated sludge", "ontology_name": "envo"}})
# OLS4's GOLD: paths with their links (as OLS4 gives them, full IRIs); Fish states one class, Algae none.
_P = "https://w3id.org/gold.path/"
GOLD = [(_P + "1", "Host-associated", {}),
        (_P + "2", "Host-associated > Mammals", {"host_taxon": [TAXON + "40674"]}),
        (_P + "3", "Host-associated > Mammals > Digestive system > Large intestine",
         {"host_taxon": [TAXON + "40674"], "anatomical_site": [UBERON + "0000059"]}),
        (_P + "4", "Host-associated > Mammals > Digestive system > Large intestine > Fecal",
         {"host_taxon": [TAXON + "40674"], "anatomical_site": [UBERON + "0000059"], "env_medium": [UBERON + "0001988"]}),
        (_P + "5", "Host-associated > Fish", {"host_taxon": [TAXON + "7777"]}),
        (_P + "6", "Host-associated > Fish > Skin", {"host_taxon": [TAXON + "7777"]}),
        (_P + "7", "Host-associated > Algae", {}),
        (_P + "11", "Host-associated > Birds", {"host_taxon": [TAXON + "8782"]}),
        (_P + "12", "Host-associated > Birds > Digestive system > Fecal",
         {"host_taxon": [TAXON + "8782"], "env_medium": [UBERON + "0001988"]}),
        (_P + "8", "Engineered > Lab enrichment > Feces", {"env_medium": [UBERON + "0001988"]}),
        (_P + "13", "Engineered > Wastewater", {}),
        (_P + "14", "Engineered > Wastewater > Activated Sludge", {"env_medium": [ENVO + "00002046"]}),
        (_P + "9", "Environmental > Air", {"env_medium": [ENVO + "00002005"]}),
        (_P + "10", "Environmental > Air > Outdoor Air", {"env_medium": [ENVO + "00002005"]}),
        ("https://w3id.org/gold.vocab/Air", "Air", {})]
ANCESTORS = {TAXON + "9913": [("NCBITaxon:9903", "Bos"), ("NCBITaxon:9895", "Bovidae"), ("NCBITaxon:40674", "Mammalia"),
                              ("NCBITaxon:32525", "Theria <mammals>"), ("NCBITaxon:33208", "Metazoa"),
                              ("NCBITaxon:2759", "Eukaryota")],
             ENVO + "00002046": [("ENVO:00002044", "sludge"), ("ENVO:0010001", "anthropogenic environmental material")]}


@pytest.fixture
def services(monkeypatch, tmp_path):
    """OLS4 (ENVO, NCBITaxon, PATO), GBIF, Wikidata and the CF table, answering from these tables."""
    monkeypatch.setattr(sources, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(sources, "_cf_terms", None)
    monkeypatch.setattr(gold, "_model", None)
    monkeypatch.setattr(embed, "available", lambda: False)        # words only, unless a test turns embeddings on
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "cf-standard-name-table.xml").write_bytes(CF)
    ols = {("envo", "estuary"): [{"iri": ENVO + "00000045", "label": "estuary", "obo_id": "ENVO:00000045"}],
           ("envo", "lagoon"): [{"iri": ENVO + "00000038", "label": "lagoon", "obo_id": "ENVO:00000038"}],
           ("envo", "coastal"): [{"iri": ENVO + "1", "label": "coastal water", "obo_id": "ENVO:1"}],
           ("envo", "water"): [{"iri": ENVO + "2", "label": "tap water", "obo_id": "ENVO:2"}],
           ("ncbitaxon", "lynx lynx"): [{"iri": TAXON + "13125", "label": "Lynx lynx", "obo_id": "NCBITaxon:13125"}],
           ("ncbitaxon", "cow"): [{"iri": TAXON + "9913", "label": "Bos taurus", "obo_id": "NCBITaxon:9913",
                                   "synonym": ["cow"]}],
           ("ncbitaxon", "bos taurus"): [{"iri": TAXON + "9913", "label": "Bos taurus", "obo_id": "NCBITaxon:9913",
                                          "synonym": ["cow"]}],
           ("envo", "activated sludge"): [{"iri": ENVO + "00002046", "label": "activated sludge",
                                           "obo_id": "ENVO:00002046", "is_defining_ontology": True}],
           ("ncbitaxon", "mammals"): [{"iri": TAXON + "40674", "label": "Mammalia", "obo_id": "NCBITaxon:40674"}],
           ("ncbitaxon", "fish"): [{"iri": TAXON + "7777", "label": "Chondrichthyes", "obo_id": "NCBITaxon:7777"},
                                   {"iri": TAXON + "7898", "label": "Actinopterygii", "obo_id": "NCBITaxon:7898"}],
           ("ncbitaxon", "algae"): [{"iri": TAXON + "2763", "label": "Rhodophyta", "obo_id": "NCBITaxon:2763"}],
           ("ncbitaxon", "estuaries"): [{"iri": TAXON + "1", "label": "estuaries bacterium"}],
           ("pato", "temperature"): [{"iri": PATO + "0000146", "label": "temperature", "obo_id": "PATO:0000146"}],
           ("envo", "urban biome"): [{"iri": ENVO + "01000249", "label": "urban biome", "obo_id": "ENVO:01000249",
                                      "is_defining_ontology": True}],
           ("envo", "air"): [{"iri": ENVO + "00002005", "label": "air", "obo_id": "ENVO:00002005", "is_defining_ontology": True}],
           ("gold", "air"): [{"iri": "https://w3id.org/gold.path/3962", "label": "Environmental > Air > Outdoor Air",
                              "is_defining_ontology": False},
                             {"iri": "https://w3id.org/gold.vocab/Air", "label": "Air", "is_defining_ontology": False}]}
    calls = []

    def fake(url, **p):
        calls.append(url)
        if url.endswith("/portal/api/search"):                         # ENA, asked in bulk
            asked = re.findall(r'(\w+)="([^"]+)"', p["query"])
            rows = ENA[p["result"]]
            return [{f: r.get(f, "") for f in p["fields"].split(",")} for r in rows
                    if any(str(r.get(k, "")).upper() == v.upper() for k, v in asked)]
        if url.endswith("/hierarchicalAncestors"):                    # OLS4 ancestors of an IRI (encoded twice)
            from urllib.parse import unquote
            iri = unquote(unquote(url.split("/terms/")[1].rsplit("/", 1)[0]))
            return {"_embedded": {"terms": [{"obo_id": i, "label": a} for i, a in ANCESTORS[iri]]}} if iri in ANCESTORS else {}
        if url.endswith("/ontologies/gold/terms"):                     # OLS4's GOLD, a page at a time
            return {"_embedded": {"terms": [{"iri": i, "label": lab, "annotation": a} for i, lab, a in GOLD]},
                    "page": {"totalPages": 1}}
        if "/ontologies/" in url:
            oid = url.rsplit("/", 1)[1]
            return {"config": {"title": oid, "preferredPrefix": {"ncbitaxon": "NCBITaxon"}.get(oid, oid.upper())}} \
                if oid in ("envo", "ncbitaxon", "pato", "gold") else {}
        if url.endswith("/api/terms"):                                  # OLS4 term by CURIE
            return {"_embedded": {"terms": [TERMS[p["obo_id"]]]}} if p["obo_id"] in TERMS else {}
        if url.endswith("/search"):
            return {"response": {"docs": ols.get((p["ontology"], p["q"].lower()), [])}}
        if "species/match" in url:
            return {"usageKey": 2435240, "canonicalName": "Lynx lynx", "matchType": "EXACT"} if p["name"] == "Lynx lynx" \
                else {"matchType": "NONE"}
        if "MapServer" in url:                                          # Natura 2000 (Article 17)
            if "/5/" in url:
                return {"features": [{"attributes": {"reference_habitatlist.habitat_code": "1130",
                                                     "reference_habitatlist.label": "Estuaries"}}]}
            return {"features": [{"attributes": {"reference_specieslist.species_code": "1361",
                                                 "reference_specieslist.species_name": "Lynx lynx",
                                                 "reference_specieslist.taxonomical_group": "Mammals"}}]}
        if "wikidata" in url:
            return {"search": [{"id": "Q43375", "label": "Eurasian lynx", "aliases": ["Lynx lynx"]}]} if p["search"] == "Lynx lynx" \
                else {"search": [{"id": "Q9", "label": "some moth", "aliases": ["coastal lagoons moth"]}]}
        return {}
    monkeypatch.setattr(sources, "_json", fake)
    return calls


def test_read_terms_from_many_inputs(tmp_path):
    (tmp_path / "a.csv").write_text("id,Parameter,group\nx1,air temperature (°C),parameter\nx2,Estuaries,habitat\nx2,again,habitat\n")
    (tmp_path / "b.txt").write_text("Lynx lynx\n\nEstuaries\n")
    (tmp_path / "c.tsv").write_text("code\tlabel\n1130\tEstuaries\n")
    assert verdy.read_terms(tmp_path / "a.csv") == [
        {"id": "x1", "label": "air temperature (°C)", "category": "parameter"}, {"id": "x2", "label": "Estuaries", "category": "habitat"}]
    assert [t["label"] for t in verdy.read_terms(tmp_path / "b.txt")] == ["Lynx lynx", "Estuaries"]
    assert verdy.read_terms(tmp_path / "c.tsv")[0] == {"id": "1130", "label": "Estuaries", "category": None}
    assert [t["id"] for t in verdy.read_terms(["Lynx lynx", {"name": "Coastal lagoons"}])] == ["lynx_lynx", "coastal_lagoons"]
    with pytest.raises(ValueError):
        verdy.read_terms(tmp_path / "a.csv", column="nope")


def test_only_the_chosen_ontologies(services):
    ms = verdy.match(["Lynx lynx", "Estuaries", "Coastal lagoons"], ["envo"])
    assert {m["ontology"] for m in ms} == {"ENVO"}
    by = {(m["term"], m["match_label"]): m for m in ms}
    assert by[("Estuaries", "estuary")]["match_type"] == "skos:exactMatch"            # plural aside
    assert by[("Coastal lagoons", "lagoon")]["match_type"] == "skos:relatedMatch"
    assert not any(m["term"] == "Lynx lynx" for m in ms)
    assert not any("wikidata" in c or "gbif" in c for c in services)                  # not chosen, not asked


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
    from verdy.sources import query_text
    assert query_text("1330 Atlantic salt meadows") == "Atlantic salt meadows"
    assert query_text("air temperature [K]") == "air temperature" and query_text("air_temperature") == "air temperature"
    assert query_text("16S rRNA gene") == "16S rRNA gene"


def test_unknown_or_no_ontology(services):
    with pytest.raises(ValueError, match="nosuch"):
        verdy.match(["Lynx lynx"], ["nosuch"])
    with pytest.raises(ValueError):
        verdy.match(["Lynx lynx"], [])


def test_outputs(services, tmp_path):
    ms = verdy.match(["Lynx lynx", "Estuaries"], ["envo", "ncbitaxon"])
    for f in ("m.csv", "m.tsv", "m.json", "m.sssom.tsv"):
        verdy.save(ms, tmp_path / f)
    rows = list(csv.DictReader(open(tmp_path / "m.csv")))
    assert {r["match_curie"] for r in rows} == {"ENVO:00000045", "NCBITaxon:13125"}
    assert json.loads((tmp_path / "m.json").read_text()) == ms
    sssom = (tmp_path / "m.sssom.tsv").read_text()
    assert "semapv:LexicalMatching" in sssom and "#   ENVO: http://purl.obolibrary.org/obo/ENVO_" in sssom


def test_cache_makes_no_second_request(services):
    verdy.match(["Estuaries"], ["envo"])
    n = len(services)
    verdy.match(["Estuaries"], ["envo"])
    assert len(services) == n


def test_command_line(services, tmp_path, capsys):
    from verdy.__main__ import main
    (tmp_path / "n.csv").write_text("name\nLynx lynx\nEstuaries\n")
    assert main(["--list"]) == 0 and "ncbitaxon" in capsys.readouterr().out
    assert main([str(tmp_path / "n.csv"), "-o", "envo,ncbitaxon", "--out", str(tmp_path / "o.csv")]) == 0
    err = capsys.readouterr().err
    assert "2 matches for 2 of 2 inputs" in err and "nothing in envo for: Lynx lynx" in err
    assert (tmp_path / "o.csv").exists()


def test_ids_are_looked_up_in_ena_and_the_ontologies(services):
    import importlib
    r = importlib.import_module("verdy.resolve")
    assert [r.kind(x) for x in (AIR, "ERS1794916", "ERR2012938", "PRJEB21441", "ENVO:00000045", "air")] == \
        ["sample", "sample", "run", "project", "name", "name"]
    assert r.resolve(AIR) == [("scientific_name", "air metagenome"), ("broad_scale_environmental_context", "urban biome"),
                              ("local_environmental_context", "city"), ("environmental_medium", "air"),
                              ("environment_biome", "urban biome"), ("environment_feature", "city"),
                              ("environment_material", "air")]                          # 'Not applicable' left out
    assert r.resolve("ERR2012938") == r.resolve(AIR)
    assert r.resolve("air temperature") == [("name", "air temperature")]
    assert r.resolve("SAMD999") == []


def test_ena_is_asked_in_bulk_with_the_sample_context(services):
    found = verdy.samples([AIR, "SRS5634417", "SAMD999", "ERR2012938", "ERP023684", "Estuaries"])
    ena = [c for c in services if "/portal/api/" in c]
    assert len(ena) == 4            # samples and runs' samples in one; runs in one; studies in one; the project in one
    assert found["SAMD999"] == [] and "Estuaries" not in found
    assert found[AIR][0]["context"] == {"sample_title": "1521.Chi.1.s.8.1.sequences",
                                        "sample_description": "air sample Chi.1", "description": "air sample Chi.1"}
    cow = found["SRS5634417"][0]                                       # by its secondary accession
    assert cow["sample"] == COW
    assert cow["values"] == [("scientific_name", "gut metagenome"), ("isolation_source", "Cow feces"),
                             ("host", "Bos taurus"), ("host_scientific_name", "Bos taurus")]
    assert cow["context"]["host_tax_id"] == "9913"
    assert found["ERR2012938"][0]["sample"] == AIR
    project = {r["sample"]: r for r in found["ERP023684"]}             # ERP023684 is PRJEB21441; SOIL has no runs
    assert set(project) == {AIR, SOIL}
    assert project[SOIL]["context"] == {"sample_title": "1521.CF3.s.6.1.sequences", "sample_description": "soil sample CF3",
                                        "description": "soil sample CF3", "study": "PRJEB21441",
                                        "study_title": "Samples presented at EMP conference June 2011 Shenzhen"}

    n = len(services)
    verdy.samples([AIR, "SRS5634417", "SAMD999", "ERR2012938", "ERP023684"])
    assert len(services) == n                                          # all cached, the unknown sample too
    verdy.samples([AIR], fields=["scientific_name", "sample_title"])
    assert len(services) == n + 1                                      # other fields: asked again
    assert verdy.samples([AIR], fields=["sample_title"])[AIR][0]["values"] == [("sample_title", "1521.Chi.1.s.8.1.sequences")]

    terms, unresolved = verdy.resolve_terms([{"id": "x", "label": "PRJEB21441"}, {"id": "y", "label": "SAMD999"}])
    soil = next(t for t in terms if t["label"] == "soil")
    assert (soil["id"], soil["input"], soil["context"]["study"]) == (SOIL, "PRJEB21441", "PRJEB21441")
    assert unresolved == ["SAMD999"]


def test_hosts_are_ncbitaxon_classes_from_ols4(services):
    cow = verdy.host({"host_tax_id": "9913", "host": "something else"})
    assert (cow["id"], cow["label"], cow["from"]) == ("NCBITaxon:9913", "Bos taurus", "host_tax_id")
    assert "Mammalia" in cow["ancestors"] and "Theria" in cow["ancestors"]          # OLS4's '<mammals>' tag left off
    assert "NCBITaxon:40674" in cow["ancestor_ids"]                                  # Mammalia, by ID
    assert verdy.host({"host": "cow"})["from"] == "host"                            # a common name is a synonym
    assert verdy.host({"host": "soil"}) is None and verdy.host({}) is None
    n = len(services)
    verdy.host({"host": "cow"})
    verdy.host({"host": "soil"})
    assert len(services) == n                                                        # cached, the miss too
    assert not any("ena/taxonomy" in c or "ncbi.nlm" in c for c in services)         # OLS4 only

    terms, _ = verdy.resolve_terms([{"id": "x", "label": COW}, {"id": "y", "label": "PRJEB21441"}])
    feces = next(t for t in terms if t["label"] == "Cow feces")
    assert feces["context"]["host_taxon"]["label"] == "Bos taurus"
    assert not any("host_taxon" in t["context"] for t in terms if t["id"] == AIR)      # 'Not applicable': no host


def test_gold_levels_are_named_by_what_gold_links_them_to(services):
    g = gold.load()
    assert g.names[("Host-associated", "Fecal")] == ["Fecal", "feces", "faeces", "stool", "dung"]   # UBERON feces
    assert g.names[("Host-associated", "Large intestine")] == ["Large intestine", "large intestine"]
    assert "large intestine" not in g.names[("Host-associated", "Fecal")]       # its parent links it first
    assert [c["label"] for c in verdy.search("stool", "gold")] == [
        "Engineered > Lab enrichment > Feces", "Host-associated > Birds > Digestive system > Fecal",
        "Host-associated > Mammals > Digestive system > Large intestine > Fecal"]
    assert not any("gold.vocab" in c["id"] for c in verdy.search("air", "gold"))  # paths only


def test_gold_paths_know_their_host(services):
    g = gold.load()
    fecal = g.by_label["Host-associated > Mammals > Digestive system > Large intestine > Fecal"]
    skin, algae = g.by_label["Host-associated > Fish > Skin"], g.by_label["Host-associated > Algae"]
    assert fecal["host_taxa"] == ["NCBITaxon:40674"]
    assert skin["host_taxa"] == ["NCBITaxon:7777", "NCBITaxon:7898"]           # GOLD's one class, and what "Fish" names
    assert algae["host_taxa"] == ["NCBITaxon:2763"]                             # GOLD states none: the name's
    assert g.by_label["Host-associated"]["host_taxa"] == []
    cow = verdy.host({"host": "cow"})
    salmon = {"id": "NCBITaxon:8030", "ancestor_ids": ["NCBITaxon:7898"]}
    assert g.host_fits(fecal, cow) is True and g.host_fits(skin, cow) is False and g.host_fits(skin, salmon) is True
    assert g.host_fits(fecal, None) is False and g.host_fits(g.by_label["Host-associated"], cow) is None
    n = len(services)
    gold._model = None
    gold.load()
    assert len(services) == n                                                   # rebuilt from the cache


def test_one_gold_path_and_one_envo_class_per_sample(services):
    verdy.match([COW, CAT, SLUDGE, "Estuaries"], ["gold", "envo", "ncbitaxon"])
    rows = {s["sample"]: s for s in verdy.match.samples}
    assert set(rows) == {COW, CAT, SLUDGE}                                  # samples only, not free text
    cow = rows[COW]                                                         # cow + feces: the mammals' Fecal
    assert cow["host"] == "Bos taurus"
    gold_, envo = cow["matches"]["gold"], cow["matches"]["envo"]
    assert gold_["match_label"] == "Host-associated > Mammals > Digestive system > Large intestine > Fecal"
    assert gold_["method"] == "ontology name" and gold_["match_type"] == "skos:closeMatch"
    assert (envo["match_curie"], envo["method"]) == ("UBERON:0001988", "GOLD medium")
    assert cow["matches"]["ncbitaxon"]["match_label"] == "Bos taurus"      # another ontology: its best match
    nohost = rows[CAT]["matches"]["gold"]                                   # feces, no host: what the hosts share
    assert (nohost["match_label"], nohost["match_type"], nohost["method"]) == \
        ("Host-associated", "skos:broadMatch", "shared parent")
    sludge = rows[SLUDGE]["matches"]                                        # ENVO places activated sludge under anthropogenic
    assert sludge["gold"]["match_label"] == "Engineered > Wastewater > Activated Sludge"
    assert sludge["envo"]["match_curie"] == "ENVO:00002046"

    table = {r["sample"]: r for r in verdy.sample_rows(verdy.match.samples)}    # one row each, side by side
    assert (table[COW]["gold_id"], table[COW]["envo_id"], table[COW]["status"]) == \
        ("GOLD.path:4", "UBERON:0001988", "matched")
    assert table[CAT]["envo_id"] == "UBERON:0001988"               # the tied Fecal paths agree on the medium
    assert table[CAT]["status"] == "no match in ncbitaxon"


def test_ids_in_predictions_out(services, tmp_path):
    (tmp_path / "ids.csv").write_text(f"sample_accession\n{AIR}\nEstuaries\nPRJEB21441\nSAMD999\n")
    ms = verdy.match(tmp_path / "ids.csv", ["envo", "gold", "natura2000"])
    rows = {(m["term_id"], m["term"], m["ontology"], m["match_curie"] or m["match_id"]): m for m in ms}
    air = rows[(AIR, "air", "ENVO", "ENVO:00002005")]
    assert air["category"] == "environmental_medium|environment_material" and air["match_type"] == "skos:exactMatch"
    assert (AIR, "urban biome", "ENVO", "ENVO:01000249") in rows
    assert any(k[0] == AIR and k[2] == "GOLD" and "Air" in rows[k]["match_label"] for k in rows)   # GOLD kept
    assert rows[("estuaries", "Estuaries", "Natura2000", "n2k:1130")]["match_type"] == "skos:exactMatch"
    assert verdy.match.unresolved == ["SAMD999"]
    assert not any(m["term_id"] == "PRJEB21441" for m in ms)        # a project's rows carry its samples' IDs


def test_free_text_and_ena_ids_together(services):
    ms = verdy.match([AIR, "Estuaries"], ["envo"])
    assert {(m["term_id"], m["term"]) for m in ms} >= {(AIR, "air"), (AIR, "urban biome"), ("estuaries", "Estuaries")}
    sssom = verdy.to_sssom(ms)
    assert f"biosample:{AIR}\t" in sssom and "term:estuaries" in sssom


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
    assert verdy.sources.query_text("marine biome ENVO: 00000447") == "marine biome"


def test_rank_is_best_first_and_a_typed_id_wins_a_tie(services):
    ms = verdy.match(["estuary ENVO:00001998", "estuary ENVO:00000045"], ["envo"])
    wrong = sorted((m["rank"], m["match_label"], m["confidence"]) for m in ms if m["term"] == "estuary ENVO:00001998")
    assert wrong == [(1, "estuary", 1.0), (2, "soil", 0.5)]          # the better match first, the wrong ID still there
    right = [m for m in ms if m["term"] == "estuary ENVO:00000045"]
    assert [(m["rank"], m["why"]) for m in right] == [(1, "ID in the text")]   # a fitting ID settles it: no search
    from verdy.match import _ranked                                  # equal confidence: the typed ID (listed first) stays first
    tie = _ranked([{"confidence": 1.0, "why": "ID in the text"}, {"confidence": 1.0, "why": ""}])
    assert [(m["rank"], m["why"]) for m in tie] == [(1, "ID in the text"), (2, "")]
