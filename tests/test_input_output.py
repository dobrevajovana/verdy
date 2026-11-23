"""Terms read from files and lists; matches written as CSV, TSV, JSON and SSSOM; the command line."""

import csv
import json

import pytest
from fake_data import ENVO

import verdy


def test_read_terms_from_many_inputs(tmp_path):
    (tmp_path / "a.csv").write_text("id,Parameter,group\nx1,air temperature (°C),parameter\nx2,Estuaries,habitat\nx2,again,habitat\n")
    (tmp_path / "b.txt").write_text("Lynx lynx\n\nEstuaries\n")
    (tmp_path / "c.tsv").write_text("code\tlabel\n1130\tEstuaries\n")
    assert verdy.read_terms(tmp_path / "a.csv") == [
        {"id": "x1", "label": "air temperature (°C)", "category": "parameter"}, {"id": "x2", "label": "Estuaries", "category": "habitat"}]
    assert [t["label"] for t in verdy.read_terms(tmp_path / "b.txt")] == ["Lynx lynx", "Estuaries"]
    assert verdy.read_terms(tmp_path / "c.tsv")[0] == {"id": "1130", "label": "Estuaries", "category": None}
    assert [t["id"] for t in verdy.read_terms(["Lynx lynx", {"name": "Coastal lagoons"}])] == ["lynx_lynx", "coastal_lagoons"]
    with pytest.raises(ValueError):
        verdy.read_terms(tmp_path / "a.csv", column="nope")


def test_outputs(services, tmp_path):
    ms = verdy.match(["Lynx lynx", "Estuaries"], ["envo", "ncbitaxon"])
    for f in ("m.csv", "m.tsv", "m.json", "m.sssom.tsv"):
        verdy.save(ms, tmp_path / f)
    rows = list(csv.DictReader(open(tmp_path / "m.csv")))
    assert {r["match_curie"] for r in rows} == {"ENVO:00000045", "NCBITaxon:13125"}
    assert json.loads((tmp_path / "m.json").read_text()) == ms
    sssom = (tmp_path / "m.sssom.tsv").read_text()
    assert "semapv:LexicalMatching" in sssom and f"#   ENVO: {ENVO}" in sssom


def test_command_line(services, tmp_path, capsys):
    from verdy.__main__ import main
    (tmp_path / "n.csv").write_text("name\nLynx lynx\nEstuaries\n")
    assert main(["--list"]) == 0 and "ncbitaxon" in capsys.readouterr().out
    assert main([str(tmp_path / "n.csv"), "-o", "envo,ncbitaxon", "--out", str(tmp_path / "o.csv")]) == 0
    err = capsys.readouterr().err
    assert "2 matches for 2 of 2 inputs" in err and "nothing in envo for: Lynx lynx" in err
    assert (tmp_path / "o.csv").exists()
