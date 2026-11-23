"""GOLD ecosystem paths from OLS4, with what each level is called and which host it needs.

GOLD classifies where a sample comes from as a path of up to five levels:

    Host-associated > Mammals > Digestive system > Large intestine > Fecal
    Engineered > Lab enrichment > Feces

OLS4's GOLD gives every path its links to other ontologies (``LINKS``): its environment
(env_broad, env_local, env_medium: ENVO, or UBERON for body materials), its body site
(anatomical_site), its curated exact and close matches, and for Host-associated paths its
host (host_taxon, an NCBITaxon class). From them:

* names: what each level is also called. A linked class's label and synonyms name the level
  where the link first appears on the path: "...> Fecal" links UBERON feces (faeces, stool,
  dung, ...), so they name Fecal; its parent "...> Large intestine" already links UBERON
  large intestine, so that names Large intestine, not Fecal.
* host taxa: the NCBITaxon classes a path's host must be under. GOLD's own host_taxon, and
  the classes the host level's name stands for in NCBITaxon ("Fish" is three classes where
  GOLD gives one); a Host-associated path with none says nothing about its host.

Nothing here is written by hand: every name and taxon comes from GOLD and the ontologies it
links to, through OLS4, and is cached.
"""

from __future__ import annotations

import threading

from verdy import hosts, sources
from verdy.constants import GOLD_PATH
from verdy.sources import Cache, by_id, canon, counted, score

LINKS = ("env_broad", "env_local", "env_medium", "anatomical_site", "has exact match", "has close match")
HOST = "Host-associated"
STAGE = "Reading GOLD"

_model: Gold | None = None
_lock = threading.Lock()


def _terms() -> list[dict]:
    """Every GOLD class in OLS4, 500 to a request."""
    def fetch():
        found = sources.ols_all_terms("gold")
        return found if found is None else [{"iri": t["iri"], "label": t.get("label") or "",
                                             "annotation": t.get("annotation") or {}} for t in found]
    terms = Cache("gold").get("terms", fetch)
    if terms is None:
        raise RuntimeError("OLS4 did not answer for GOLD; try again later.")
    return terms


class Gold:
    """``paths``: [{id, iri, label, levels, root, links: {kind: [ontology ID]}, host_taxon (GOLD's own),
    host_taxa (what a host must be under), host_level (the index of the level that names the host)}];
    ``names``: {(root, level): [names]}; ``owned``: {(root, level): {the ontology IDs that name it}}."""

    def __init__(self, terms: list[dict], workers: int = 6, progress=None):
        self.paths = []
        for t in terms:
            if not t["iri"].startswith(GOLD_PATH):
                continue
            levels = [x.strip() for x in t["label"].split(">")]
            ann = t["annotation"]
            self.paths.append({"id": canon(t["iri"]), "iri": t["iri"], "label": " > ".join(levels), "levels": levels,
                               "root": levels[0], "links": {k: [canon(x) for x in ann.get(k) or []] for k in LINKS},
                               "host_taxon": [canon(x) for x in ann.get("host_taxon") or []], "host_taxa": [],
                               "host_level": None})
        self.by_label = {p["label"]: p for p in self.paths}
        self._owners()
        self._name_levels(workers, progress)
        self._host_taxa()

    def lineage(self, path: dict) -> list[dict]:
        """The path and the paths above it, shallowest first."""
        return [self.by_label[" > ".join(path["levels"][:i])] for i in range(1, len(path["levels"]) + 1)
                if " > ".join(path["levels"][:i]) in self.by_label]

    def _owners(self) -> None:
        """{(root, level): {linked ontology IDs}}: a link names the level where it first appears on the path."""
        self.owned: dict[tuple[str, str], set[str]] = {}
        for p in self.paths:
            for kind in LINKS:
                for oid in p["links"][kind]:
                    first = next(q for q in self.lineage(p) if oid in q["links"][kind])
                    self.owned.setdefault((p["root"], first["levels"][-1]), set()).add(oid)

    def _name_levels(self, workers: int, progress=None) -> None:
        ids = sorted({oid for oids in self.owned.values() for oid in oids if ":" in oid})
        found = dict(zip(ids, counted(by_id, ids, workers, STAGE, progress)))
        self.names: dict[tuple[str, str], list[str]] = {}
        for p in self.paths:
            key = (p["root"], p["levels"][-1])
            names = self.names.setdefault(key, [p["levels"][-1]])
            for oid in self.owned.get(key, ()):
                c = found.get(oid) or {}
                for n in [c.get("label"), *(c.get("synonyms") or [])]:
                    if n and n not in names:
                        names.append(n)

    def _host_taxa(self) -> None:
        """Each Host-associated path's host taxa: GOLD's own, or the nearest path above's, plus what the name
        of the level where that taxon first appears stands for in NCBITaxon ("Fish" for "Fish > Skin").
        Unstated: what the depth-1 level's name stands for."""
        level_taxa = {}
        for p in self.paths:
            if p["root"] != HOST:
                continue
            line = self.lineage(p)
            stated = next((q for q in reversed(line) if q["host_taxon"]), None)
            if stated:
                stated = next(q for q in line if q["host_taxon"] == stated["host_taxon"])
            at = len(stated["levels"]) - 1 if stated else (1 if len(p["levels"]) > 1 else None)
            level = p["levels"][at] if at is not None else None
            if level and level not in level_taxa:
                level_taxa[level] = hosts.named(level) or []
            p["host_taxa"] = list(dict.fromkeys([*(stated or {}).get("host_taxon", []), *level_taxa.get(level, [])]))
            p["host_level"] = at if p["host_taxa"] else None

    def host_fits(self, path: dict, host: dict | None) -> bool | None:
        """Whether ``host`` (from ``verdy.host``) is under the path's host taxa; None when the path names none."""
        if not path["host_taxa"]:
            return None
        if not host:
            return False
        return bool(set(path["host_taxa"]) & {host["id"], *host.get("ancestor_ids", [])})

    def search(self, name: str) -> list[dict]:
        """Candidates for the term ``name``: the paths whose last level it names, by GOLD's word or a
        linked class's label or synonym. Shallower paths first among equals."""
        out = []
        for p in sorted(self.paths, key=lambda p: len(p["levels"])):
            names = self.names.get((p["root"], p["levels"][-1])) or [p["levels"][-1]]
            s, exact, same = score(name, names)
            if s > 0:
                out.append({"id": p["iri"], "curie": p["id"], "label": p["label"], "synonyms": names[1:6],
                            "score": round(s, 3), "exact": exact, "same": same, "definition": None})
        return out


def load(workers: int = 6, progress=None) -> Gold:
    """The GOLD model, built once per run (every request behind it is cached); ``progress(stage, done,
    total)`` counts the linked classes whose names are read."""
    global _model
    with _lock:
        if _model is None:
            if progress:
                progress(STAGE, None, None)
            _model = Gold(_terms(), workers, progress)
    return _model
