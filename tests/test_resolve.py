"""Test all input types are accepted, the correct data is extracted and converted to the correct type:string """

from fake_data import AIR, COW, SOIL

import verdy
from verdy.resolve import kind, resolve


def test_ids_are_looked_up_in_ena_and_the_ontologies(services):
    assert [kind(x) for x in (AIR, "ERS1794916", "ERR2012938", "PRJEB21441", "ENVO:00000045", "air")] == \
        ["sample", "sample", "run", "project", "name", "name"]
    assert resolve(AIR) == [("scientific_name", "air metagenome"), ("broad_scale_environmental_context", "urban biome"),
                            ("local_environmental_context", "city"), ("environmental_medium", "air"),
                            ("environment_biome", "urban biome"), ("environment_feature", "city"),
                            ("environment_material", "air")]
    assert ("host_scientific_name", "Not applicable") not in resolve(AIR)
    assert resolve("ERR2012938") == resolve(AIR)
    assert resolve("air temperature") == [("name", "air temperature")]
    assert resolve("SAMD999") == []


def test_ena_is_asked_in_bulk_with_the_sample_context(services):
    found = verdy.samples([AIR, "SRS5634417", "SAMD999", "ERR2012938", "ERP023684", "Estuaries"])
    assert services.count("ena_search") == 4   # samples and runs' samples in one; runs in one; studies in one; the project in one
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
