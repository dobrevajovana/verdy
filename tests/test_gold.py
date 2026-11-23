"""GOLD ecosystem paths: what each level is called, which host a path needs, and one path per sample."""

from fake_data import CAT, COW, SLUDGE

import verdy
from verdy import gold


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
