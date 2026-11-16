"""The generate_input_sourmash_tax_*.sh helper scripts (decision P6) produce a CSV that builds."""

import shutil
import subprocess

import pytest

from tests.helpers import FIX, REPO, run_make_db

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def layout(root, by_tool):
    def d(kind):
        p = root / "Dir" / kind / "S1" if by_tool else root / "Dir" / "S1" / kind
        p.mkdir(parents=True, exist_ok=True)
        return p
    for f in (FIX / "s1" / "eggnog").iterdir():
        shutil.copy(f, d("eggnog") / f.name)
    cls = d("sourmash")
    for f in (FIX / "sourmash_tax_genome").glob("S1.bin*.classifications.csv"):
        shutil.copy(f, cls / f.name)
    shutil.copy(FIX / "s1" / "checkm2" / "S1_checkm2_report.tsv", d("checkm2") / "quality_report.tsv")


@pytest.mark.parametrize("script, by_tool", [("generate_input_sourmash_tax_by_sample.sh", False),
                                             ("generate_input_sourmash_tax_by_tool.sh", True)])
def test_tax_genome_helper_script(tmp_path, script, by_tool):
    layout(tmp_path, by_tool)
    subprocess.run(["bash", str(REPO / script)], cwd=tmp_path, check=True)
    lines = (tmp_path / "samples.csv").read_text().splitlines()
    assert lines[0] == "Sample name,Annotation_dir,classification_dir,Checkm2_dir"
    assert len(lines) == 2 and lines[1].startswith("S1,")
    run_make_db(tmp_path / "samples.csv", tmp_path / "out", "t", "--classification", "sourmash_tax", cwd=tmp_path)
