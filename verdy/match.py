"""Predict matches for your inputs in the ontologies you choose.

    import verdy
    matches = verdy.match("my_samples.csv", ontologies=["natura2000", "gold", "envo"])
    verdy.save(matches, "my_samples.matches.csv")

Words (as in the README):
    input           one ENA ID or one line of free text you give VERDY
    term            one text to match: a free-text input, or one field value of an ENA sample
    ontology class  an entry in an ontology: its ontology ID (ENVO:00001998), label and synonyms
    typed ID        an ontology ID written inside a term ("soil [ENVO:00001998]")
    candidate       an ontology class a search returned for a term
    match           a candidate kept for a term, with its match type and confidence

1. An ENA ID (sample, run or project) becomes one term per field of its sample: organism
   (scientific_name), broad_scale_environmental_context, local_environmental_context,
   environmental_medium, ...; a free-text input is one term as it is.
2. A typed ID is a match in its own ontology if its label fits the words beside it;
   otherwise it is kept as a relatedMatch with the reason in ``why``, and the words are
   searched as well.
3. Each term is searched in each chosen ontology separately:

    exactMatch     the candidate's label or a synonym is the term (plurals and 'sp.' aside)
    closeMatch     most of their words are shared (overlap >= 0.6)
    relatedMatch   some words are shared (overlap >= ``min_score``)

Up to ``per_ontology`` matches per term and ontology; when there is an exact one, only it.
In the taxonomies (NCBITaxon, GBIF) only exact names count: a near name is another taxon.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from verdy import embed, gold
from verdy.hosts import HOST_FIELDS, host
from verdy.resolve import SAMPLE_FIELDS, kind, samples
from verdy.summary import summarise
from verdy.sources import TAXONOMIES, by_id, counted, ids_in, ontology_info, query_text, search, words

NAME_COLUMNS = ("name", "label", "term", "parameter", "measurement", "variable", "scientific_name", "scientificname",
                "species", "taxon", "habitat", "biome", "text", "value", "description")
ID_COLUMNS = ("id", "subject_id", "identifier", "accession", "sample_accession", "run_accession", "study_accession",
              "sample_id", "sample", "key", "source", "code")
CATEGORY_COLUMNS = ("category", "group", "type", "kind", "field")
MATCH_TYPES = ("skos:exactMatch", "skos:closeMatch", "skos:relatedMatch")


# --- your terms ---------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:60] or "term"


def _pick(columns, wanted) -> str | None:
    low = {str(c).strip().lower(): c for c in columns}
    return next((low[w] for w in wanted if w in low), None)


def read_terms(data, column: str | None = None) -> list[dict]:
    """Your inputs as ``[{"id", "label", "category"}]`` (``label``: the input's text) from a
    CSV / TSV / Excel file, a text file with one input per line, a list of strings or dicts,
    or a pandas DataFrame. The column read is given with ``column=``, or found by its header:
    a text column (name, label, term, parameter, measurement, species, ...) if there is one,
    else an ID column (id, accession, sample_accession, run_accession, ...). Repeats once."""
    if hasattr(data, "to_dict") and hasattr(data, "columns"):            # pandas DataFrame
        rows = data.fillna("").astype(str).to_dict("records")
    elif isinstance(data, (list, tuple)):
        rows = [r if isinstance(r, dict) else {"name": r} for r in data]
    else:
        path = Path(data)
        if path.suffix.lower() in (".xlsx", ".xls"):
            import pandas as pd
            rows = pd.read_excel(path, dtype=str).fillna("").to_dict("records")
        else:
            text = path.read_text(encoding="utf-8-sig")
            lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
            delim = "\t" if path.suffix.lower() in (".tsv", ".txt") or text.count("\t") > text.count(",") else ","
            first = lines[0] if lines else ""
            header = _pick(next(csv.reader([first], delimiter=delim)), NAME_COLUMNS + ID_COLUMNS) if lines else None
            if column is None and header is None and (delim not in first or path.suffix.lower() == ".txt"):
                rows = [{"name": ln.strip()} for ln in lines]                 # one input per line, no header
            else:
                rows = list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delim))
    if not rows:
        return []
    cols = list(rows[0])
    id_col, cat_col = _pick(cols, ID_COLUMNS), _pick(cols, CATEGORY_COLUMNS)
    name_col = column or _pick(cols, NAME_COLUMNS) or id_col
    if name_col is None:      # the first column with words in it
        name_col = next((c for c in cols if c != id_col and any(re.search(r"[A-Za-z]{3}", str(r.get(c) or "")) for r in rows[:20])), None)
    if name_col is None or name_col not in cols:
        raise ValueError(f"No text column found; give one with column= (columns: {', '.join(map(str, cols))}).")
    out, seen = [], set()
    for r in rows:
        label = str(r.get(name_col) or "").strip()
        if not label or label.lower() == "nan":
            continue
        tid = (str(r.get(id_col) or "").strip() if id_col and id_col != name_col else "") or _slug(label)
        if tid in seen:
            continue
        seen.add(tid)
        out.append({"id": tid, "label": label, "category": (str(r.get(cat_col) or "").strip() or None) if cat_col else None})
    return out


# --- ENA IDs to terms ----------------------------------------------------------------

def resolve_terms(inputs: list[dict], fields=SAMPLE_FIELDS, workers: int = 6,
                  progress=None) -> tuple[list[dict], list[str]]:
    """The terms to match: a free-text input as it is; an ENA ID becomes one term per field value
    of its sample(s) (``id`` the sample, or the sample or run ID given; ``category`` the field(s)
    it came from; ``context`` what else ENA says about the sample, and its host as an NCBITaxon
    class with its ancestors, ``host_taxon``). ENA is asked for all the IDs at once. The ENA IDs
    nothing was found for come second. ``progress(stage, done, total)`` as in ``match``."""
    found = samples([t["label"] for t in inputs], fields, workers, progress)
    _add_hosts([r for recs in found.values() for r in recs or []], workers, progress)
    out, unresolved = [], []
    for t in inputs:
        if t["label"] not in found:
            out.append(t)
            continue
        recs = found[t["label"]]
        if not any(r["values"] for r in recs or []):
            unresolved.append(t["label"] + (" (no answer from its source)" if recs is None else ""))
            continue
        project = kind(t["label"]) == "project"
        merged: dict[tuple[str, str], dict] = {}
        for r in recs:
            tid = r["sample"] if project else t["label"]
            for field, value in r["values"]:
                term = merged.setdefault((tid, value), {"fields": [], "context": r["context"]})
                term["fields"].append(field)
        for (tid, value), term in merged.items():
            out.append({"id": tid, "label": value, "category": "|".join(dict.fromkeys(term["fields"])),
                        **({"input": t["label"]} if tid != t["label"] else {}), "context": term["context"]})
    return out, unresolved


def _add_hosts(records: list[dict], workers: int, progress=None) -> None:
    """Each sample record's host (from its host fields, by OLS4's NCBITaxon) into its context."""
    def said(r):
        fields = {**dict(r["values"]), **r["context"]}
        return tuple((f, fields[f]) for f in HOST_FIELDS if fields.get(f))
    keys = list(dict.fromkeys(k for k in map(said, records) if k))
    found = dict(zip(keys, counted(lambda k: host(dict(k)), keys, workers, "Looking up hosts", progress)))
    for r in records:
        if found.get(said(r)):
            r["context"]["host_taxon"] = found[said(r)]


# --- matching ---------------------------------------------------------------------------

# Words added to a label that don't change its meaning
_GENERIC = {"biome", "environment", "environmental", "ecosystem", "material"}
TYPED = "ID in the text"        # ``why`` of a typed-ID match starts with this


def _typed(term: dict, short: str) -> tuple[list[dict], bool]:
    """Matches for the typed IDs of this ontology in the term, and whether one settles it.

    1. The words beside the ID are none, or the words of its label or a synonym (give or take
       a generic word from _GENERIC) -> exactMatch 1.0.
    2. They share some words with the label: e.g. "marine biome ENVO:01000024" is the marine
       *benthic* biome -> relatedMatch 0.75.
    3. They share none -> relatedMatch 0.5.
    In 2 and 3 the words are searched as well."""

    out, settled = [], False
    said = words(query_text(term["label"]))
    for prefix, number in ids_in(term["label"]):
        if prefix.lower() != short.lower():
            continue
        ontology_id = f"{short}:{number}"
        found = by_id(ontology_id)
        if not found:
            continue
        names = [found["label"], *found["synonyms"]]
        if not said or any(words(n) - _GENERIC <= said <= words(n) | _GENERIC for n in names):
            kind, conf, why = "skos:exactMatch", 1.0, TYPED
            settled = True
        elif said & set().union(*(words(n) for n in names)):
            kind, conf, why = "skos:relatedMatch", 0.75, f"{TYPED}, but it is {found['label']}: more than the term says"
        else:
            kind, conf, why = "skos:relatedMatch", 0.5, f"{TYPED}, but it is {found['label']}: not what the term says"
        out.append({"term_id": term["id"], "term": term["label"], "category": term.get("category"), "match_type": kind,
                    "ontology": short, "match_id": found["id"], "match_curie": ontology_id, "match_label": found["label"],
                    "confidence": conf, "method": "ID", "word_overlap": None, "cosine": None, "rank": len(out) + 1,
                    "definition": found["definition"], "searched_for": query_text(term["label"]), "why": why})
    return out, settled


def _ontologies(ontologies) -> list[str]:
    if isinstance(ontologies, str):
        ontologies = re.split(r"[,\s]+", ontologies)
    return list(dict.fromkeys(o.strip().lower() for o in ontologies or [] if o and o.strip()))


def _matches(term: dict, ontology: str, short: str, candidates: list[dict], per_ontology: int, min_score: float,
             cos: list[float] | None = None, min_cosine: float = embed.MIN_COSINE) -> list[dict]:
    """Pick the candidates kept as matches and give each its match type. Words decide exact
    matches; with embeddings, cosine similarity also orders the others and can keep a
    candidate that shares no word with the term. Cosine never makes an exactMatch, and is not
    used for a narrower candidate, one that says more than the term ("water": tap water)."""
    said = words(query_text(term["label"]))
    if cos is not None:
        for c, s in zip(candidates, cos):
            c["cosine"] = round(s, 4)
            narrower = said < words(str(c["label"]).split(">")[-1])
            c["by_cosine"] = None if narrower else c["cosine"]
    exact = [c for c in candidates if c["exact"]]
    if ontology in TAXONOMIES or exact:
        chosen = exact[:1]
    elif cos is not None:
        keep = [c for c in candidates if (c["by_cosine"] or 0) >= min_cosine or c["score"] >= min_score]
        chosen = sorted(keep, key=lambda c: -max(c["by_cosine"] or 0, c["score"]))[:per_ontology]
    else:
        chosen = [c for c in candidates if c["score"] >= min_score][:per_ontology]
    out = []
    for rank, c in enumerate(chosen, 1):
        s = c.get("by_cosine")
        if c["exact"]:
            kind, conf = "skos:exactMatch", 1.0 if c["same"] else 0.95
        elif c["score"] >= 0.6 or (s is not None and s >= max(embed.CLOSE, min_cosine)):
            kind, conf = "skos:closeMatch", round(max(0.5 + 0.4 * c["score"], s or 0), 3)
        else:
            kind, conf = "skos:relatedMatch", round(max(0.3 + 0.4 * c["score"], s or 0), 3)
        method, why = _how(c, kind, conf)
        out.append({"term_id": term["id"], "term": term["label"], "category": term.get("category"),
                    "match_type": kind, "ontology": short, "match_id": c["id"], "match_curie": c["curie"],
                    "match_label": c["label"], "confidence": conf, "method": method, "word_overlap": c["score"],
                    "cosine": c.get("cosine"), "rank": rank, "definition": c.get("definition"),
                    "searched_for": query_text(term["label"]), "why": why})
    return out


def _how(c: dict, kind: str, conf: float) -> tuple[str, str]:
    """(method, why) of a match found by searching: an ID (a Natura 2000 code), the ontology's names, or cosine."""
    if c.get("definition") == "matched by its Annex I code":
        return "ID", "its Annex I code"
    if kind == "skos:exactMatch":
        return "ontology name", "the label or a synonym is the term" + ("" if c["same"] else ", plurals aside")
    guard = f"; cosine not used: {str(c['label']).split('>')[-1].strip()} says more than the term" \
        if c.get("cosine") is not None and c.get("by_cosine") is None else ""
    by_words = (0.5 if kind == "skos:closeMatch" else 0.3) + 0.4 * c["score"]
    if c.get("by_cosine") is not None and c["by_cosine"] > by_words:
        return "cosine", f"cosine {c['by_cosine']} (word overlap {c['score']})"
    return "ontology name", f"word overlap {c['score']}" + guard


def match(data, ontologies, *, column: str | None = None, per_ontology: int = 3, min_score: float = 0.34,
          embeddings: bool | None = None, min_cosine: float = embed.MIN_COSINE, model: str | None = None,
          fields=SAMPLE_FIELDS, progress=None,
          workers: int = 6) -> list[dict]:
    """Matches for every input in ``data`` in each of ``ontologies``: one dict per match with
    term_id (the sample, your ID, or the term itself), term, category (the ENA field it came
    from), match_type, ontology, match_id (the IRI), match_curie (the ontology ID),
    match_label, confidence, word_overlap, cosine, rank, definition, searched_for, why.

    ``ontologies``: a list or a comma-separated string of IDs (``verdy.ONTOLOGIES`` or any
    OLS4 ontology). ``embeddings``: also compare by cosine similarity of SentenceTransformers
    embeddings (default: when ``verdy[embeddings]`` is installed); ``min_cosine``: the least
    cosine similarity for a match kept on embeddings (default 0.60; 0.80 or more is a
    closeMatch); ``model`` names the model (default all-MiniLM-L6-v2). ``fields``: which ENA sample fields to search for a sample,
    run or project. ``progress(stage, done, total)`` is called through each slow stage (looking up
    ENA IDs, hosts, reading GOLD, searching, embeddings); ``done`` and ``total`` are None while a
    stage can't count. ENA IDs nothing was found for are in ``match.unresolved`` after the call.

    For samples (from ENA IDs), with ``gold`` or ``envo`` chosen, ``match.samples`` holds one row
    per sample after the call: its one GOLD path and one ENVO class, chosen from all its terms,
    context and host together (see verdy.summary)."""
    chosen = _ontologies(ontologies)
    if not chosen:
        raise ValueError("Choose at least one ontology, e.g. ontologies=['envo', 'ncbitaxon'].")
    use_embeddings = embed.available() if embeddings is None else embeddings
    if use_embeddings and not embed.available():
        raise ValueError('embeddings=True needs sentence-transformers: pip install "verdy[embeddings]"')
    terms = data if isinstance(data, list) and data and isinstance(data[0], dict) and {"id", "label"} <= set(data[0]) \
        else read_terms(data, column)
    terms, match.unresolved = resolve_terms(terms, fields, workers, progress)
    shorts = {}
    for o in chosen:
        info = ontology_info(o)
        if info is None:
            raise ValueError(f"Unknown ontology “{o}”: use one of verdy.ONTOLOGIES or an OLS4 ontology ID.")
        shorts[o] = info["short"]
    if "gold" in chosen:
        gold.load(workers, progress)           # once, here, not inside the searches

    # Typed IDs first; one that fits the words beside it settles that term in its ontology.
    typed: dict[tuple[int, str], list[dict]] = {}
    settled = set()
    for i, t in enumerate(terms):
        if not ids_in(t["label"]):
            continue
        for o in chosen:
            rows, done_ = _typed(t, shorts[o])
            if rows:
                typed[(i, o)] = rows
            if done_:
                settled.add((i, o))

    top = 10 if use_embeddings else 5          # more candidates when embeddings will order them
    tasks = [(i, t, o) for o in chosen for i, t in enumerate(terms) if (i, o) not in settled]
    answers = counted(lambda task: (*task, search(task[1]["label"], task[2], top=top)), tasks,
                      2 if "wikidata" in chosen else workers, "Searching the ontologies", progress)
    found = [(i, t, o, candidates) for i, t, o, candidates in answers if candidates]

    cos: dict[int, list[float]] = {}
    if use_embeddings:                         # one batch for all terms and candidates (not taxonomies)
        if progress:
            progress("Comparing by embeddings", None, None)
        pairs = [(n, query_text(t["label"]), embed.candidate_text(c))
                 for n, (_, t, o, candidates) in enumerate(found) if o not in TAXONOMIES for c in candidates]
        sims = embed.cosine([p[1] for p in pairs], [p[2] for p in pairs], **({"model": model} if model else {}))
        for (n, _, _), s in zip(pairs, sims):
            cos.setdefault(n, []).append(s)

    groups: dict[tuple[int, str], list[dict]] = {k: list(rows) for k, rows in typed.items()}
    for n, (i, t, o, candidates) in enumerate(found):
        groups.setdefault((i, o), []).extend(_matches(t, o, shorts[o], candidates, per_ontology, min_score,
                                                      cos.get(n), min_cosine))
    matches = [m for rows in groups.values() for m in _ranked(rows)]
    match.samples = summarise(terms, matches, chosen, workers, progress)
    return matches


def _ranked(rows: list[dict]) -> list[dict]:
    """Number one term's matches in one ontology: highest confidence first. On a tie, a typed
    ID goes before a match found by searching the words."""
    def typed(m):
        return m["why"].startswith(TYPED)
    rows = sorted(rows, key=lambda m: (-(m["confidence"] or 0), not typed(m)))
    for rank, m in enumerate(rows, 1):
        m["rank"] = rank
    return rows


def unmatched(data, matches: list[dict], ontologies) -> dict[str, list[str]]:
    """Per ontology, the terms that got no match in it (``data``: the inputs or the terms)."""
    terms = data if isinstance(data, list) and data and isinstance(data[0], dict) and "label" in data[0] else read_terms(data)
    got = {(m["term_id"], m["ontology"].lower()) for m in matches}
    out = {}
    for o in _ontologies(ontologies):
        short = (ontology_info(o) or {}).get("short", o).lower()
        out[o] = [t["label"] for t in terms if (t["id"], short) not in got]
    return out
