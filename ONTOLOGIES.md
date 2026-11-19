# Ontologies and sources

What verdy matches against, who makes it, and how verdy gets it. Every address verdy fetches from is in
[`verdy/constants.py`](verdy/constants.py).

All answers are cached on disk (`VERDY_CACHE`, default `~/.cache/verdy`), so verdy keeps using the version it
first fetched. Delete the cache folder to fetch the current versions again.

## Ontologies served by OLS4

[OLS4](https://www.ebi.ac.uk/ols4) is EMBL-EBI's Ontology Lookup Service. It loads the latest release of
each ontology; the version it serves is on the ontology's OLS4 page. verdy uses OLS4's search (by label and
synonym), looks classes up by ontology ID, and reads ancestors. Any other OLS4 ontology can be chosen by its
OLS4 name.

| Name in verdy | Ontology | Made by | What it covers |
|---|---|---|---|
| `envo` | [ENVO](http://environmentontology.org/), the Environment Ontology | ENVO community (OBO Foundry) | environments, habitats, ecosystems, environmental materials |
| `gold` | GOLD ecosystem classification | JGI's [GOLD](https://gold.jgi.doe.gov/) database; OLS4 loads the OWL version at [cmungall/gold-ontology](https://github.com/cmungall/gold-ontology) | ecosystem paths such as `Host-associated > Mammals > Digestive system > Large intestine > Fecal` |
| `ncbitaxon` | [NCBITaxon](https://github.com/obophenotype/ncbitaxon) | OBO's ontology version of the NCBI Taxonomy | organisms, and the hosts of samples |
| `pato` | [PATO](https://github.com/pato-ontology/pato/), the Phenotype And Trait Ontology | PATO community | qualities: temperature, salinity, colour, ... |
| `oba` | [OBA](https://github.com/obophenotype/bio-attribute-ontology), the Ontology of Biological Attributes | OBO community | biological attributes and traits |
| `uo` | [UO](https://github.com/bio-ontology-research-group/unit-ontology), the Units of measurement ontology | Bio-Ontology Research Group | units |
| `chebi` | [ChEBI](http://www.ebi.ac.uk/chebi), Chemical Entities of Biological Interest | EMBL-EBI | chemical compounds |
| `obi` | [OBI](http://obi-ontology.org), the Ontology for Biomedical Investigations | OBI community | investigations, assays, instruments |
| `uberon` | [Uberon](http://uberon.org), the Uber-anatomy ontology | Uberon community | anatomy across species |
| `po` | [Plant Ontology](http://browser.planteome.org/amigo) | Planteome | plant anatomy and growth stages |
| `go` | [Gene Ontology](http://geneontology.org/) | GO Consortium | gene product functions, processes, cell parts |

### What verdy reads from GOLD

GOLD's classes on OLS4 carry links to other ontologies. verdy reads these annotations: `env_broad`,
`env_local`, `env_medium`, `anatomical_site`, `has exact match`, `has close match` and `host_taxon`. The links
point to ENVO, UBERON and NCBITaxon classes. For example, the Fecal paths link to UBERON *feces* and UBERON
*large intestine*, so "stool" finds them, and a feces sample falls back to UBERON *feces* when no ENVO class
fits. GOLD has 1,115 paths; reading them takes 4 requests.

### Hosts

A sample's host (`host_tax_id`, `host_scientific_name` or `host` in ENA) is looked up as an NCBITaxon class on
OLS4, with its ancestors. Common names such as "cow" are NCBITaxon synonyms.

### Ontology classes verdy uses by ID

| Class | Used for |
|---|---|
| NCBITaxon:410657, *ecological metagenomes* | an organism under it (soil metagenome, seawater metagenome, ...) with no host keeps the sample out of GOLD's Host-associated paths |
| ENVO's *anthropogenic* classes | a GOLD Engineered path whose ENVO link sits under one of them counts as man-made (activated sludge) |

## Other sources

| Name in verdy | Source | Made by | How verdy gets it |
|---|---|---|---|
| `natura2000` | Natura 2000 habitat types and species, from the Habitats Directive Article 17 report 2019–2024 | European Environment Agency (EEA) | the EEA's public Article 17 map service, read once and searched locally |
| `gbif` | [GBIF Backbone Taxonomy](https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c) | Global Biodiversity Information Facility | GBIF's species name matcher, one request per name |
| `wikidata` | [Wikidata](https://www.wikidata.org) | Wikimedia community | Wikidata's item search, one request per name |
| `cf` | [CF Standard Names](https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html) | CF Conventions committee | the current table, downloaded once (XML) and searched locally |

## Where sample data comes from

ENA IDs (samples, runs, experiments, projects) are looked up in the
[ENA Portal API](https://www.ebi.ac.uk/ena/portal/api/) at EMBL-EBI, 100 IDs to a request. verdy reads the
sample fields listed in the README (environment, isolation source, host, tissue) and a few more for context
(title, description, host taxon ID, project title).

## Embedding model

With `verdy[embeddings]`, the [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
model is downloaded from Hugging Face by sentence-transformers the first time it is used.
`VERDY_EMBEDDING_MODEL` chooses another.
