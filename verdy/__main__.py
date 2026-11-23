"""Command line:  verdy INPUTS -o envo,pato,cf [--column NAME] [--out FILE]

    verdy my_inputs.csv -o envo,ncbitaxon,gbif --out my_inputs.matches.csv
    verdy my_inputs.csv -o pato,cf,uo                      # print a table instead
    verdy --list                                           # the ready ontologies
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verdy.match import match, read_terms, resolve_terms, unmatched
from verdy.output import samples_path, save, save_samples, to_table
from verdy.progress import ProgressBar
from verdy.sources import ONTOLOGIES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verdy", description="Match your ENA IDs or free text to the ontologies you choose.")
    ap.add_argument("inputs", nargs="?", help="CSV / TSV / Excel with an ID or text column, or a text file with one input per line")
    ap.add_argument("-o", "--ontologies", help="comma-separated: see --list; any OLS4 ontology works too")
    ap.add_argument("--column", help="the column holding the inputs (found by its header otherwise)")
    ap.add_argument("--out", type=Path, help="write here: .csv, .tsv, .sssom.tsv, .json or .xlsx (default: print)")
    ap.add_argument("--per-ontology", type=int, default=3, help="at most this many matches per term and ontology (3)")
    ap.add_argument("--min-score", type=float, default=0.34, help="least word overlap for a related match (0.34)")
    ap.add_argument("--embeddings", action=argparse.BooleanOptionalAction, default=None,
                    help="also compare by embedding cosine similarity (default: when verdy[embeddings] is installed)")
    ap.add_argument("--min-cosine", type=float, default=0.60,
                    help="least embedding cosine similarity for a match (0.60); 0.80 or more is a closeMatch")
    ap.add_argument("--model", help="SentenceTransformers model for --embeddings (default all-MiniLM-L6-v2)")
    ap.add_argument("--list", action="store_true", help="list the ready ontologies")
    args = ap.parse_args(argv)
    if args.list:
        for k, v in ONTOLOGIES.items():
            print(f"{k:11} {v}")
        return 0
    if not args.inputs or not args.ontologies:
        ap.error("give an INPUTS file and --ontologies (or --list)")
    bar = ProgressBar()
    try:
        inputs = read_terms(args.inputs, args.column)
        matches = match(inputs, args.ontologies, per_ontology=args.per_ontology,
                        min_score=args.min_score, embeddings=args.embeddings, min_cosine=args.min_cosine, model=args.model,
                        progress=bar)
    except ValueError as exc:
        ap.error(str(exc))
    bar.close()
    unresolved = match.unresolved
    if unresolved:
        print(f"nothing found for {len(unresolved)} IDs: {', '.join(unresolved[:20])}"
              + (" ..." if len(unresolved) > 20 else ""), file=sys.stderr)
    if args.out:
        save(matches, args.out)
        print(f"{len(matches)} matches for {len({m['term_id'] for m in matches})} of {len(inputs)} inputs -> {args.out}",
              file=sys.stderr)
        if match.samples:
            path = save_samples(match.samples, samples_path(args.out))
            print(f"{len(match.samples)} samples, one row each -> {path}", file=sys.stderr)
    else:
        sys.stdout.write(to_table(matches, "\t"))
    for o, missing in unmatched(resolve_terms(inputs)[0], matches, args.ontologies).items():
        if missing:
            print(f"nothing in {o} for: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
