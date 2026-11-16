"""One version source: pankegg/__init__.py. Everything else must agree with it."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pankegg

REPO = Path(__file__).resolve().parent.parent


def test_cli_version():
    out = subprocess.run([sys.executable, str(REPO / "pankegg_make_db.py"), "--version"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == f"pankegg_make_db {pankegg.__version__}"


def test_codemeta_version():
    meta = json.loads((REPO / "codemeta.json").read_text())
    assert meta["version"].lstrip("v") == pankegg.__version__


def test_conda_recipe_reads_package_version():
    recipe = (REPO / "conda.recipe" / "meta.yaml").read_text()
    assert "load_file_regex" in recipe and "pankegg/__init__.py" in recipe
    assert not re.search(r"^\s*version:\s*\"?\d", recipe, re.M), "hard-coded version in meta.yaml"
