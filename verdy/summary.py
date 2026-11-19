"""One GOLD path and one ENVO class per sample, from everything the sample says together.

A sample's terms are matched one by one (verdy.match); here they are read together, with the
sample's context (title, descriptions, study title) and its host (verdy.hosts), to choose:

GOLD   every path is scored level by level, not by its last step (the names of a level are
       GOLD's word and those of the classes GOLD links it to, see verdy.gold):
       * the level that names the host must contain the sample's host, or the path is out;
       * its last level must be in the sample's own words;
       * Host-associated needs a host, or a name never used under Environmental; Engineered
         needs the kind of engineering (the level under it: Lab enrichment, Wastewater, ...) by
         a name used only there, or a level whose ENVO class is under an anthropogenic one;
       * the path the sample supports most wins: words saying what was sampled (medium,
         isolation source, local context, body site) weigh most, the study title least; then
         the more specific host, the longer name, the fewer words of its name the sample
         doesn't say. When the host is unknown and several hosts fit (feces, no host), or
         paths still tie, the class they share is given, as a broadMatch.
ENVO   the class naming the host and the material together ("cow dung"), else a confident
       match of the sample's terms that GOLD's chosen path links to, else by field (medium,
       isolation source, local context, ...), never a biome for a host's sample; failing those,
       the medium GOLD's path links to.

Every name, host and link comes from the ontologies through OLS4; nothing is written by hand.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import quote

from verdy import gold as gold_model
from verdy import hosts, sources
from verdy.constants import ECOLOGICAL, OBO, OLS
from verdy.sources import Cache, by_id, counted, query_text, search, singular

HOST, ENGINEERED, ENVIRONMENTAL = "Host-associated", "Engineered", "Environmental"
STRONG, MATERIAL, WEAK = 1.0, 1.5, 0.5         # the sample's words; what was sampled; its study's title
SHARED_CONFIDENCE = 0.6
CONFIDENT = 0.8                                # an ENVO match below this (and not exact or close) is not used
MATERIAL_FIELDS = ("environmental_medium", "environment_material", "isolation_source", "local_environmental_context",
                   "environment_feature", "host_body_site", "tissue_type")
ENVO_ORDER = ("environmental_medium", "environment_material", "isolation_source", "local_environmental_context",
              "environment_feature", "host_body_site", "tissue_type", "broad_scale_environmental_context",
              "environment_biome")
BROAD = {"broad_scale_environmental_context", "environment_biome"}
TEXT_FIELDS = ("sample_title", "sample_description", "description")


def phrase(text: str) -> str:
    """Lower case, without typed IDs or punctuation, each word singular."""
    return " ".join(singular(w) for w in re.findall(r"[a-z0-9]+", query_text(text or "").lower()))


def _text(parts) -> str:
    """Phrases joined so that no phrase runs across two of them."""
    return " " + " | ".join(p for p in (phrase(x) for x in parts if x) if p) + " "


def _has(p: str, text: str) -> bool:
    return f" {p} " in text


def _top(items, key):
    best = max(key(x) for x in items)
    return [x for x in items if key(x) == best]


def _anthropogenic(ontology_id: str) -> bool | None:
    """Whether ENVO places the class under an anthropogenic one (activated sludge: yes; sea water: no)."""
    iri = OBO + ontology_id.replace(":", "_")

    def fetch():
        d = sources._json(f"{OLS}/ontologies/envo/terms/{quote(quote(iri, safe=''), safe='')}/hierarchicalAncestors",
                          size=500)
        return d if d is None else [t.get("label") or "" for t in (d.get("_embedded") or {}).get("terms") or []]
    labels = Cache("envo_ancestors").get(ontology_id, fetch)
    return None if labels is None else any("anthropogenic" in a for a in labels)


class Chooser:
    """GOLD's paths as phrases, for choosing one per sample."""

    def __init__(self, g, workers: int = 6, progress=None):
        self.g = g
        self.paths = g.paths
        self.levels = [p["levels"] for p in self.paths]
        self.phrases: dict[tuple, set[str]] = {}
        for p in self.paths:
            for lvl in p["levels"]:
                key = (p["root"], lvl)
                if key not in self.phrases:
                    own = {phrase(lvl)} | ({phrase(x) for x in lvl.split("/")} if " " not in lvl else set())
                    self.phrases[key] = (own | {phrase(n) for n in g.names.get(key, ())}) - {""}
        # What a root needs, by what its levels are called (any name, so Engineered's "Feces" and the
        # hosts' "Fecal" are one thing): Host-associated, a name never under Environmental; Engineered,
        # one only under it -- its deeper levels copy nature ("Modeled > ... > Sea water").
        under: dict[str, set[str]] = defaultdict(set)
        for (root, _), names in self.phrases.items():
            under[root] |= names
        self.evidence_for = {ENGINEERED: under[ENGINEERED] - under[HOST] - under[ENVIRONMENTAL],
                             HOST: under[HOST] - under[ENVIRONMENTAL]}
        # "sea" inside "sea water": the longer known name is what the text says.
        known = {x for names in self.phrases.values() for x in names}
        by_word: dict[str, list[str]] = defaultdict(list)
        for x in known:
            for w in set(x.split()):
                by_word[w].append(x)
        self.longer = {x: [y for y in by_word[x.split()[0]] if y != x and f" {x} " in f" {y} "] for x in known}
        self.by_word: dict[str, set[int]] = defaultdict(set)
        for i, p in enumerate(self.paths):
            for x in self.phrases[(p["root"], p["levels"][-1])]:
                self.by_word[x.split()[0]].add(i)
        self.hosted = {i for i, p in enumerate(self.paths) if p["host_level"] is not None}
        self.index = {p["id"]: i for i, p in enumerate(self.paths)}
        self.by_label = {p["label"]: p for p in self.paths}
        self.matched_by: dict[str, set[int]] = defaultdict(set)      # ENVO class -> paths curated as its match
        for i, p in enumerate(self.paths):
            for oid in p["links"]["has exact match"] + p["links"]["has close match"]:
                self.matched_by[oid].add(i)
        engineered = sorted({oid for (root, _), oids in g.owned.items() if root == ENGINEERED
                             for oid in oids if oid.startswith("ENVO:")})
        made = {oid for oid, yes in zip(engineered, counted(_anthropogenic, engineered, workers,
                                                            gold_model.STAGE, progress)) if yes}
        self.man_made = {key for key, oids in g.owned.items() if key[0] == ENGINEERED and oids & made}
        self._depth: dict[str, int] = {}

    def depth(self, taxon_id: str) -> int:
        """How specific a taxon is: its number of ancestors."""
        if taxon_id not in self._depth:
            t = hosts.taxon(taxon_id)
            self._depth[taxon_id] = len(t["ancestor_ids"]) if t else 0
        return self._depth[taxon_id]

    def _in(self, p: str, text: str, own: set[str] = frozenset()) -> bool:
        """``p`` is in the text, and not only inside a longer name of another path's level."""
        return _has(p, text) and not any(_has(y, text) for y in self.longer.get(p, ()) if y not in own)

    def _level(self, path: dict, depth: int, strong: str, weak: str, host: dict | None, material: str, own: set[str]):
        """(weight, host specificity) of one level, or None when the sample contradicts it."""
        root, lvl = path["root"], path["levels"][depth]
        if depth == path["host_level"] and host:
            under = {host["id"], *host.get("ancestor_ids", [])}
            fits = [t for t in path["host_taxa"] if t in under]
            return (STRONG, max(map(self.depth, fits))) if fits else None
        if depth == 0 and root == HOST and host:
            return STRONG, 0
        names = self.phrases[(root, lvl)]
        if material and any(self._in(p, material, own) for p in names):
            return MATERIAL, 0
        if any(self._in(p, strong, own) for p in names):
            return STRONG, 0
        if any(self._in(p, weak, own) for p in names):
            return WEAK, 0
        return 0.0, 0

    def _root_evidence(self, path: dict, depth: int, strong: str, own: set[str]) -> bool:
        root, lvl = path["root"], path["levels"][depth]
        if root == HOST and depth == path["host_level"]:
            return True
        if root == ENGINEERED and (root, lvl) in self.man_made:
            return True
        if root == ENGINEERED and depth != 1:
            return False
        return any(p in self.evidence_for[root] and self._in(p, strong, own) for p in self.phrases[(root, lvl)])

    def score(self, i: int, strong: str, weak: str, host: dict | None, material: str, given: bool) -> dict | None:
        path = self.paths[i]
        levels, root = path["levels"], path["root"]
        own = set().union(*(self.phrases[(root, lvl)] for lvl in levels))       # names along this path
        got = []
        for depth in range(len(levels)):
            v = self._level(path, depth, strong, weak, host, material, own)
            if v is None:
                return None                       # the host is not one this path allows
            got.append(v)
        if got[-1][0] == 0 and not given:
            return None                           # its last level must be the sample's own
        # One word supports one level: "gut" names Gut, and Digestive system above it only by implication.
        used, implied = set(), set()
        for depth in range(len(levels) - 1, -1, -1):
            if host and (depth == path["host_level"] or depth == 0):
                continue
            said_here = {p for p in self.phrases[(root, levels[depth])] if self._in(p, strong, own)}
            if said_here and said_here <= used:
                implied.add(depth)
                got[depth] = (0.0, got[depth][1])
            used |= said_here
        if root in (HOST, ENGINEERED) and got[0][0] == 0 and not any(
                w and self._root_evidence(path, depth, strong, own) for depth, (w, _) in enumerate(got)):
            return None                           # no host, nothing engineered: not under those roots
        hl = path["host_level"]
        return {"i": i, "score": sum(w for w, _ in got) + (STRONG if given and got[-1][0] < STRONG else 0),
                "spec": max(s for _, s in got), "hosted": hl is not None,
                "said": hl is not None and got[hl][0] > 0,                          # "human gut": the text names it
                "words": max((len(p.split()) for p in self.phrases[(root, levels[-1])] if self._in(p, strong, own)),
                             default=0),
                "unsaid": sum(1 for w in phrase(levels[-1]).split() if f" {w} " not in strong),
                "unsupported": sum(1 for d, (w, _) in enumerate(got) if w == 0 and d not in implied),
                "crosswalk": given and got[-1][0] == 0,
                "evidence": [lvl for lvl, (w, _) in zip(levels, got) if w]}

    def best(self, strong: str, weak: str, host: dict | None, material: str = "", given=(),
             free_living: bool = False) -> dict | None:
        """The GOLD path the sample fits best, or the one the paths that fit equally share.
        ``free_living``: the sample's organism is an ecological metagenome (soil, seawater), so
        without a host it is not under Host-associated, whatever its free text mentions."""
        cands = set().union(*(self.by_word.get(w, set()) for w in set(strong.split())))
        if host:
            cands |= self.hosted
        given = {self.index[g] for g in given if g in self.index}
        if free_living and not host:
            cands = {i for i in cands if self.paths[i]["root"] != HOST}
            given = {i for i in given if self.paths[i]["root"] != HOST}
        scored = [s for s in (self.score(i, strong, weak, host, material, i in given) for i in cands | given) if s]
        if not scored:
            return None
        if host is None and any(s["said"] for s in scored):
            scored = [s for s in scored if s["said"] or not s["hosted"]]     # "human gut": not a mollusc's
        top = _top(scored, lambda s: s["score"])
        top = _top(top, lambda s: s["spec"])
        top = _top(top, lambda s: s["words"])         # "hot spring": Thermal springs, not Spring
        top = _top(top, lambda s: -s["unsaid"])       # feces: Fecal, not its sibling Cow Dung (both UBERON feces)
        if host is None and len({tuple(self.paths[s["i"]]["host_taxa"]) for s in top}) > 1:
            return self._shared(top, "the host is not given and several fit")
        top = _top(top, lambda s: -s["unsupported"])
        if len(top) > 1:
            return self._shared(top, "several fit equally")
        s = top[0]
        p = self.paths[s["i"]]
        conf = round(0.75 + 0.2 * min(1.0, s["score"] / max(1, len(p["levels"]) - 1)), 2)
        return {**_row(p), "match_type": "skos:closeMatch", "confidence": conf,
                "method": "crosswalk" if s["crosswalk"] else "ontology name",
                "why": "fits: " + ", ".join(s["evidence"])}

    def _shared(self, top: list[dict], why: str) -> dict | None:
        prefix = []
        for parts in zip(*(self.paths[s["i"]]["levels"] for s in top)):
            if len(set(parts)) > 1:
                break
            prefix.append(parts[0])
        while prefix and " > ".join(prefix) not in self.by_label:
            prefix.pop()
        if not prefix:
            return None
        options = "; ".join(sorted({self.paths[s["i"]]["label"] for s in top})[:5])
        # The paths that fit may agree on what was sampled (all Fecal: feces) though not on the host.
        media = {tuple(self.paths[s["i"]]["links"]["env_medium"]) for s in top}
        return {**_row(self.by_label[" > ".join(prefix)]), "match_type": "skos:broadMatch",
                "confidence": SHARED_CONFIDENCE, "method": "shared parent", "why": f"{why}: {options}",
                "medium": media.pop()[:1] if len(media) == 1 else ()}


def _row(path: dict) -> dict:
    return {"ontology": "GOLD", "match_id": path["iri"], "match_curie": path["id"], "match_label": path["label"]}


def _confident(m: dict) -> bool:
    return m["match_type"] in ("skos:exactMatch", "skos:closeMatch") or (m["confidence"] or 0) >= CONFIDENT


def best_envo(envo: list[dict], host_hit: dict | None, g: dict | None, chooser: Chooser | None) -> dict | None:
    """``envo``: the sample's ENVO matches (each with its ``category``, the field(s) it came from)."""
    path = chooser.by_label.get(g["match_label"]) if g and chooser else None
    linked = {oid for oids in (path or {}).get("links", {}).values() for oid in oids}
    from_host = bool(g) and g["match_label"].startswith(HOST)
    cands = [((0, 0, 0, 0), host_hit, "names the host and the material")] if host_hit else []
    for m in envo:
        fields = [f for f in (m.get("category") or "").split("|") if f in ENVO_ORDER]
        if not fields or not _confident(m) or (from_host and set(fields) <= BROAD):
            continue                  # not an environment field (the organism's name), a weak match, or a biome for a host's sample
        agrees = m["match_curie"] in linked
        order = min((ENVO_ORDER.index(f) for f in fields if f in ENVO_ORDER), default=len(ENVO_ORDER))
        cands.append(((1, 0 if agrees else 1, order, -(m["confidence"] or 0)), m,
                      f"from {m.get('category')}" + (" (GOLD's path links it)" if agrees else "")))
    if cands:
        _, m, why = min(cands, key=lambda c: c[0])
        return {k: m[k] for k in ("ontology", "match_id", "match_curie", "match_label", "match_type", "confidence")} | {
            "method": m.get("method") or "ontology name", "why": why}
    medium = next(iter((path or {}).get("links", {}).get("env_medium") or (g or {}).get("medium") or []), None)
    found = by_id(medium) if medium else None
    if found:
        return {"ontology": medium.split(":")[0], "match_id": found["id"], "match_curie": medium,
                "match_label": found["label"], "match_type": "skos:closeMatch", "confidence": 0.75,
                "method": "GOLD medium",
                "why": f"the medium of GOLD's {g['match_label']}" if path and path["links"]["env_medium"]
                else f"the medium all the GOLD paths that fit share ({g['why']})"}
    return None




def _free_living(organism: str | None) -> bool:
    """Whether NCBITaxon places the sample's organism under ecological metagenomes."""
    oid = hosts._by_name(organism) if organism else None
    t = hosts.taxon(oid) if oid else None
    return bool(t) and ECOLOGICAL in t["ancestor_ids"]


def _host_hit(values: dict, host: dict | None) -> dict | None:
    """An ENVO class whose name is the host and the material together ("cow dung"), by exact search."""
    if not host:
        return None
    material = next((values[f][0] for f in ("environmental_medium", "isolation_source") if values.get(f)), "")
    name = (values.get("host") or [host["label"]])[0]
    if not material or phrase(name) in phrase(material):
        return None
    for c in search(f"{name} {query_text(material)}", "envo", top=3) or []:
        if c["exact"]:
            return {"ontology": "ENVO", "match_id": c["id"], "match_curie": c["curie"], "match_label": c["label"],
                    "match_type": "skos:exactMatch", "confidence": 1.0 if c["same"] else 0.95}
    return None


def _best_of(ms: list[dict]) -> dict | None:
    """The sample's best match in an ontology other than GOLD and ENVO: the most confident, a typed ID on a tie."""
    if not ms:
        return None
    m = min(ms, key=lambda m: (-(m["confidence"] or 0), m["method"] != "ID"))
    return {k: m[k] for k in ("ontology", "match_id", "match_curie", "match_label", "match_type", "confidence",
                              "method")} | {"why": f"from {m.get('category')}: {m['why']}"}


def summarise(terms: list[dict], matches: list[dict], ontologies, workers: int = 6, progress=None) -> list[dict]:
    """One row per sample (the terms that came from ENA), with ``matches``: {ontology: its one match
    or None} for each of ``ontologies``, each with its match type, confidence, method and why. GOLD and
    ENVO are chosen from the whole sample (above); any other ontology gives the sample's best match in it."""
    chosen = list(dict.fromkeys(o.lower() for o in ontologies))
    by_sample: dict[str, list[dict]] = {}
    for t in terms:
        if "context" in t:
            by_sample.setdefault(t["id"], []).append(t)
    if not by_sample:
        return []
    others: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for m in matches:
        if m["term_id"] in by_sample and m["ontology"].lower() in chosen:
            others[(m["term_id"], m["ontology"].lower())].append(m)
    chooser = Chooser(gold_model.load(workers, progress), workers, progress) if "gold" in chosen else None
    envo_of: dict[str, list[dict]] = defaultdict(list)
    for m in matches:                    # from the environment fields, not the organism's name
        if m["ontology"] == "ENVO" and m["term_id"] in by_sample and \
                set((m.get("category") or "").split("|")) & set(ENVO_ORDER):
            envo_of[m["term_id"]].append(m)

    out, memo = [], {}
    for n, (sample, ts) in enumerate(by_sample.items(), 1):
        if progress:
            progress("Choosing one match per sample", n, len(by_sample))
        ctx = ts[0]["context"]
        values: dict[str, list[str]] = defaultdict(list)
        for t in ts:
            for f in (t.get("category") or "").split("|"):
                values[f].append(t["label"])
        host = ctx.get("host_taxon")
        envo = envo_of.get(sample, [])
        sure = [m["match_label"] for m in envo if _confident(m)]
        organism = (values.get("scientific_name") or [None])[0]
        free_living = bool(chooser) and _free_living(organism)
        strong = _text([v for vs in values.values() for v in vs] + [ctx.get(f) for f in TEXT_FIELDS] + sure)
        # An ecological metagenome's name says what was sampled ("activated sludge metagenome").
        material = _text([v for f in MATERIAL_FIELDS for v in values.get(f, [])] + ([organism] if free_living else [])
                         + [m["match_label"] for m in envo if _confident(m)
                            and not set((m.get("category") or "").split("|")) <= BROAD])
        weak = _text([ctx.get("study_title")])
        # The host's own names place it by its taxon, not as words: "honey bee" says nothing of Honey.
        for name in {phrase(x) for x in [*(values.get("host") or []), *(values.get("host_scientific_name") or []),
                                         (host or {}).get("label")] if x} - {""}:
            strong, material = (x.replace(f" {name} ", " | ") for x in (strong, material))
        given = tuple(sorted({chooser.paths[i]["id"] for m in envo if _confident(m)
                              for i in chooser.matched_by.get(m["match_curie"], ())})) if chooser else ()
        g = None
        if chooser:
            key = (strong, weak, material, (host or {}).get("id"), given, free_living)
            if key not in memo:
                memo[key] = chooser.best(strong, weak, host, material, given, free_living)
            g = memo[key]
        e = best_envo(envo, _host_hit(values, host), g, chooser) if "envo" in chosen else None
        chosen_here = {o: g if o == "gold" else e if o == "envo" else _best_of(others.get((sample, o), []))
                       for o in chosen}
        out.append({"sample": sample, "input": ts[0].get("input", sample), "study": ctx.get("study"),
                    "study_title": ctx.get("study_title"), "host": (host or {}).get("label"),
                    "evidence": " · ".join(dict.fromkeys(t["label"] for t in ts)), "matches": chosen_here})
    return out
