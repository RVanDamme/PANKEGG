"""Build small PANKEGG inputs in a temporary directory and run pankegg_make_db on them."""

import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures"

LCA_HEADER = "ID,status,superkingdom,phylum,class,order,family,genus,species,strain\n"
ECOLI = ("d__Bacteria,p__Pseudomonadota,c__Gammaproteobacteria,o__Enterobacterales,"
         "f__Enterobacteriaceae,g__Escherichia,s__Escherichia coli,")
CHECKM2_HEADER = "Name\tCompleteness\tContamination\n"
# Real legacy (one '##' line) eggNOG files cut from the OSF example data.
EGGNOG_SOURCES = sorted((FIX / "s1" / "eggnog").glob("*.emapper.annotations"))


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def run_make_db(csv_path, out_dir, name="test", *extra, cwd=None, check=True):
    cmd = [sys.executable, str(REPO / "pankegg_make_db.py"), "-i", str(csv_path),
           "-o", name, "--output_dir", str(out_dir), *extra]
    res = subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True)
    if check:
        assert res.returncode == 0, f"{cmd} exited {res.returncode}\n{res.stdout}\n{res.stderr}"
    return res


def bins_table(db_path):
    """{(sample, bin): (completeness, contamination, genus or None)}"""
    con = sqlite3.connect(db_path)
    rows = con.execute(
        """SELECT s.sample_name, b.bin_name, b.completeness, b.contamination, t._genus_
           FROM bin b JOIN sample s ON s.id=b.sample_id
           LEFT JOIN taxonomy t ON t.id=b.taxonomic_id""").fetchall()
    con.close()
    return {(r[0], r[1]): r[2:] for r in rows}
