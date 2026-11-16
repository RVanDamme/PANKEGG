"""Sample metadata: pankegg_make_db --metadata FILE (phase 2, A10).

The simple form is a two-column TSV, sample<TAB>condition, with free-text conditions and any
number of them. More columns are allowed when the file has a header: each one is a variable.
"""

import sqlite3

import pytest

from tests.helpers import FIX, run_make_db, write

S1 = FIX / "s1"


def build(tmp_path, metadata_text, samples=("A", "B", "C"), check=True, extra=()):
    rows = "".join(f"{s},{S1}/eggnog/S1.bin1.emapper.annotations,{FIX}/sourmash_lca/S1.bin1.lca.csv,"
                   f"{S1}/checkm2/S1_checkm2_report.tsv\n" for s in samples)
    csv_path = write(tmp_path / "samples.csv", "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n" + rows)
    args = ["--metadata", str(write(tmp_path / "meta.tsv", metadata_text))] if metadata_text is not None else []
    res = run_make_db(csv_path, tmp_path / "out", "t", *args, *extra, check=check)
    return res, tmp_path / "out" / "t.db"


def stored(db):
    con = sqlite3.connect(db)
    rows = con.execute("SELECT s.sample_name, m.variable, m.value FROM sample_metadata m "
                       "JOIN sample s ON s.id = m.sample_id ORDER BY 1, 2").fetchall()
    info = dict(con.execute("SELECT key, value FROM pankegg_info"))
    con.close()
    return rows, info


@pytest.mark.parametrize("text", [
    "A\tsick\nB\thealthy\nC\tsick\n",                             # no header: variable 'condition'
    "sample\tcondition\nA\tsick\nB\thealthy\nC\tsick\n",          # with header
    "Sample name\tcondition\r\nA\tsick\r\nB\thealthy\r\nC\tsick\r\n",
    "# my study\nsample,condition\nA,sick\nB,healthy\n\nC,sick\n",  # comma-separated, comment, blank line
], ids=["no-header", "header", "crlf", "csv"])
def test_two_column_file(tmp_path, text):
    _, db = build(tmp_path, text)
    rows, info = stored(db)
    assert rows == [("A", "condition", "sick"), ("B", "condition", "healthy"), ("C", "condition", "sick")]
    assert info["metadata_variables"] == "condition"


def test_any_number_of_conditions_and_free_text(tmp_path):
    _, db = build(tmp_path, "A\ttest / true\nB\tday 14 (treated)\nC\tÉté\n")
    assert [r[2] for r in stored(db)[0]] == ["test / true", "day 14 (treated)", "Été"]


def test_several_variables(tmp_path):
    _, db = build(tmp_path, "sample\tcondition\tsite\nA\tsick\tgut\nB\thealthy\tgut\nC\tsick\t\n")
    rows, info = stored(db)
    assert ("A", "site", "gut") in rows and ("C", "condition", "sick") in rows
    assert not any(r[0] == "C" and r[1] == "site" for r in rows), "an empty value is not stored"
    assert info["metadata_variables"] == "condition,site"


def test_no_metadata_option(tmp_path):
    _, db = build(tmp_path, None)
    rows, info = stored(db)
    assert rows == [] and info.get("metadata_variables", "") == ""


def test_missing_and_unknown_samples_are_warnings(tmp_path):
    res, db = build(tmp_path, "sample\tcondition\nA\tsick\nZ\thealthy\n")
    assert res.returncode == 0
    assert "Z" in res.stderr and "B" in res.stderr and "WARNING" in res.stderr
    assert stored(db)[0] == [("A", "condition", "sick")]


@pytest.mark.parametrize("text, message", [
    ("sample\tcondition\nA\tsick\nA\thealthy\n", "twice"),
    ("sample\tcondition\nA\tsick\textra\n", "line 2"),
    ("A\tsick\tgut\nB\thealthy\tgut\n", "header"),
    ("sample\tcondition\tcondition\nA\tx\ty\n", "condition"),
    ("", "empty"),
    ("sample\tcondition\nX\tsick\nY\thealthy\n", "none of the samples"),
], ids=["duplicate-sample", "extra-field", "three-columns-no-header", "duplicate-variable", "empty", "no-match"])
def test_bad_metadata_is_an_error(tmp_path, text, message):
    res, db = build(tmp_path, text, check=False)
    assert res.returncode == 1 and message in res.stderr, res.stderr
    assert "Traceback" not in res.stderr and not db.exists()


def test_missing_metadata_file(tmp_path):
    csv_path = write(tmp_path / "s.csv", "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"A,{S1}/eggnog/*.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,{S1}/checkm2/S1_checkm2_report.tsv\n")
    res = run_make_db(csv_path, tmp_path / "out", "t", "--metadata", str(tmp_path / "nope.tsv"), check=False)
    assert res.returncode == 1 and "nope.tsv" in res.stderr
