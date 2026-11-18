<p align="center"><img src="https://raw.githubusercontent.com/dobrevajovana/verdy/main/logo.png" width="200" alt="VERDY logo: a green forest spirit with a flower crown, braided leafy hair and berry nodes linked by vines"></p>

# VERDY

[![PyPI](https://img.shields.io/pypi/v/verdy)](https://pypi.org/project/verdy/)
[![Python package](https://github.com/dobrevajovana/verdy/actions/workflows/python-package.yml/badge.svg)](https://github.com/dobrevajovana/verdy/actions/workflows/python-package.yml)

*Part of **VERDANT**: **V**ocabulary **E**nrichment & **R**esolution of **D**iversity **A**nnotations via **N**eural **T**echnology
(BioHackathon Europe 2026).*

**Meet VERDY, your warrior for ontology matching.** Give it your ENA IDs or free text, choose the ontologies, and it predicts the matching ontology classes in each.

1. **Input:** a file (or Python list) of ENA IDs and/or free text. The IDs can be samples, runs or projects. The free text can be species, habitats, parameters or measurement names.
2. **Terms:** each ENA ID is looked up in [ENA](https://www.ebi.ac.uk/ena/portal/api), and each organism and environment field of its sample (`scientific_name`, `broad_scale_environmental_context`, `local_environmental_context`, `environmental_medium`, ...) becomes a term. Free text is one term as it is.
   A typed ID (`soil [ENVO:00001998]`) is a match in its own ontology when its label fits the words beside it.
3. **Search:** every term is searched in each ontology you choose (for example `natura2000`, `gold`, `envo`).
4. **Output:** a file with the exact match, or the most closely related matches, per term and ontology.

### Words used by this tool and the codebase

| word | means | in the output |
|---|---|---|
| **input** | one ENA ID or one line of free text you give VERDY | |
| **ENA ID** | an ENA sample, run or project accession (`SAMD00132352`, `ERR9966617`, `PRJEB54740`) | |
| **term** | one text to match: a free-text input as it is, or one field value of an ENA sample | `term`; `term_id` is its sample (or your ID for it, or the text itself); `category` the ENA field it came from |
| **ontology class** | an entry in an ontology, with an ontology ID, a label and synonyms | |
| **ontology ID** | a class's short identifier, `ENVO:00001998` | `match_curie` (its full web address, the IRI, is `match_id`) |
| **label** | a class's name, `soil` | `match_label` |
| **typed ID** | an ontology ID written inside a term: `soil [ENVO:00001998]` | |
| **candidate** | an ontology class a search returned for a term | |
| **match** | a candidate (or typed ID) kept for a term, with its match type and confidence | one row |
| **rank** | a match's place among one term's matches in one ontology | `rank` |

```python
import verdy

matches = verdy.match("my_input.csv", ontologies=["natura2000", "gold", "envo", "ncbitaxon"])
verdy.save(matches, "my_input.matches.csv")      # .csv  .tsv  .sssom.tsv  .json  .xlsx
```

```
verdy my_input.csv -o natura2000,gold,envo --out my_input.matches.csv
```

## Install

```
pip install verdy
pip install "verdy[excel]"     # to read and write Excel
pip install "verdy[embeddings]"   # to also compare by embedding similarity (SentenceTransformers, cosine)
pip install git+https://github.com/dobrevajovana/verdy.git    # the latest, unreleased version
```

Python 3.10 or newer; the only dependency is `requests`.

## Input

`verdy.match` takes a CSV / TSV / Excel file, a text file with one input per line, a Python list or a pandas DataFrame.
The column is found by its header (`name`, `term`, `parameter`, `species`, ..., or `id`, `accession`, `sample_accession`, `run_accession`)
or given with `column="..."`. One file can mix both kinds of input:

| input | what happens |
|---|---|
| `SAMD00132352`, `SAMEA...`, `SAMN...`, `ERS...` | an ENA sample: its fields are looked up in ENA and each field value is a term |
| `ERR9966617`, `SRR...`, `ERX...` | a run or experiment: its sample, as above |
| `PRJEB54740`, `PRJNA...`, `ERP...`, `SRP...` | a project: all its samples (those without runs too), each term under the sample's own accession |
| anything else | free text: one term, searched as it is (units in brackets, underscores and a leading code are set aside) |

The fields searched are `verdy.SAMPLE_FIELDS`: the organism, the environment fields, `isolation_source`, `host`,
`host_scientific_name`, `host_body_site` and `tissue_type`. `fields=` chooses others (see ENA's `returnFields?result=sample`).
ENA is asked in bulk: samples and runs 100 to a request, each project in one request. Every answer is cached
(`VERDY_CACHE`, default `~/.cache/verdy`) by the fields asked for, so a rerun asks ENA nothing.

ENA's other words about a sample (`verdy.CONTEXT_FIELDS`: `host_tax_id`, `sample_title`, `sample_description`,
`description`, and for a project its `study` and `study_title`) are read too but not searched: long free text
finds noise on its own. They are kept with each term as `context`, to choose among a sample's matches.
`verdy.samples(ids)` shows what ENA says about many IDs at once.

A sample's host is looked up as an NCBITaxon class with its ancestors, from OLS4 (`host_tax_id` first, then
`host_scientific_name`, then `host`; common names such as "cow" or "honey bee" are NCBITaxon synonyms), and kept
in `context` as `host_taxon`. `verdy.host({"host": "cow"})` gives *Bos taurus*, whose ancestors include Mammalia.
After a run, `verdy.match.unresolved` lists the ENA IDs ENA did not know.

## The ontologies

`verdy.ONTOLOGIES` (or `verdy --list`):

| ID | What | For |
|---|---|---|
| `natura2000` | Natura 2000 habitat types and species (EEA Article 17 lists, fetched live) | habitats by name or code, protected species |
| `envo` | Environment Ontology | habitats, environments, materials, environmental measurements |
| `gold` | GOLD ecosystem classification (whole paths, from OLS4; see below) | sample ecosystems |
| `ncbitaxon` | NCBI Taxonomy | organisms |
| `gbif` | GBIF Backbone Taxonomy | organisms |
| `pato` | Phenotype And Trait Ontology | qualities: temperature, salinity, humidity, ... |
| `oba` | Ontology of Biological Attributes | traits and measurable attributes |
| `cf` | CF Standard Names | climate, weather and ocean variables |
| `uo` | Units of measurement | units |
| `chebi` | Chemical Entities of Biological Interest | chemicals |
| `obi` | Ontology for Biomedical Investigations | assays, instruments, protocols |
| `uberon`, `po`, `go` | anatomy, plants, biological processes | |
| `wikidata` | Wikidata | anything with a name |

**GOLD** classifies where a sample comes from as a path, such as
`Host-associated > Mammals > Digestive system > Large intestine > Fecal`. VERDY reads every GOLD path from OLS4
with what GOLD links it to: its environment and body site (ENVO, or UBERON for body materials), its curated
exact and close matches, and for host-associated paths its host (an NCBITaxon class). A level is also called by
the labels and synonyms of the classes it links to, so `stool` finds `…> Fecal` through UBERON *feces*,
though GOLD itself never says "stool". `verdy.gold.load()` gives the whole model; its `host_fits(path, host)` says
whether a host (from `verdy.host`) is one a path allows. Nothing in it is written by hand. The first build
takes about half a minute; then it is cached.

**Any other ontology in [OLS4](https://www.ebi.ac.uk/ols4/ontologies) works as well:** pass its name there
(for example `foodon`, `pco` or `ms`).

## What comes out

One row per match:

| column | |
|---|---|
| `term_id`, `term`, `category` | the term: its sample (or your ID), its text, and the ENA field it came from |
| `match_type` | `skos:exactMatch`: a label or synonym is the term (plurals and `sp.` aside) · `skos:closeMatch`: most words shared · `skos:relatedMatch`: some words shared |
| `ontology`, `match_curie`, `match_id`, `match_label` | the matched ontology class: its ontology, ontology ID, IRI and label |
| `confidence` | 1.0 exact as written, 0.95 exact up to plurals, then by word overlap |
| `method` | how it was found: `ID` (a typed ID, or a Natura 2000 code), `ontology name` (the class's label or synonyms), `cosine` (embedding similarity gave the confidence) |
| `cosine` | embedding similarity (0..1) with `verdy[embeddings]` installed; empty otherwise. A match is kept on it from `min_cosine` (default 0.60); from 0.80 it is a closeMatch. Cosine never makes an exactMatch, and is not used for a candidate that says more than the term (`water`: *tap water*) |
| `word_overlap`, `rank` | how many words they share (0..1), and the match's place among this term's matches in this ontology: by confidence, a typed ID first on a tie |
| `definition` | the class's definition (units first, for CF) |
| `searched_for` | the term after cleaning (without units, codes or typed IDs) |
| `why` | in words, on every match: `ID in the text` (or why a typed ID was not trusted: its label says more than, or something other than, the term), `its Annex I code`, `the label or a synonym is the term` (`, plurals aside`), `word overlap 0.5`, `cosine 0.86 (word overlap 0.5)`; and `cosine not used: … says more than the term` for a narrower candidate |

`verdy.unmatched(inputs, matches, ontologies)` lists, per ontology, the terms it found nothing for.

## Example

`python examples/predict.py` runs [examples/input.csv](examples/input.csv), which has three ENA IDs and four free-text inputs, against
Natura 2000, GOLD, ENVO, NCBITaxon, PATO and CF. It writes [examples/input.matches.csv](examples/input.matches.csv). Part of the result:

| input | term (from) | ontology | match |
|---|---|---|---|
| SAMD00132352 | urban biome (broad_scale_environmental_context) | ENVO | exactMatch ENVO:01000249 urban biome |
| SAMD00132352 | air (local_environmental_context, environmental_medium) | ENVO · GOLD | exactMatch ENVO:00002005 air · GOLD:Air |
| SAMD00132352 | air metagenome (scientific_name) | NCBITaxon | exactMatch NCBITaxon:655179 |
| ERR9966617 | temperate forest | ENVO | exactMatch ENVO:01001805 temperate forest |
| ERR9966617 | mountain | ENVO | exactMatch ENVO:00000081 mountain |
| SAMEA110429224 | Human (host_scientific_name) | NCBITaxon | exactMatch NCBITaxon:9606 Homo sapiens |
| Lynx lynx | | Natura 2000 · NCBITaxon | exactMatch n2k:1361 · NCBITaxon:13125 |
| Atlantic salt meadows | | Natura 2000 | exactMatch n2k:1330 |
| air_temperature | | CF · ENVO | exactMatch CF:air_temperature · ENVO:09200001 temperature of air |
| salinity | | PATO | exactMatch PATO:0085001 |

## One GOLD path and one ENVO class per sample

For samples (ENA IDs), `verdy.match.samples` holds one row per sample after `verdy.match`, with one match per
chosen ontology side by side. Its GOLD path and ENVO class are chosen from all its fields, its title and
descriptions, its study's title and its host together; any other ontology gives the sample's best match in it.
Each has `match_type`, `confidence`, `method` and `why`.

```python
verdy.save_samples(verdy.match.samples, "my_input.samples.csv")    # .csv  .tsv  .json  .xlsx
```

On the command line, `--out results.csv` also writes `results.samples.csv` when the input has samples. Its columns:
`sample`, `input`, `study`, `study_title`, `host`, `evidence`, `status` (`matched`, `no match in …`, `no match`),
then for each chosen ontology `<ontology>_id`, `_label`, `_match_type`, `_confidence`, `_method`, `_why`.

- **GOLD** is scored level by level along each whole path. The level naming a host must contain the sample's
  host (a cow's feces go to `Host-associated > Mammals > … > Fecal`, a chicken's to `… > Birds > … > Fecal`).
  Host-associated needs a host or a name never used under Environmental; Engineered needs the kind of engineering
  (`Lab enrichment`, `Wastewater`, …) or a level ENVO places under an anthropogenic class. A sample whose organism
  NCBITaxon calls an ecological metagenome (soil, seawater) is not put under a host by a word in its free text,
  and that organism's name counts as what was sampled. When the host is unknown and several fit (feces, no host),
  or paths still tie, the class they share is given as a `broadMatch` (method `shared parent`).
- **ENVO** is the class naming host and material together, else a confident match from the environment fields
  that GOLD's chosen path links to, else by field (medium first); never a biome for a host's sample. Failing
  those, the medium GOLD's path links to (method `GOLD medium`: UBERON *feces* for a Fecal path).

Methods: `ID` (a typed ID), `ontology name` (a label or synonym), `crosswalk` (GOLD reached from the sample's
ENVO class through GOLD's curated matches), `shared parent`, `GOLD medium`.

## Progress

The command line draws a bar for each slow stage. In Python, pass `progress=verdy.ProgressBar()` (and call its
`close()` after), or your own `progress(stage, done, total)` function; `done` and `total` are `None` while a stage
can't count.

```
Looking up ENA IDs         [##############################] 3/3
Looking up hosts           [##############################] 1/1
Reading GOLD               [##############################] 507/507
Searching the ontologies   [##############################] 39/39
```

## One term at a time

```python
verdy.search("cloud liquid water content", "cf")    # the ontology's candidates, best first
verdy.resolve("SAMD00132352")                      # what ENA says about an ID
verdy.read_terms("my_input.csv")                    # what VERDY read from your file
verdy.to_dataframe(matches)                         # pandas
```

## Tests and development

```
pip install verdy                 # to use it: only requests
pip install -e ".[test]"          # to run the tests: adds pytest
pip install -e ".[dev]"           # to work on it: the tests and pre-commit
pre-commit install                # then black, isort, flake8 and ruff check every commit
python -m pytest -q
pre-commit run --all-files        # every check on every file
```

The tests stub every web service, so they run offline. The checks' settings (line length 120) are in
`pyproject.toml` and `.flake8`.

## Licence

MIT, see [LICENSE](LICENSE).
