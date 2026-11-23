"""VERDY: predict matches for your ENA IDs or free text in the ontologies you choose.

Part of VERDANT: Vocabulary Enrichment & Resolution of Diversity Annotations via Neural Technology.

Your inputs (a CSV / TSV / Excel file, a text file or a Python list) are ENA IDs (samples,
runs, projects) and/or free text (species, habitats, parameters, measurements). Each ENA
ID becomes one term per organism and environment field of its sample; every term is
searched in each ontology you choose; out come its exact and most related matches.
The words used are defined in the README and in verdy.match.

    import verdy

    matches = verdy.match("my_input.csv", ontologies=["natura2000", "gold", "envo", "ncbitaxon"])
    verdy.save(matches, "my_input.matches.csv")        # or .tsv / .sssom.tsv / .json / .xlsx
    verdy.save_samples(verdy.match.samples, "my_input.samples.csv")   # one row per sample
    verdy.match.unresolved                             # ENA IDs ENA did not know
    verdy.unmatched("my_input.csv", matches, ["envo"]) # terms an ontology found nothing for

    verdy.ONTOLOGIES                       # the ready ones; any OLS4 ontology works too
    verdy.search("air temperature", "cf")  # one term in one ontology: its candidates
    verdy.resolve("SAMD00132352")          # what ENA says about an ID
    verdy.samples(["PRJEB54740", "ERR1"])  # many ENA IDs at once: their samples, with context
    verdy.host({"host": "cow"})            # a host as an NCBITaxon class with its ancestors (OLS4)

From the shell:  verdy my_input.csv -o natura2000,gold,envo --out my_input.matches.csv
"""

from verdy.match import MATCH_TYPES, match, read_terms, resolve_terms, unmatched
from verdy.hosts import host
from verdy.resolve import CONTEXT_FIELDS, SAMPLE_FIELDS, resolve, samples
from verdy.output import sample_rows, save, save_samples, to_dataframe, to_sample_table, to_sssom, to_table
from verdy.progress import ProgressBar
from verdy.sources import ONTOLOGIES, ontology_info, search

__version__ = "0.1.1"

predict = match          # the same: inputs in, predicted matches out

__all__ = ["match", "predict", "ProgressBar", "save_samples", "sample_rows", "to_sample_table", "resolve", "resolve_terms", "samples", "host","SAMPLE_FIELDS", "CONTEXT_FIELDS", "search", "read_terms", "unmatched", "save", "to_table", "to_sssom", "to_dataframe",
           "ONTOLOGIES", "MATCH_TYPES", "ontology_info", "__version__"]
