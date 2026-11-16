"""pankegg_make_db stores KEGG module completeness per bin (phase 2, A9)."""

import sqlite3

from pankegg import resource_path
from pankegg.modules import ModuleSet, load_modules
from tests.helpers import FIX, run_make_db, write


def build(tmp_path):
    csv_path = write(tmp_path / "samples.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"S1,{FIX}/s1/eggnog/*.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                     f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n")
    run_make_db(csv_path, tmp_path / "out", "t", "--quiet")
    return sqlite3.connect(tmp_path / "out" / "t.db")


def test_module_tables(tmp_path):
    con = build(tmp_path)
    modules = load_modules(resource_path("data", "kegg_modules.tsv"))
    stored = {r[0]: r[1:] for r in con.execute("SELECT module_number, module_name, definition, steps_total FROM module")}
    assert set(stored) == set(modules)
    assert stored["M00001"][0].startswith("Glycolysis") and stored["M00001"][2] == 9

    mset = ModuleSet(modules)
    n_rows = 0
    for bin_id, bin_name in con.execute("SELECT id, bin_name FROM bin").fetchall():
        kos = {r[0] for r in con.execute(
            "SELECT k.ko_id FROM bin_extra_kegg ek JOIN bin_extra e ON e.id=ek.extra_id "
            "JOIN kegg k ON k.id=ek.kegg_id WHERE e.bin_id=?", (bin_id,))}
        expected = mset.completeness(kos)
        got = {r[0]: r[1:] for r in con.execute(
            "SELECT m.module_number, bm.steps_complete, bm.steps_total, bm.completeness FROM bin_module bm "
            "JOIN module m ON m.id=bm.module_id WHERE bm.bin_id=?", (bin_id,))}
        assert got == expected, bin_name
        n_rows += len(got)
    assert n_rows > 0, "the fixture bins carry KOs of at least one module"
    assert con.execute("SELECT COUNT(*) FROM bin_module WHERE completeness <= 0 OR completeness > 100").fetchone()[0] == 0
    con.close()
