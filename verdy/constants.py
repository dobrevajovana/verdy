"""Everything verdy fetches: the web services it asks, the model it downloads, and the ontology
classes it relies on by ID. What each source is and what verdy reads from it: ONTOLOGIES.md.

Every answer is cached on disk (``VERDY_CACHE``, see ``sources``).
"""

# Web services
OLS = "https://www.ebi.ac.uk/ols4/api"                     # OLS4: the OBO ontologies, GOLD, hosts (NCBITaxon)
ENA_API = "https://www.ebi.ac.uk/ena/portal/api"           # ENA Portal API: samples, runs, projects
GBIF_MATCH = "https://api.gbif.org/v1/species/match"       # GBIF Backbone Taxonomy name matcher
WIKIDATA_API = "https://www.wikidata.org/w/api.php"        # Wikidata item search
CF_TABLE = "https://cfconventions.org/Data/cf-standard-names/current/src/cf-standard-name-table.xml"
ART17 = "https://bio.discomap.eea.europa.eu/arcgis/rest/services/Article17/ART17_2019_2024_public/MapServer"

# Downloaded from Hugging Face by sentence-transformers, only with verdy[embeddings] (VERDY_EMBEDDING_MODEL overrides)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# An OBO class's IRI: ENVO:00002046 is OBO + "ENVO_00002046"
OBO = "http://purl.obolibrary.org/obo/"

# Ontology classes used by ID
ECOLOGICAL = "NCBITaxon:410657"     # ecological metagenomes (soil, seawater, air); organismal ones are 410656
