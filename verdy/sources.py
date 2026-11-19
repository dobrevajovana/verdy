"""The ontologies, and how a term is searched in each for candidates (ontology classes).

Ontologies are chosen by name. The ready ones are in ``ONTOLOGIES``; any other OLS4
ontology name works too (https://www.ebi.ac.uk/ols4/ontologies).

* OLS4 ontologies (ENVO, NCBITaxon, PATO, OBA, UO, ...): OLS4's exact search on the term as
  written, then its word searches on the term, its singular form and its key words (OLS4
  only returns classes holding every word of a query).
* ``gbif``: the GBIF Backbone's name matcher.
* ``wikidata``: Wikidata's item search.
* ``natura2000``: the Natura 2000 habitat types and species of the EEA's Article 17 report
  (2019-2024), fetched from its public service once and searched locally; by name, or by
  code ('1330 Atlantic salt meadows').
* ``cf``: the CF Standard Names table (climate and forecast variables), read once and
  searched locally.

Every answer is cached on disk (``VERDY_CACHE``, default ``~/.cache/verdy``), so a
second run on the same terms makes no requests.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from verdy.constants import ART17, CF_TABLE, GBIF_MATCH, OLS, WIKIDATA_API

logger = logging.getLogger("verdy")

CACHE = Path(os.environ.get("VERDY_CACHE", Path.home() / ".cache" / "verdy"))
UA = {"User-Agent": "verdy/0.1 (ontology matcher)"}

ONTOLOGIES = {
    # environments, habitats, samples
    "envo": "ENVO: environments, habitats, environmental materials",
    "natura2000": "Natura 2000 habitat types and species (EEA Article 17 lists)",
    "gold": "GOLD ecosystem classification",
    # organisms
    "ncbitaxon": "NCBI Taxonomy",
    "gbif": "GBIF Backbone Taxonomy",
    # parameters and measurements
    "pato": "PATO: qualities (temperature, salinity, colour, ...)",
    "oba": "OBA: biological attributes and traits",
    "cf": "CF Standard Names: climate and forecast variables",
    "uo": "UO: units of measurement",
    "chebi": "ChEBI: chemical entities",
    "obi": "OBI: investigations, assays, instruments",
    # anatomy, plants, processes
    "uberon": "Uberon: anatomy",
    "po": "Plant Ontology",
    "go": "Gene Ontology",
    # general
    "wikidata": "Wikidata",
}
NATURA = "natura2000"
SHORT = {NATURA: "Natura2000", "gbif": "GBIF", "wikidata": "Wikidata", "ncbitaxon": "NCBITaxon", "cf": "CF"}
TAXONOMIES = {"ncbitaxon", "gbif"}      # a near name there is another taxon: exact matches only
LOCAL = {"gbif", "wikidata", "cf", NATURA}

_STOP = {"the", "and", "with", "of", "in", "on", "or", "by", "for", "to", "a", "an", "which", "are", "is", "sp", "spp",
         "cf", "aff", "type", "types", "other", "including", "mainly", "where", "at", "per", "from"}


# --- cache and requests ----------------------------------------------------------

class Cache:
    """One JSON file per source; a failed lookup (None) is not kept, so it is tried again.
    Every Cache of one file shares its data, so threads writing at once don't lose each other's answers."""
    _locks: dict[str, threading.Lock] = {}
    _data: dict[str, dict] = {}

    def __init__(self, name: str):
        self.path = CACHE / f"{name}.json"
        key = str(self.path)
        self.lock = Cache._locks.setdefault(key, threading.Lock())
        with self.lock:
            if key not in Cache._data:
                try:
                    Cache._data[key] = json.loads(self.path.read_text())
                except (OSError, ValueError):
                    Cache._data[key] = {}
        self.data = Cache._data[key]

    def get(self, key, fetch):
        if key in self.data:
            return self.data[key]
        value = fetch()
        if value is None:
            return None
        self.put({key: value})
        return value

    def put(self, items: dict) -> None:
        """Keep several answers, written once."""
        with self.lock:
            self.data.update(items)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(self.data))
            tmp.replace(self.path)


def _json(url, _post=False, **params):
    """GET (or POST, for long queries) JSON; {} for 404 or an empty answer, None when the service
    did not answer (after two retries)."""
    for attempt in range(3):
        try:
            r = requests.post(url, data=params, headers=UA, timeout=300) if _post else \
                requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 404 or (r.ok and not r.content.strip()):
                return {}
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                wait = r.headers.get("Retry-After") or ""
                time.sleep(min(10.0, float(wait)) if wait.isdigit() else 2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.Timeout:
            if attempt < 2:
                continue
            logger.warning("No answer from %s", url)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Lookup failed for %s: %s", url, exc)
            return None
    return None


def counted(fn, items: list, workers: int, stage: str, progress=None) -> list:
    """``fn`` over ``items``, ``workers`` at a time, in order; ``progress(stage, done, total)`` as each is done."""
    out = []
    if progress and items:
        progress(stage, 0, len(items))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for x in pool.map(fn, items):
            out.append(x)
            if progress:
                progress(stage, len(out), len(items))
    return out


# --- terms and identifiers --------------------------------------------------------

def canon(identifier) -> str:
    """An ontology class's IRI as its ontology ID (ENVO:00001998), so both compare equal."""
    o = str(identifier or "").strip()
    if m := re.search(r"/obo/([A-Za-z][A-Za-z0-9]*)_(\w+)$", o):
        return f"{m.group(1)}:{m.group(2)}"
    if m := re.search(r"gbif\.org/species/(\d+)", o):
        return f"GBIF:{m.group(1)}"
    if m := re.search(r"wikidata\.org/(?:entity|wiki)/(Q\d+)", o):
        return f"wikidata:{m.group(1)}"
    if m := re.search(r"w3id\.org/gold\.(path|vocab)/([\w.-]+)", o):
        return f"{'GOLD.path' if m.group(1) == 'path' else 'GOLD'}:{m.group(2)}"
    if m := re.search(r"vocab\.nerc\.ac\.uk/standard_name/([\w-]+)", o):
        return f"CF:{m.group(1)}"
    return o


# A typed ID, an ontology ID written in a term: "soil [ENVO:00001998]", "ENVO_00002149", "marine biome ENVO: 00000447".
ONTOLOGY_ID = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)[:_]\s?(\d{4,8})\b")


def ids_in(text) -> list[tuple[str, str]]:
    """The ontology IDs typed in ``text``, as (prefix, number) pairs, in order and once each."""
    return list(dict.fromkeys(ONTOLOGY_ID.findall(str(text or ""))))


def query_text(label: str) -> str:
    """The term as searched (``searched_for``): without a leading code ('1330 Atlantic salt meadows'),
    a bracketed note such as a unit ('air temperature [K]'), a typed ID ('soil ENVO:00001998') or
    underscores ('air_temperature')."""
    t = re.sub(r"^\d{3,}[0-9A-Z]*\s+\*?\s*(?=[A-Za-z])", "", str(label or "")).strip()
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", t)
    t = ONTOLOGY_ID.sub(" ", t)
    t = t.replace("_", " ")
    return re.sub(r"\s+", " ", t).strip(" ,;")


def singular(word: str) -> str:
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "ches", "shes", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def words(text) -> set[str]:
    return {singular(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if w not in _STOP and len(w) > 1}


def _norm(text) -> str:
    return re.sub(r"[\s_]+", " ", str(text or "").lower()).strip(" .")


def score(name: str, labels: list[str]) -> tuple[float, bool, bool]:
    """How well the best of a candidate's labels fits the term ``name`` (word overlap, 0..1); whether
    one has the same words (plurals and 'sp.' aside); whether one is the term as written."""
    nw = words(name)
    # an abbreviation ('AIR' for a chemical) counts only when the term is written the same way
    labels = [lab for lab in labels if lab and not (lab.isupper() and len(lab) <= 8 and lab != name.strip())]
    # each label also without a bracketed part, and a path's last step ('Environmental > Air > Outdoor Air')
    labels = list(dict.fromkeys(v for lab in labels if lab for v in (lab, query_text(lab), lab.split(">")[-1].strip()) if v))
    best, exact, same = 0.0, False, any(_norm(lab) == _norm(name) for lab in labels)
    for lab in labels:
        lw = words(lab)
        if not lw or not nw:
            continue
        if lw == nw:
            best, exact = 1.0, True
        best = max(best, len(nw & lw) / len(nw | lw))
    return best, exact or same, same


def _queries(name: str, taxon: bool) -> list[str]:
    out = [name]
    bare = re.sub(r"\b(spp?|cf|aff)\.?(\s|$)", " ", name).strip()
    if bare and bare != name:
        out.append(bare)
    sing = " ".join(singular(w) for w in name.split())
    if sing.lower() != name.lower():
        out.append(sing)
    if not taxon:
        keys = [singular(w) for w in re.findall(r"[A-Za-z][A-Za-z-]+", name) if w.lower() not in _STOP and len(w) > 2]
        if len(keys) > 2:
            out += [f"{a} {b}" for a, b in zip(keys, keys[1:])][:4]
        if len(keys) > 1:
            out += sorted(set(keys), key=len, reverse=True)[:4]
    seen, uniq = set(), []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq


# --- the sources ------------------------------------------------------------------

def by_id(ontology_id: str) -> dict | None:
    """An ontology class from OLS4 by its ontology ID: {id (the IRI), curie, label, synonyms, definition};
    {} when OLS4 does not know it, None when it did not answer. Its own ontology's entry is preferred
    to the ontologies importing it."""
    prefix = ontology_id.split(":", 1)[0].lower()

    def fetch():
        d = _json(f"{OLS}/terms", obo_id=ontology_id)
        if d is None:
            return None
        docs = (d.get("_embedded") or {}).get("terms") or []
        docs = [x for x in docs if x.get("ontology_name") == prefix] or docs
        if not docs:
            return {}
        x, desc = docs[0], docs[0].get("description")
        return {"id": x.get("iri"), "curie": ontology_id, "label": x.get("label") or ontology_id,
                "synonyms": x.get("synonyms") or [],
                "definition": (desc[0] if isinstance(desc, list) and desc else desc) or None}
    return Cache("terms").get(ontology_id, fetch)


def ontology_info(ontology: str) -> dict | None:
    """Title and short name of a source; None when it is neither ready nor in OLS4."""
    o = ontology.strip().lower()
    if o in LOCAL:
        return {"id": o, "title": ONTOLOGIES[o], "short": SHORT[o]}
    if not re.fullmatch(r"[a-z0-9_.-]{1,40}", o):
        return None

    def fetch():
        d = _json(f"{OLS}/ontologies/{o}")
        return d if not d else {"title": (d.get("config") or {}).get("title"),
                                "prefix": (d.get("config") or {}).get("preferredPrefix")}

    d = Cache("ols_ontologies").get(o, fetch)
    if not d:
        return None
    return {"id": o, "title": d.get("title") or ONTOLOGIES.get(o) or o, "short": SHORT.get(o) or d.get("prefix") or o.upper()}


def _ols(name: str, ontology: str, cache: Cache) -> list[dict] | None:
    taxon = ontology == "ncbitaxon"
    docs, seen, failed = [], set(), False
    for exact, q in [(True, name)] + [(False, q) for q in _queries(name, taxon)]:
        res = cache.get(f"{ontology}|{'=' if exact else ''}{q.lower()}", lambda q=q, exact=exact: _json(
            f"{OLS}/search", q=q, ontology=ontology, type="class", rows=10, exact=str(exact).lower(),
            fieldList="iri,label,obo_id,synonym,description,is_defining_ontology,is_obsolete"))
        if res is None:
            failed = True
            continue
        for d in (res.get("response") or {}).get("docs") or []:
            if d.get("iri") in seen or d.get("is_obsolete"):
                continue
            seen.add(d["iri"])
            docs.append(d)
        if taxon and docs:
            break
    if failed and not docs:
        return None
    if any(d.get("is_defining_ontology") for d in docs):          # its own classes, not imported ones;
        docs = [d for d in docs if d.get("is_defining_ontology")]  # (some, like GOLD, mark none as its own)
    candidates = []
    for d in docs:
        s, exact, same = score(name, [d.get("label") or "", *(d.get("synonym") or [])])
        if s > 0:
            desc = d.get("description")
            candidates.append({"id": d["iri"], "curie": canon(d["iri"]) if "gold" in d["iri"] else d.get("obo_id") or canon(d["iri"]),
                               "label": d.get("label"), "synonyms": (d.get("synonym") or [])[:5],
                               "score": round(s, 3), "exact": exact, "same": same,
                               "definition": (desc[0] if isinstance(desc, list) and desc else desc) or None})
    return candidates


def _gbif(name: str, cache: Cache) -> list[dict] | None:
    name = re.sub(r"\b(spp?|cf|aff)\.?(\s|$)", " ", name).strip()     # GBIF reads 'Elphidium sp.' as the genus
    d = cache.get(name.lower(), lambda: _json(GBIF_MATCH, name=name, verbose="true"))
    if d is None:
        return None
    out = []
    for c in [d, *(d.get("alternatives") or [])]:
        if c.get("usageKey") and c.get("matchType") not in (None, "NONE", "HIGHERRANK"):
            label = c.get("canonicalName") or c.get("scientificName")
            s, exact, same = score(name, [label])
            if not s and c.get("matchType") != "EXACT":
                continue
            out.append({"id": f"https://www.gbif.org/species/{c['usageKey']}", "curie": f"GBIF:{c['usageKey']}",
                        "label": label, "score": round(s, 3), "exact": exact or c.get("matchType") == "EXACT",
                        "same": same, "definition": " · ".join(x for x in (c.get("rank"), c.get("status")) if x) or None})
    return out


def _wikidata(name: str, cache: Cache) -> list[dict] | None:
    d = cache.get(name.lower(), lambda: _json(
        WIKIDATA_API, action="wbsearchentities", search=name, language="en", limit=7,
        format="json", type="item"))
    if d is None:
        return None
    out = []
    for item in d.get("search") or []:
        _, exact, same = score(name, [item.get("label") or "", *(item.get("aliases") or [])])   # an alias can make it exact,
        s = 1.0 if exact else score(name, [item.get("label") or ""])[0]                        # only the label otherwise
        if s > 0:
            out.append({"id": f"http://www.wikidata.org/entity/{item['id']}", "curie": f"wikidata:{item['id']}",
                        "label": item.get("label"), "score": round(s, 3), "exact": exact, "same": same,
                        "definition": item.get("description")})
    return out


_cf_terms: list[dict] | None = None


def cf_terms() -> list[dict]:
    """The CF Standard Names table: name, its words as a label, units, description; aliases included."""
    global _cf_terms
    if _cf_terms is None:
        path = CACHE / "cf-standard-name-table.xml"
        if not path.exists():
            r = requests.get(CF_TABLE, headers=UA, timeout=60)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        root = ET.fromstring(path.read_bytes())
        terms = {}
        for e in root.iter("entry"):
            sid = e.get("id")
            terms[sid] = {"id": sid, "labels": [sid.replace("_", " ")], "units": (e.findtext("canonical_units") or "").strip(),
                          "description": re.sub(r"\s+", " ", e.findtext("description") or "").strip()}
        for a in root.iter("alias"):
            target = (a.findtext("entry_id") or "").strip()
            if target in terms:
                terms[target]["labels"].append(a.get("id").replace("_", " "))
        _cf_terms = list(terms.values())
    return _cf_terms


def _cf(name: str) -> list[dict]:
    out = []
    for t in cf_terms():
        s, exact, same = score(name, t["labels"])
        if s >= 0.25:
            out.append({"id": f"http://vocab.nerc.ac.uk/standard_name/{t['id']}/", "curie": f"CF:{t['id']}",
                        "label": t["id"], "synonyms": t["labels"][:5], "score": round(s, 3), "exact": exact, "same": same,
                        "definition": (f"[{t['units']}] " if t["units"] else "") + t["description"][:200]})
    return out


def natura_terms() -> list[dict]:
    """Natura 2000 habitat types and species, with codes, from the Article 17 layers (cached)."""
    def fetch(layer, fields):
        d = _json(f"{ART17}/{layer}/query", where="1=1", outFields=",".join(fields), returnDistinctValues="true",
                  returnGeometry="false", f="json")
        return None if d is None or "features" not in d else [f["attributes"] for f in d["features"]]

    def build():
        hab = fetch(5, ["reference_habitatlist.habitat_code", "reference_habitatlist.label"])
        spe = fetch(6, ["reference_specieslist.species_code", "reference_specieslist.species_name",
                        "reference_specieslist.taxonomical_group"])
        if hab is None or spe is None:
            return None
        out = [{"code": a["reference_habitatlist.habitat_code"], "label": a["reference_habitatlist.label"],
                "category": "habitat"} for a in hab if a.get("reference_habitatlist.habitat_code")]
        out += [{"code": a["reference_specieslist.species_code"], "label": a["reference_specieslist.species_name"],
                 "category": "species", "group": a.get("reference_specieslist.taxonomical_group")}
                for a in spe if a.get("reference_specieslist.species_name")]
        return out
    terms = Cache("natura2000").get("art17_2019_2024", build)
    if terms is None:
        raise RuntimeError("The EEA Article 17 service did not answer; try again later.")
    return terms


_CODE = re.compile(r"^(?:n2k:|natura2000:)?(\d[0-9A-Z]{3})\b", re.I)


def _natura(name: str, raw: str) -> list[dict]:
    terms = natura_terms()
    candidate = lambda t, s, exact, same, note=None: {
        "id": f"n2k:{t['code']}", "curie": f"n2k:{t['code']}", "label": f"{t['code']} {t['label']}" if t["category"] == "habitat" else t["label"],
        "score": round(s, 3), "exact": exact, "same": same,
        "definition": note or ("Annex I habitat type" if t["category"] == "habitat" else f"species · {t.get('group') or ''}")}
    if (m := _CODE.match(raw.strip())) and (t := next((t for t in terms if t["code"] == m.group(1).upper()
                                                       and t["category"] == "habitat"), None)):
        return [candidate(t, 1.0, True, True, "matched by its Annex I code")]
    out = []
    for t in terms:
        s, exact, same = score(name, [t["label"]])
        if s >= 0.25:
            out.append(candidate(t, s, exact, same))
    return out


def search(name: str, ontology: str, top: int = 5) -> list[dict] | None:
    """The ontology's candidates for the term ``name``, best first (exact names first, then by
    word overlap, then in the source's own order); None if the service did not answer."""
    q = query_text(name)
    if not q:
        return []
    if ontology == "gbif":
        candidates = _gbif(q, Cache("search_gbif"))
    elif ontology == "wikidata":
        candidates = _wikidata(q, Cache("search_wikidata"))
    elif ontology == "cf":
        candidates = _cf(q)
    elif ontology == NATURA:
        candidates = _natura(q, name)
    elif ontology == "gold":
        from verdy import gold
        candidates = gold.load().search(q)
    else:
        candidates = _ols(q, ontology, Cache(f"search_{ontology}"))
    if candidates is None:
        return None
    candidates.sort(key=lambda c: (-c["same"], -c["exact"], -c["score"]))
    return candidates[:top]
