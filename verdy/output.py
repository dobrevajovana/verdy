"""Matches out: a table (CSV / TSV), SSSOM, JSON, or a pandas DataFrame."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from verdy.constants import GOLD_PATH, GOLD_VOCAB, OBO

COLUMNS = ["term_id", "term", "category", "match_type", "ontology", "match_curie", "match_label", "confidence",
           "method", "word_overlap", "cosine", "rank", "match_id", "definition", "searched_for", "why"]
PREFIXES = {**{p: f"{OBO}{p}_" for p in ("ENVO", "NCBITaxon", "PATO", "OBA", "UO", "CHEBI", "OBI", "UBERON", "PO", "GO")},
            "GBIF": "https://www.gbif.org/species/", "wikidata": "http://www.wikidata.org/entity/",
            "CF": "http://vocab.nerc.ac.uk/standard_name/", "GOLD": GOLD_VOCAB, "GOLD.path": GOLD_PATH,
            "n2k": "https://w3id.org/verdy/natura2000/"}   # local: Natura 2000 has no URIs of its own


def to_table(matches: list[dict], sep: str = ",") -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=sep, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(matches)
    return buf.getvalue()


def _subject(term_id: str) -> str:
    """The term_id with a prefix, for SSSOM: ENA IDs with their registry's, prefixed IDs as they
    are, free text under term:."""
    t = str(term_id)
    if re.match(r"^SAM[NED][A-Z]?\d+$", t):
        return "biosample:" + t
    if re.match(r"^([EDS]R[RXSP]|PRJ[EDN][A-Z])\d+$", t):
        return "ena.embl:" + t
    if re.match(r"^[A-Za-z][\w.]*:\S+$", t) or t.startswith("http"):
        return t
    if re.match(r"^Q\d+$", t):
        return "wikidata:" + t
    return "term:" + re.sub(r"\s+", "_", t)


def to_sssom(matches: list[dict], name: str = "matches") -> str:
    """SSSOM TSV: lexical matches with their confidence, subjects as ``term:<term_id>``."""
    used = {m["match_curie"].split(":", 1)[0] for m in matches if ":" in m["match_curie"]}
    header = ["# curie_map:", "#   term: https://w3id.org/verdy/term/",
              "#   biosample: https://www.ebi.ac.uk/biosamples/samples/", "#   ena.embl: https://www.ebi.ac.uk/ena/browser/view/"] + \
        [f"#   {p}: {u}" for p, u in PREFIXES.items() if p in used] + [
        "#   skos: http://www.w3.org/2004/02/skos/core#", "#   semapv: https://w3id.org/semapv/vocab/",
        f"# mapping_set_id: https://w3id.org/verdy/{re.sub(r'[^A-Za-z0-9_.-]+', '-', name)}.sssom.tsv",
        "# mapping_set_description: Lexical matches found by VERDY; not reviewed."]
    fields = ["subject_id", "subject_label", "subject_category", "predicate_id", "object_id", "object_label",
              "mapping_justification", "confidence", "object_source", "mapping_tool", "comment"]
    buf = io.StringIO()
    buf.write("\n".join(header) + "\n")
    w = csv.DictWriter(buf, fieldnames=fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for m in matches:
        w.writerow({"subject_id": _subject(m["term_id"]), "subject_label": m["term"],
                    "subject_category": m.get("category") or "", "predicate_id": m["match_type"],
                    "object_id": m["match_curie"], "object_label": m["match_label"] or "",
                    "mapping_justification": "semapv:LexicalMatching", "confidence": m["confidence"],
                    "object_source": m["ontology"], "mapping_tool": "verdy",
                    "comment": f"word overlap {m['word_overlap']}"
                               + (f"; cosine {m['cosine']}" if m.get("cosine") is not None else "") + f"; rank {m['rank']}"})
    return buf.getvalue()


SAMPLE_COLUMNS = ["sample", "input", "study", "study_title", "host", "evidence", "status"]
PER_ONTOLOGY = ["id", "label", "match_type", "confidence", "method", "why"]


def sample_rows(samples: list[dict]) -> list[dict]:
    """``verdy.match.samples`` as flat rows: the sample, then ``<ontology>_id``, ``_label``, ``_match_type``,
    ``_confidence``, ``_method`` and ``_why`` for each chosen ontology, side by side. ``status`` names the
    ontologies the sample got no match in."""
    rows = []
    for s in samples:
        row = {k: s.get(k) or "" for k in SAMPLE_COLUMNS}
        missing = [o for o, m in s["matches"].items() if not m]
        row["status"] = "matched" if not missing else "no match" if len(missing) == len(s["matches"]) \
            else "no match in " + ", ".join(missing)
        for o, m in s["matches"].items():
            m = m or {}
            row.update({f"{o}_id": m.get("match_curie") or "", f"{o}_label": m.get("match_label") or "",
                        f"{o}_match_type": m.get("match_type") or "",
                        f"{o}_confidence": "" if m.get("confidence") is None else m["confidence"],
                        f"{o}_method": m.get("method") or "", f"{o}_why": m.get("why") or ""})
        rows.append(row)
    return rows


def to_sample_table(samples: list[dict], sep: str = ",") -> str:
    rows = sample_rows(samples)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else SAMPLE_COLUMNS, delimiter=sep, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def save_samples(samples: list[dict], path) -> Path:
    """One row per sample, by the extension: .csv, .tsv, .json (or .xlsx with pandas)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(samples, indent=1, ensure_ascii=False), encoding="utf-8")
    elif path.suffix.lower() == ".xlsx":
        import pandas as pd
        pd.DataFrame(sample_rows(samples)).to_excel(path, index=False)
    else:
        path.write_text(to_sample_table(samples, "\t" if path.suffix.lower() == ".tsv" else ","), encoding="utf-8")
    return path


def samples_path(path) -> Path:
    """Where the per-sample file goes beside a matches file: results.csv -> results.samples.csv
    (an SSSOM file's samples go to a .tsv)."""
    path = Path(path)
    if path.name.endswith(".sssom.tsv"):
        return path.with_name(path.name[: -len(".sssom.tsv")] + ".samples.tsv")
    return path.with_name(path.stem + ".samples" + path.suffix)


def to_dataframe(matches: list[dict]):
    import pandas as pd
    return pd.DataFrame(matches, columns=COLUMNS)


def save(matches: list[dict], path) -> Path:
    """By the extension: .csv, .tsv, .sssom.tsv, .json (or .xlsx with pandas)."""
    path = Path(path)
    if path.name.endswith(".sssom.tsv"):
        path.write_text(to_sssom(matches, path.name[: -len(".sssom.tsv")]), encoding="utf-8")
    elif path.suffix.lower() == ".json":
        path.write_text(json.dumps(matches, indent=1, ensure_ascii=False), encoding="utf-8")
    elif path.suffix.lower() == ".xlsx":
        to_dataframe(matches).to_excel(path, index=False)
    else:
        path.write_text(to_table(matches, "\t" if path.suffix.lower() == ".tsv" else ","), encoding="utf-8")
    return path
