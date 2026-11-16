"""Clean-install tests (brief §5, acceptance criterion 1; finding F1).

Build the wheel, install it into a fresh virtual environment, change to a
directory that contains only the input files, and run the installed console
scripts. Nothing from the repository checkout may be importable there.

Runs offline: wheels are built without build isolation and installed with
--no-deps; the full package reuses the web stack of the test interpreter
through --system-site-packages.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures"

pytestmark = pytest.mark.install


def run(cmd, cwd=None, env=None, check=True):
    res = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise AssertionError(f"{cmd} exited {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
    return res


def clean_env():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env["PIP_NO_INDEX"] = "1"
    return env


def clean_source_copy(dest):
    """Copy of the source tree without build leftovers: a stale in-tree build/
    directory would otherwise leak old files into the wheel."""
    shutil.copytree(REPO, dest, ignore=shutil.ignore_patterns(
        ".git", "build", "dist", "*.egg-info", "__pycache__", ".pytest_cache", "tests", "docs", "paper"))
    return dest


def build_wheel(dist, kind):
    dist.mkdir(parents=True, exist_ok=True)
    if kind == "full":
        src = clean_source_copy(dist.parent / "src")
        run([sys.executable, "-m", "pip", "wheel", src, "--no-deps", "--no-build-isolation", "-w", dist],
            env=clean_env())
        pattern = "pankegg-*.whl"
    else:
        run([sys.executable, REPO / "tools" / "build_makedb.py", "--wheel-only", "--outdir", dist], env=clean_env())
        pattern = "pankegg_makedb-*.whl"
    wheels = sorted(dist.glob(pattern))
    assert len(wheels) == 1, f"expected one {pattern} in {dist}, found {wheels}"
    return wheels[0]


def make_venv(path, system_site_packages):
    venv.EnvBuilder(with_pip=True, system_site_packages=system_site_packages, clear=True).create(path)
    bindir = path / ("Scripts" if os.name == "nt" else "bin")
    return bindir


def prepare_inputs(work):
    """A working directory holding only the inputs, referenced by relative paths."""
    work.mkdir()
    shutil.copytree(FIX / "s1", work / "s1")
    shutil.copytree(FIX / "sourmash_lca", work / "lca")
    (work / "samples.csv").write_text(
        "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
        "S1,s1/eggnog/*.emapper.annotations,lca/*.lca.csv,s1/checkm2/S1_checkm2_report.tsv\n"
    )


def check_make_db(bindir, work, env):
    exe = bindir / "pankegg_make_db"
    version = run([exe, "--version"], cwd=work, env=env).stdout.strip()
    assert version.startswith("pankegg_make_db "), version
    run([exe, "-i", "samples.csv", "-o", "s1", "--output_dir", "out"], cwd=work, env=env)
    con = sqlite3.connect(work / "out" / "s1.db")
    n_bins = con.execute("SELECT COUNT(*) FROM bin").fetchone()[0]
    n_links = con.execute("SELECT COUNT(*) FROM bin_map_kegg").fetchone()[0]
    con.close()
    assert n_bins == 3
    assert n_links > 0


def test_full_wheel_clean_install(tmp_path):
    wheel = build_wheel(tmp_path / "dist", "full")
    bindir = make_venv(tmp_path / "venv", system_site_packages=True)
    env = clean_env()
    run([bindir / "python", "-m", "pip", "install", "--no-deps", "--no-index", wheel], env=env)
    work = tmp_path / "work"
    prepare_inputs(work)
    check_make_db(bindir, work, env)
    # The web app is part of the full package: entry point, templates and bundled DB resolve.
    run([bindir / "pankegg_app", "--help"], cwd=work, env=env)
    probe = (
        "from pankegg.app import app, get_default_db_path; import os;"
        "assert os.path.exists(get_default_db_path()), get_default_db_path();"
        "r = app.test_client().get('/'); assert r.status_code == 200, r.status_code"
    )
    run([bindir / "python", "-c", probe], cwd=work, env=env)
    # No stray top-level package from PANKEGG (finding F7).
    run([bindir / "python", "-c", "import importlib.util as u; assert u.find_spec('lib') is None"], cwd=work, env=env)


def test_makedb_wheel_clean_install(tmp_path):
    wheel = build_wheel(tmp_path / "dist", "makedb")
    bindir = make_venv(tmp_path / "venv", system_site_packages=False)
    env = clean_env()
    run([bindir / "python", "-m", "pip", "install", "--no-index", wheel], env=env)
    work = tmp_path / "work"
    prepare_inputs(work)
    check_make_db(bindir, work, env)
    # Light distribution: standard library only, no web app.
    assert not (bindir / "pankegg_app").exists()
    reqs = run([bindir / "python", "-c",
                "import importlib.metadata as m; print(m.requires('pankegg-makedb'))"], cwd=work, env=env)
    assert reqs.stdout.strip() == "None", reqs.stdout


def test_makedb_build_produces_sdist_and_wheel(tmp_path):
    """The default build (used for PyPI and Bioconda) yields both artefacts, without the web app."""
    import tarfile
    run([sys.executable, REPO / "tools" / "build_makedb.py", "--outdir", tmp_path], env=clean_env())
    sdists = sorted(tmp_path.glob("pankegg_makedb-*.tar.gz"))
    wheels = sorted(tmp_path.glob("pankegg_makedb-*.whl"))
    assert len(sdists) == 1 and len(wheels) == 1, sorted(p.name for p in tmp_path.iterdir())
    with tarfile.open(sdists[0]) as tf:
        names = {n.split("/", 1)[1] for n in tf.getnames() if "/" in n}
    assert "pankegg/make_db.py" in names and "pankegg/data/ko.txt" in names
    assert "pankegg/app.py" not in names and "pankegg/data/pankegg.db" not in names
