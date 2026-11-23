"""A sample's host as an NCBITaxon class with its ancestors."""

from fake_data import AIR, COW

import verdy


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
    assert all(c.startswith("ols_") for c in services)                              # OLS4 only

    terms, _ = verdy.resolve_terms([{"id": "x", "label": COW}, {"id": "y", "label": "PRJEB21441"}])
    feces = next(t for t in terms if t["label"] == "Cow feces")
    assert feces["context"]["host_taxon"]["label"] == "Bos taurus"
    assert not any("host_taxon" in t["context"] for t in terms if t["id"] == AIR)      # 'Not applicable': no host
