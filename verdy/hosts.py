"""A sample's host as an NCBITaxon class with its ancestors, all from OLS4.

    host({"host_tax_id": "9913"})  -> {"id": "NCBITaxon:9913", "label": "Bos taurus",
                                       "ancestors": ["Bos", "Bovidae", ..., "Mammalia", ...],
                                       "ancestor_ids": ["NCBITaxon:9903", ..., "NCBITaxon:40674", ...],
                                       "from": "host_tax_id"}
    host({"host": "cow"})          -> the same, found by its synonym "cow"

The host is read from ``host_tax_id`` first, then ``host_scientific_name``, then ``host``: a
name is found by OLS4's exact search on NCBITaxon labels and synonyms (which hold the common
names: cow, honey bee, human). Ancestors come unordered; labels lose OLS4's tags
('Theria <mammals>' is 'Theria'). Every answer is cached.
"""

from __future__ import annotations

import re

from verdy import sources
from verdy.sources import Cache, by_id

HOST_FIELDS = ("host_tax_id", "host_scientific_name", "host")


def _name(label: str) -> str:
    return re.sub(r"\s*<[^>]*>$", "", label or "").strip()


def _ancestors(iri: str) -> list[dict] | None:
    """[{id, label}] of every ancestor, unordered."""
    def fetch():
        found = sources.ols_ancestors("ncbitaxon", iri)
        return found if found is None else [{"id": a["id"], "label": _name(a["label"])} for a in found if a["label"]]
    return Cache("taxon_ancestors").get(iri, fetch)


def named(name: str) -> list[str] | None:
    """The NCBITaxon IDs whose label or synonym is ``name``, OLS4's best first ("Fish": three classes)."""
    def fetch():
        docs = sources.ols_search(name, "ncbitaxon", True, "obo_id,label", queryFields="label,synonym")
        return docs if docs is None else [x["obo_id"] for x in docs if x.get("obo_id")]
    return Cache("taxon_named").get(name.lower(), fetch)


def _by_name(name: str) -> str | None:
    return next(iter(named(name) or []), None)


def taxon(ontology_id: str) -> dict | None:
    """{id, label, ancestors (labels), ancestor_ids} of an NCBITaxon class; None when OLS4 does not
    know it or did not answer. Compare by ``ancestor_ids``: labels vary, IDs don't."""
    found = by_id(ontology_id)
    if not found:
        return None
    ancestors = _ancestors(found["id"])
    if ancestors is None:
        return None
    return {"id": ontology_id, "label": _name(found["label"]), "ancestors": [a["label"] for a in ancestors],
            "ancestor_ids": [a["id"] for a in ancestors if a["id"]]}


def host(fields: dict) -> dict | None:
    """The host of a sample, from its fields (``{field: value}``): {id, label, ancestors, from}, or None."""
    for f in HOST_FIELDS:
        value = str(fields.get(f) or "").strip()
        if not value:
            continue
        if f == "host_tax_id":
            oid = f"NCBITaxon:{value}" if value.isdigit() else None
        else:
            oid = _by_name(value)
        found = taxon(oid) if oid else None
        if found:
            return {**found, "from": f}
    return None
