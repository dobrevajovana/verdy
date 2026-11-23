"""What the fake web services answer in the tests, one section per service (conftest.py reads them)."""

from verdy.constants import GOLD_PATH, GOLD_VOCAB, OBO

ENVO, TAXON, PATO, UBERON = OBO + "ENVO_", OBO + "NCBITaxon_", OBO + "PATO_", OBO + "UBERON_"

# Real ENA samples
AIR, SOIL, COW, CAT, SLUDGE = "SAMEA104135898", "SAMEA104135884", "SAMN13091181", "SAMD00659239", "SAMD00444474"
ENA = {"sample": [
    # air and soil, both in project PRJEB21441
    {"sample_accession": AIR, "secondary_sample_accession": "ERS1794916", "study_accession": "PRJEB21441",
     "scientific_name": "air metagenome", "broad_scale_environmental_context": "urban biome",
     "local_environmental_context": "city", "environmental_medium": "air", "environment_biome": "urban biome",
     "environment_feature": "city", "environment_material": "air", "host_scientific_name": "Not applicable",
     "sample_title": "1521.Chi.1.s.8.1.sequences", "sample_description": "air sample Chi.1",
     "description": "air sample Chi.1"},
    {"sample_accession": SOIL, "secondary_sample_accession": "ERS1794902", "study_accession": "PRJEB21441",
     "scientific_name": "soil metagenome", "broad_scale_environmental_context": "forest biome",
     "local_environmental_context": "forest", "environmental_medium": "soil", "environment_biome": "forest biome",
     "environment_feature": "forest", "environment_material": "soil", "host_scientific_name": "Not applicable",
     "sample_title": "1521.CF3.s.6.1.sequences", "sample_description": "soil sample CF3",
     "description": "soil sample CF3"},
    # cow feces, the host by its taxon ID
    {"sample_accession": COW, "secondary_sample_accession": "SRS5634417", "study_accession": "PRJNA579572",
     "scientific_name": "gut metagenome", "isolation_source": "Cow feces", "host": "Bos taurus",
     "host_scientific_name": "Bos taurus", "host_tax_id": "9913",
     "sample_title": "Metagenome or environmental sample from gut metagenome",
     "sample_description": "Metagenome or environmental sample from gut metagenome",
     "description": "Metagenome or environmental sample from gut metagenome"},
    # feces with no host given (only the title names the cat)
    {"sample_accession": CAT, "secondary_sample_accession": "DRS362558", "study_accession": "PRJDB17088",
     "scientific_name": "feces metagenome", "broad_scale_environmental_context": "subtropical forests",
     "environmental_medium": "feces", "environment_biome": "subtropical forests", "environment_material": "feces",
     "sample_title": "Iriomote cat fecal sample in summer 10", "sample_description": "Keywords: GSC:MIxS MIMS:6.0",
     "description": "Keywords: GSC:MIxS MIMS:6.0"},
    # lab-scale activated sludge; the organism is a worm living in it
    {"sample_accession": SLUDGE, "secondary_sample_accession": "DRS229742", "study_accession": "PRJDB13106",
     "scientific_name": "Monopylephorus rubroniveus", "broad_scale_environmental_context": "activated sludge",
     "local_environmental_context": "lab-scale activated sludge at Ritumeikan University",
     "environmental_medium": "water", "environment_biome": "activated sludge",
     "environment_feature": "lab-scale activated sludge at Ritumeikan University", "environment_material": "water",
     "sample_title": "Monopylephorus rubroniveus WR", "sample_description": "Keywords: GSC:MIxS MIGS:6.0",
     "description": "Keywords: GSC:MIxS MIGS:6.0"}],
    "read_run": [{"run_accession": "ERR2012938", "experiment_accession": "ERX2072610", "sample_accession": AIR}],
    "study": [{"study_accession": "PRJEB21441", "secondary_study_accession": "ERP023684",
               "study_title": "Samples presented at EMP conference June 2011 Shenzhen"}]}

# OLS4 search: the candidates for (ontology, text searched). Anything else finds nothing.

OLS_SEARCH = {
    ("envo", "estuary"): [{"iri": ENVO + "00000045", "label": "estuary", "obo_id": "ENVO:00000045"}],
    ("envo", "lagoon"): [{"iri": ENVO + "00000038", "label": "lagoon", "obo_id": "ENVO:00000038"}],
    ("envo", "coastal"): [{"iri": ENVO + "1", "label": "coastal water", "obo_id": "ENVO:1"}],
    ("envo", "water"): [{"iri": ENVO + "2", "label": "tap water", "obo_id": "ENVO:2"}],     # narrower than the term
    ("envo", "activated sludge"): [{"iri": ENVO + "00002046", "label": "activated sludge", "obo_id": "ENVO:00002046",
                                    "is_defining_ontology": True}],
    ("envo", "urban biome"): [{"iri": ENVO + "01000249", "label": "urban biome", "obo_id": "ENVO:01000249",
                               "is_defining_ontology": True}],
    ("envo", "air"): [{"iri": ENVO + "00002005", "label": "air", "obo_id": "ENVO:00002005", "is_defining_ontology": True}],
    ("ncbitaxon", "lynx lynx"): [{"iri": TAXON + "13125", "label": "Lynx lynx", "obo_id": "NCBITaxon:13125"}],
    ("ncbitaxon", "cow"): [{"iri": TAXON + "9913", "label": "Bos taurus", "obo_id": "NCBITaxon:9913", "synonym": ["cow"]}],
    ("ncbitaxon", "bos taurus"): [{"iri": TAXON + "9913", "label": "Bos taurus", "obo_id": "NCBITaxon:9913",
                                   "synonym": ["cow"]}],
    ("ncbitaxon", "mammals"): [{"iri": TAXON + "40674", "label": "Mammalia", "obo_id": "NCBITaxon:40674"}],
    ("ncbitaxon", "fish"): [{"iri": TAXON + "7777", "label": "Chondrichthyes", "obo_id": "NCBITaxon:7777"},   # one name,
                            {"iri": TAXON + "7898", "label": "Actinopterygii", "obo_id": "NCBITaxon:7898"}],  # two classes
    ("ncbitaxon", "algae"): [{"iri": TAXON + "2763", "label": "Rhodophyta", "obo_id": "NCBITaxon:2763"}],
    ("ncbitaxon", "estuaries"): [{"iri": TAXON + "1", "label": "estuaries bacterium"}],        # a near name, not it
    ("pato", "temperature"): [{"iri": PATO + "0000146", "label": "temperature", "obo_id": "PATO:0000146"}],
    ("gold", "air"): [{"iri": GOLD_PATH + "3962", "label": "Environmental > Air > Outdoor Air", "is_defining_ontology": False},
                      {"iri": GOLD_VOCAB + "Air", "label": "Air", "is_defining_ontology": False}],   # not a path
}

# OLS4 lookup of a class by its ontology ID. ENVO:99999999 is missing on purpose: an ID OLS4 does not know.

OLS_TERMS = {
    "ENVO:00001998": {"iri": ENVO + "00001998", "label": "soil", "ontology_name": "envo", "synonyms": []},
    "ENVO:01000024": {"iri": ENVO + "01000024", "label": "marine benthic biome", "ontology_name": "envo"},
    "ENVO:00000045": {"iri": ENVO + "00000045", "label": "estuary", "ontology_name": "envo"},
    "ENVO:00002005": {"iri": ENVO + "00002005", "label": "air", "ontology_name": "envo"},
    "ENVO:00002046": {"iri": ENVO + "00002046", "label": "activated sludge", "ontology_name": "envo"},
    "NCBITaxon:9913": {"iri": TAXON + "9913", "label": "Bos taurus", "ontology_name": "ncbitaxon",
                       "synonyms": ["cow", "domestic cattle"]},
    "UBERON:0001988": {"iri": UBERON + "0001988", "label": "feces", "ontology_name": "uberon",
                       "synonyms": ["faeces", "stool", "dung"]},
    "UBERON:0000059": {"iri": UBERON + "0000059", "label": "large intestine", "ontology_name": "uberon"},
}

# OLS4 ancestors of a class, by IRI (OLS4 gives them in no order). Real IDs, a shortened list.

ANCESTORS = {
    TAXON + "9913": [{"id": "NCBITaxon:9903", "label": "Bos"}, {"id": "NCBITaxon:9895", "label": "Bovidae"},
                     {"id": "NCBITaxon:40674", "label": "Mammalia"}, {"id": "NCBITaxon:32525", "label": "Theria <mammals>"},
                     {"id": "NCBITaxon:33208", "label": "Metazoa"}, {"id": "NCBITaxon:2759", "label": "Eukaryota"}],
    ENVO + "00002046": [{"id": "ENVO:00002044", "label": "sludge"},
                        {"id": "ENVO:0010001", "label": "anthropogenic environmental material"}],
}

# OLS4 details of an ontology: its ID prefix. Any other ontology is unknown.

OLS_ONTOLOGIES = {"envo": "ENVO", "ncbitaxon": "NCBITaxon", "pato": "PATO", "gold": "GOLD"}

# OLS4's GOLD: (IRI, label, links) as OLS4 gives them. Fish states one host class, Algae none.

GOLD = [
    (GOLD_PATH + "1", "Host-associated", {}),
    (GOLD_PATH + "2", "Host-associated > Mammals", {"host_taxon": [TAXON + "40674"]}),
    (GOLD_PATH + "3", "Host-associated > Mammals > Digestive system > Large intestine",
     {"host_taxon": [TAXON + "40674"], "anatomical_site": [UBERON + "0000059"]}),
    (GOLD_PATH + "4", "Host-associated > Mammals > Digestive system > Large intestine > Fecal",
     {"host_taxon": [TAXON + "40674"], "anatomical_site": [UBERON + "0000059"], "env_medium": [UBERON + "0001988"]}),
    (GOLD_PATH + "5", "Host-associated > Fish", {"host_taxon": [TAXON + "7777"]}),
    (GOLD_PATH + "6", "Host-associated > Fish > Skin", {"host_taxon": [TAXON + "7777"]}),
    (GOLD_PATH + "7", "Host-associated > Algae", {}),
    (GOLD_PATH + "11", "Host-associated > Birds", {"host_taxon": [TAXON + "8782"]}),
    (GOLD_PATH + "12", "Host-associated > Birds > Digestive system > Fecal",
     {"host_taxon": [TAXON + "8782"], "env_medium": [UBERON + "0001988"]}),
    (GOLD_PATH + "8", "Engineered > Lab enrichment > Feces", {"env_medium": [UBERON + "0001988"]}),
    (GOLD_PATH + "13", "Engineered > Wastewater", {}),
    (GOLD_PATH + "14", "Engineered > Wastewater > Activated Sludge", {"env_medium": [ENVO + "00002046"]}),
    (GOLD_PATH + "9", "Environmental > Air", {"env_medium": [ENVO + "00002005"]}),
    (GOLD_PATH + "10", "Environmental > Air > Outdoor Air", {"env_medium": [ENVO + "00002005"]}),
    (GOLD_VOCAB + "Air", "Air", {}),                                                    # a level's name, not a path
]

# GBIF name matcher, by name. Any other name: no match.

GBIF = {"Lynx lynx": {"usageKey": 2435240, "canonicalName": "Lynx lynx", "matchType": "EXACT"}}


# Wikidata item search, by name. Any other name finds the decoy, whose alias only contains the words.

WIKIDATA = {"Lynx lynx": [{"id": "Q43375", "label": "Eurasian lynx", "aliases": ["Lynx lynx"]}]}
WIKIDATA_DECOY = [{"id": "Q9", "label": "some moth", "aliases": ["coastal lagoons moth"]}]


# Natura 2000 (EEA Article 17 service): layer 5 holds the habitat types, the others the species.

NATURA2000_HABITATS = [{"reference_habitatlist.habitat_code": "1130", "reference_habitatlist.label": "Estuaries"}]
NATURA2000_SPECIES = [{"reference_specieslist.species_code": "1361", "reference_specieslist.species_name": "Lynx lynx",
                       "reference_specieslist.taxonomical_group": "Mammals"}]

# The CF Standard Names table: two names and one alias.

CF = b"""<?xml version="1.0"?><standard_name_table>
<entry id="air_temperature"><canonical_units>K</canonical_units><description>Air temperature is the bulk temperature of the air.</description></entry>
<entry id="wind_speed"><canonical_units>m s-1</canonical_units><description>Speed is the magnitude of velocity.</description></entry>
<alias id="surface_air_temperature"><entry_id>air_temperature</entry_id></alias>
</standard_name_table>"""
