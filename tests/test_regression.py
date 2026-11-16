"""Regression: databases built now must match what PANKEGG 2.0.0 built.

The references were produced in step 1 of the update (docs/dev/PROGRESS.md)
with the unchanged 2.0.0 code and are compared by names, not row IDs.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.regression.summarise_db import summarise

REPO = Path(__file__).resolve().parent.parent
REG = REPO / "tests" / "regression"
FIX = REPO / "tests" / "fixtures"


def build(csv_path, out_dir, name, *extra, cwd=REPO):
    cmd = [sys.executable, str(REPO / "pankegg_make_db.py"), "-i", str(csv_path),
           "-o", name, "--output_dir", str(out_dir), *extra]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert res.returncode == 0, f"{cmd} failed:\n{res.stdout}\n{res.stderr}"
    return Path(out_dir) / f"{name}.db"


def test_s1_lca_matches_2_0_0(tmp_path):
    db = build(FIX / "db_2.0.0" / "s1_lca_input.csv", tmp_path, "s1")
    expected = json.loads((FIX / "db_2.0.0" / "s1_lca_2.0.0.json").read_text())
    assert summarise(db) == expected


@pytest.mark.osf
@pytest.mark.parametrize("mode, extra", [
    ("sourmash", []),                                       # 2.0.0 command line
    ("gtdbtk", ["--gtdbtk"]),                               # 2.0.0 command line
    ("sourmash", ["--classification", "sourmash_lca"]),
    ("gtdbtk", []),                                         # auto-detected
], ids=["sourmash", "gtdbtk-flag", "sourmash-explicit", "gtdbtk-auto"])
def test_osf_example_matches_2_0_0(tmp_path, test_data_dir, mode, extra):
    db = build(test_data_dir / f"{mode}_example.csv", tmp_path, mode, *extra,
               cwd=test_data_dir.parent)
    expected = json.loads((REG / f"osf_{mode}_2.0.0.json").read_text())
    assert summarise(db) == expected
