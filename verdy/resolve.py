"""ENA IDs to the terms worth searching for: their samples' field values (ENA Portal API).

    resolve("SAMD00132352") -> [("scientific_name", "air metagenome"),
                                ("broad_scale_environmental_context", "urban biome"), ...]
    resolve("ERR10002200")  -> the run's sample, as above
    resolve("PRJEB54740")   -> every sample of the project, as "<sample>:<field>"
    samples([...])          -> many ENA IDs at once: each one's samples, with their context

Samples (SAMN/SAMEA/SAMD..., ERS/SRS/DRS...), runs and experiments (ERR/SRR/DRR...,
ERX/SRX/DRX...) and projects (PRJEB/PRJNA/PRJDB..., ERP/SRP/DRP...). Anything else is
free text and is searched as it is.

ENA is asked in bulk: samples and runs BATCH to a request, each project in one request for
all its samples (those without runs too). Every answer is cached by the fields asked for.
"""

from __future__ import annotations

import re

from verdy import sources
from verdy.sources import Cache, counted
# ENA sample fields that say what a sample is; each value is a term. ``fields=`` chooses others (see ENA's returnFields).
SAMPLE_FIELDS = ("scientific_name", "broad_scale_environmental_context", "local_environmental_context",
                 "environmental_medium", "environment_biome", "environment_feature", "environment_material",
                 "isolation_source", "host", "host_scientific_name", "host_body_site", "tissue_type")
# Read with them but not searched: the sample's context (its host's taxon, its own words), for choosing among its matches.
CONTEXT_FIELDS = ("host_tax_id", "sample_title", "sample_description", "description")
EMPTY = {"", "missing", "not applicable", "not collected", "not provided", "na", "n/a", "unknown", "none"}
BATCH = 100          # IDs per ENA query; it is POSTed, so its length is no problem

SAMPLE = re.compile(r"^(SAM[NED][A-Z]?\d+|[EDS]RS\d+)$", re.I)
RUN = re.compile(r"^[EDS]R[RX]\d+$", re.I)
PROJECT = re.compile(r"^(PRJ[EDN][A-Z]\d+|[EDS]RP\d+)$", re.I)


def kind(identifier: str) -> str:
    """What sort of ID this is, or 'name' when it is not one."""
    s = str(identifier or "").strip()
    for name, pattern in (("sample", SAMPLE), ("run", RUN), ("project", PROJECT)):
        if pattern.match(s):
            return name
    return "name"


def _keep(value) -> bool:
    return str(value or "").strip().lower() not in EMPTY


def _sample_rows(accessions: list[str], fields: tuple) -> dict[str, dict | None]:
    """{accession: its ENA sample row ({} when ENA does not know it, None when it did not answer)}."""
    cache, sig = Cache("resolve_ena_sample"), ",".join(fields)
    want = ("sample_accession", "secondary_sample_accession", *fields)
    out = {a: cache.data.get(f"{a.upper()}|{sig}") for a in accessions}
    todo = list(dict.fromkeys(a.upper() for a, row in out.items() if row is None))
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        rows = sources.ena_search("sample", want, ("sample_accession", "secondary_sample_accession"), batch)
        if rows is None:
            continue
        by = {str(r.get(k) or "").upper(): r for r in rows for k in ("sample_accession", "secondary_sample_accession")}
        cache.put({f"{a}|{sig}": by.get(a, {}) for a in batch})
    for a in accessions:
        out[a] = cache.data.get(f"{a.upper()}|{sig}")
    return out


def _run_samples(accessions: list[str]) -> dict[str, list[str] | None]:
    """{run or experiment: its sample accessions}."""
    cache = Cache("resolve_ena_runs")
    todo = list(dict.fromkeys(a.upper() for a in accessions if a.upper() not in cache.data))
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        rows = sources.ena_search("read_run", ("run_accession", "experiment_accession", "sample_accession"),
                                  ("run_accession", "experiment_accession"), batch)
        if rows is None:
            continue
        got: dict[str, list[str]] = {a: [] for a in batch}
        for r in rows:
            for k in ("run_accession", "experiment_accession"):
                key = str(r.get(k) or "").upper()
                if key in got and r.get("sample_accession") and r["sample_accession"] not in got[key]:
                    got[key].append(r["sample_accession"])
        cache.put(got)
    return {a: cache.data.get(a.upper()) for a in accessions}


def _studies(accessions: list[str]) -> dict[str, dict | None]:
    """{project as given: {"prj": its PRJ accession, "title"}} ({} when ENA does not know it).
    ENA's sample search needs the PRJ accession; ERP/SRP/DRP ones are looked up here."""
    cache = Cache("resolve_ena_studies")
    todo = list(dict.fromkeys(a.upper() for a in accessions if a.upper() not in cache.data))
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        rows = sources.ena_search("study", ("study_accession", "secondary_study_accession", "study_title"),
                                  ("study_accession", "secondary_study_accession"), batch)
        if rows is None:
            continue
        got = {a: {} for a in batch}
        for r in rows:
            for k in ("study_accession", "secondary_study_accession"):
                key = str(r.get(k) or "").upper()
                if key in got and r.get("study_accession"):
                    got[key] = {"prj": r["study_accession"], "title": r.get("study_title") or ""}
        cache.put(got)
    out = {}
    for a in accessions:
        info = cache.data.get(a.upper())
        if info == {} and a.upper().startswith("PRJ"):           # not in the study search: try its samples anyway
            info = {"prj": a.upper(), "title": ""}
        out[a] = info
    return out


def _project_rows(prj: str, fields: tuple) -> list[dict] | None:
    want = ("sample_accession", "secondary_sample_accession", *fields)
    return Cache("resolve_ena_project").get(f"{prj}|{','.join(fields)}",
                                            lambda: sources.ena_search("sample", want, ("study_accession",), [prj]))


def _record(row: dict, searched: tuple, study: dict | None = None) -> dict:
    return {"sample": row["sample_accession"],
            "values": [(f, str(row[f]).strip()) for f in searched if _keep(row.get(f))],
            "context": {**{f: str(row[f]).strip() for f in CONTEXT_FIELDS if _keep(row.get(f))},
                        **({"study": study["prj"], "study_title": study["title"]} if study else {})}}


STAGE = "Looking up ENA IDs"


def samples(identifiers, fields=SAMPLE_FIELDS, workers: int = 6, progress=None) -> dict[str, list[dict] | None]:
    """{ENA ID: its samples}, each ``{"sample", "values": [(field, value)], "context": {...}}``:
    ``values`` the fields to search, ``context`` what else ENA says (host_tax_id, sample_title,
    sample_description, description; a project's study and study_title). [] when ENA does not
    know the ID, None when it did not answer. Free text is left out. ``progress(stage, done, total)``
    counts the IDs."""
    ids = [s for s in dict.fromkeys(str(i or "").strip() for i in identifiers) if kind(s) != "name"]
    if progress and ids:
        progress(STAGE, 0, len(ids))
    searched = tuple(fields)
    fields = tuple(dict.fromkeys([*searched, *CONTEXT_FIELDS]))
    by_kind = {k: [s for s in ids if kind(s) == k] for k in ("sample", "run", "project")}
    out: dict[str, list[dict] | None] = {}

    runs = _run_samples(by_kind["run"])
    rows = _sample_rows(by_kind["sample"] + [a for accs in runs.values() for a in accs or []], fields)
    for s in by_kind["sample"]:
        out[s] = None if rows[s] is None else [_record(rows[s], searched)] if rows[s] else []
    for s, accs in runs.items():
        out[s] = None if accs is None or any(rows[a] is None for a in accs) else \
            [_record(rows[a], searched) for a in accs if rows[a]]
    done = len(out)
    if progress and ids:
        progress(STAGE, done, len(ids))

    studies = _studies(by_kind["project"])
    known = [s for s, info in studies.items() if info]
    done += len(studies) - len(known)
    each = (lambda stage, d, total: progress(STAGE, done + d, len(ids))) if progress else None
    found = dict(zip(known, counted(lambda s: _project_rows(studies[s]["prj"], fields), known, workers, STAGE, each)))
    for s, info in studies.items():
        got = found.get(s, [] if info == {} else None)
        out[s] = None if got is None else \
            [_record(r, searched, info) for r in {r["sample_accession"]: r for r in got if r.get("sample_accession")}.values()]
    return out


def resolve(identifier, fields=SAMPLE_FIELDS) -> list[tuple[str, str]] | None:
    """``[(field, value), ...]`` to search for: an ENA ID's sample field values (None when ENA did
    not answer, [] when it does not know the ID), or free text as it is."""
    s = str(identifier or "").strip()
    k = kind(s)
    if k == "name":
        return [("name", s)] if s else []
    found = samples([s], fields)[s]
    if found is None:
        return None
    return [(f"{r['sample']}:{f}" if k == "project" else f, v) for r in found for f, v in r["values"]]
