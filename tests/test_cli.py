"""Command-line behaviour (brief §4; findings F11 help text, F12 noise).

Errors go to stderr with a non-zero exit code and no traceback; normal output
is short; --quiet/--verbose control it; the same inputs give the same
database whatever the glob order or hash seed.
"""

import os
import sqlite3
import subprocess
import sys

import pytest

from tests.helpers import FIX, REPO, write

S1 = FIX / "s1"
SCRIPT = str(REPO / "pankegg_make_db.py")


def s1_csv(tmp_path, cls=f"{FIX}/sourmash_lca/*.lca.csv", checkm2=f"{S1}/checkm2/S1_checkm2_report.tsv"):
    return write(tmp_path / "samples.csv",
                 "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                 f"S1,{S1}/eggnog/*.emapper.annotations,{cls},{checkm2}\n")


def cli(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, SCRIPT, *map(str, args)], cwd=cwd, env=env,
                          capture_output=True, text=True)


# --- errors -----------------------------------------------------------------------

@pytest.mark.parametrize("case", ["missing-input", "missing-column", "contradicting-mode", "bad-checkm2-value"])
def test_errors_go_to_stderr_with_nonzero_exit(tmp_path, case):
    out = tmp_path / "out"
    if case == "missing-input":
        args = ["-i", tmp_path / "nope.csv"]
    elif case == "missing-column":
        args = ["-i", write(tmp_path / "s.csv", "Sample name,Annotation_dir\nS1,x\n")]
    elif case == "contradicting-mode":
        args = ["-i", s1_csv(tmp_path), "--classification", "gtdbtk"]
    else:  # fails while the database is being written
        bad = write(tmp_path / "checkm2.tsv", "Name\tCompleteness\tContamination\nS1.bin1\tn/a\t1\n")
        args = ["-i", s1_csv(tmp_path, checkm2=bad)]
    res = cli(*args, "-o", "db", "--output_dir", out)
    assert res.returncode == 1, (res.returncode, res.stdout, res.stderr)
    assert res.stdout == ""
    assert "ERROR" in res.stderr
    assert "Traceback" not in res.stderr
    assert not (out / "db.db").exists(), "no partial database may be left behind"


def test_failed_run_keeps_existing_database(tmp_path):
    out = tmp_path / "out"
    assert cli("-i", s1_csv(tmp_path), "-o", "db", "--output_dir", out).returncode == 0
    before = (out / "db.db").read_bytes()
    res = cli("-i", s1_csv(tmp_path), "-o", "db", "--output_dir", out, "--classification", "gtdbtk")
    assert res.returncode == 1
    assert (out / "db.db").read_bytes() == before


def test_quiet_and_verbose_are_exclusive(tmp_path):
    res = cli("-i", s1_csv(tmp_path), "--quiet", "--verbose")
    assert res.returncode == 2
    assert "not allowed with" in res.stderr


# --- verbosity --------------------------------------------------------------------

def test_default_output_is_short(tmp_path):
    res = cli("-i", s1_csv(tmp_path), "-o", "db", "--output_dir", tmp_path / "out")
    assert res.returncode == 0, res.stderr
    assert res.stdout == ""
    lines = res.stderr.splitlines()
    assert len(lines) <= 6, lines
    assert "[DEBUG]" not in res.stderr and "Skipping row" not in res.stderr
    assert str(tmp_path / "out" / "db.db") in res.stderr


def test_quiet_prints_nothing_on_success(tmp_path):
    res = cli("-i", s1_csv(tmp_path), "-o", "db", "--output_dir", tmp_path / "out", "--quiet")
    assert res.returncode == 0
    assert res.stdout == "" and res.stderr == ""


def test_quiet_still_shows_warnings(tmp_path):
    write(tmp_path / "cls" / "README.txt", "not a classification file\n")
    write(tmp_path / "cls" / "S1.bin1.lca.csv", (FIX / "sourmash_lca" / "S1.bin1.lca.csv").read_text())
    res = cli("-i", s1_csv(tmp_path, cls=f"{tmp_path}/cls/*"), "-o", "db",
              "--output_dir", tmp_path / "out", "--quiet")
    assert res.returncode == 0
    assert "README.txt" in res.stderr and "WARNING" in res.stderr


def test_verbose_shows_file_details(tmp_path):
    res = cli("-i", s1_csv(tmp_path), "-o", "db", "--output_dir", tmp_path / "out", "--verbose")
    assert res.returncode == 0
    assert "S1.bin1.emapper.annotations" in res.stderr
    assert "DEBUG" in res.stderr


# --- help -------------------------------------------------------------------------

def test_help_is_english_and_documents_inputs():
    res = cli("--help")
    assert res.returncode == 0
    text = res.stdout
    for french in ("Format du fichier", "attendu", "fichier"):
        assert french not in text
    for word in ("Sample name", "Annotation_dir", "classification_dir", "Checkm2_dir",
                 "--classification", "sourmash_tax", "--quiet", "--verbose", "--version"):
        assert word in text, word


# --- determinism ------------------------------------------------------------------

REVERSED_GLOB = (
    f"import glob, sys, runpy; sys.path.insert(0, {str(REPO)!r}); _g = glob.glob;"
    "glob.glob = lambda *a, **k: list(reversed(sorted(_g(*a, **k))));"
    f"sys.argv = ['pankegg_make_db'] + sys.argv[1:]; runpy.run_path({SCRIPT!r}, run_name='__main__')"
)


def dump(db):
    con = sqlite3.connect(db)
    lines = list(con.iterdump())
    con.close()
    return lines


def test_same_inputs_same_database(tmp_path):
    csv_path = s1_csv(tmp_path, cls=f"{FIX}/sourmash_tax_genome/*.classifications.csv")
    dumps = []
    for i, (seed, reverse) in enumerate([("1", False), ("2", False), ("3", True)]):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        cmd = ([sys.executable, "-c", REVERSED_GLOB] if reverse else [sys.executable, SCRIPT])
        res = subprocess.run(cmd + ["-i", str(csv_path), "-o", f"db{i}", "--output_dir", str(tmp_path / "out"),
                                    "--quiet"], env=env, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        dumps.append(dump(tmp_path / "out" / f"db{i}.db"))
    assert dumps[0] == dumps[1], "hash seed changed the database"
    assert dumps[0] == dumps[2], "glob order changed the database"
    files = [(tmp_path / "out" / f"db{i}.db").read_bytes() for i in range(3)]
    assert files[0] == files[1] == files[2], "same content but different bytes (snapshot tests need bytes)"


def test_checkm2_dir_accepts_a_glob(tmp_path):
    """The input CSV takes glob patterns; Checkm2_dir was opened as a literal path in 2.0.0."""
    res = cli("-i", s1_csv(tmp_path, checkm2=f"{S1}/checkm2/*_checkm2_report.tsv"),
              "-o", "db", "--output_dir", tmp_path / "out")
    assert res.returncode == 0, res.stderr
    con = sqlite3.connect(tmp_path / "out" / "db.db")
    assert con.execute("SELECT COUNT(*) FROM bin WHERE completeness IS NULL").fetchone()[0] == 0
