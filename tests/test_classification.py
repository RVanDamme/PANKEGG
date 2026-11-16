"""Bin classification inputs (brief §3.1-3.3, §4; findings F2, F6; decisions P3, P4, P7).

Three readers: ``sourmash tax genome`` (csv_summary), ``sourmash lca classify``
and GTDB-Tk summaries. Every bin known from the annotations but without a
classification becomes unclassified (one taxonomy row with all ranks NULL),
in every mode. The method and the tool's status are recorded per bin.
"""

import shutil
import sqlite3

import pytest

from tests.helpers import FIX, run_make_db, write

TAX = FIX / "sourmash_tax_genome"
LCA = FIX / "sourmash_lca"
GTDB = FIX / "gtdbtk"
S1 = FIX / "s1"

ECOLI = ("d__Bacteria", "p__Pseudomonadota", "c__Gammaproteobacteria", "o__Enterobacterales",
         "f__Enterobacteriaceae", "g__Escherichia", "s__Escherichia coli")
BSUB_LCA = ("d__Bacteria", "p__Bacillota", "c__Bacilli", "o__Bacillales", "f__Bacillaceae",
            "g__Bacillus", "s__Bacillus subtilis")
UNCLASSIFIED = (None,) * 7


def build(tmp_path, classification_files, *extra, check=True):
    """S1 sample (3 bins, legacy eggNOG, CheckM2) with the given classification files."""
    cls = tmp_path / "cls"
    cls.mkdir(exist_ok=True)
    for f in classification_files:
        if isinstance(f, tuple):          # (name, text)
            write(cls / f[0], f[1])
        else:
            shutil.copy(f, cls / f.name)
    csv_path = write(tmp_path / "samples.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"S1,{S1}/eggnog/*.emapper.annotations,cls/*,{S1}/checkm2/S1_checkm2_report.tsv\n")
    res = run_make_db(csv_path, tmp_path / "out", "t", *extra, cwd=tmp_path, check=check)
    return res, tmp_path / "out" / "t.db"


def bins(db):
    con = sqlite3.connect(db)
    rows = con.execute(
        """SELECT b.bin_name, t._kingdom_, t._phylum_, t._class_, t._order_, t._family_, t._genus_,
                  t._species_, b.classification_method, b.classification_status,
                  typeof(b.taxonomic_id), b.completeness
           FROM bin b LEFT JOIN taxonomy t ON t.id = b.taxonomic_id""").fetchall()
    con.close()
    return {r[0]: {"tax": tuple(r[1:8]), "method": r[8], "status": r[9], "id_type": r[10],
                   "completeness": r[11]} for r in rows}


def assert_one_unclassified_row(db):
    con = sqlite3.connect(db)
    n_null = con.execute(
        "SELECT COUNT(*) FROM taxonomy WHERE " +
        " AND ".join(f"{c} IS NULL" for c in
                     ["_kingdom_", "_phylum_", "_class_", "_order_", "_family_", "_genus_", "_species_"])
    ).fetchone()[0]
    dangling = con.execute(
        "SELECT COUNT(*) FROM bin b LEFT JOIN taxonomy t ON t.id=b.taxonomic_id WHERE t.id IS NULL").fetchone()[0]
    con.close()
    assert n_null <= 1, "unclassified bins must share one taxonomy row"
    assert dangling == 0, "every bin must point to a taxonomy row"


# --- detection ----------------------------------------------------------------

@pytest.mark.parametrize("path, kind", [
    (TAX / "S1.bin1.classifications.csv", "sourmash_tax"),
    (TAX / "S1.all.classifications.csv", "sourmash_tax"),
    (LCA / "S1.bin2.lca.csv", "sourmash_lca"),
    (GTDB / "S1.bac120.summary.tsv", "gtdbtk"),
])
def test_detect_file_type(path, kind):
    from pankegg.db_utils import detect_file_type
    assert detect_file_type(str(path)) == kind


def test_detect_empty_file(tmp_path):
    from pankegg.db_utils import detect_file_type
    assert detect_file_type(str(write(tmp_path / "e.csv", ""))) == "empty"


# --- sourmash tax genome (new) --------------------------------------------------

TAX_EXPECTED = {
    "S1.bin1": {"tax": ECOLI, "method": "sourmash_tax", "status": "match"},
    # P3: below_threshold keeps its partial lineage; missing ranks are NULL
    "S1.bin3": {"tax": ("d__Bacteria",) + (None,) * 6, "method": "sourmash_tax", "status": "below_threshold"},
    # no gather match -> no file at all -> unclassified (P7)
    "S1.bin2": {"tax": UNCLASSIFIED, "method": "sourmash_tax", "status": "absent"},
}


@pytest.mark.parametrize("files", [
    ["S1.bin1.classifications.csv", "S1.bin3.classifications.csv"],   # one file per bin
    ["S1.all.classifications.csv"],                                    # several bins in one file
    ["S1.all.classifications.csv", "S1.bin1.classifications.csv",
     "S1.bin3.classifications.csv"],                                   # same rows twice
], ids=["per-bin", "one-file", "duplicates"])
@pytest.mark.parametrize("mode", [[], ["--classification", "sourmash_tax"]], ids=["auto", "explicit"])
def test_sourmash_tax_genome(tmp_path, files, mode):
    _, db = build(tmp_path, [TAX / f for f in files], *mode)
    got = bins(db)
    assert {b: {k: v[k] for k in ("tax", "method", "status")} for b, v in got.items()} == TAX_EXPECTED
    assert all(v["completeness"] is not None for v in got.values())
    assert_one_unclassified_row(db)


def test_sourmash_tax_ignores_query_filename(tmp_path):
    """Bin name comes from query_name; query_filename (S1.bin1.fa.gz) is not used."""
    text = (TAX / "S1.bin1.classifications.csv").read_text().replace("S1.bin1.fa.gz", "other_name.fa.gz")
    _, db = build(tmp_path, [("x.classifications.csv", text)])
    assert bins(db)["S1.bin1"]["tax"] == ECOLI


def test_sourmash_tax_nomatch_row(tmp_path):
    text = (TAX / "S1.bin1.classifications.csv").read_text().splitlines()[0] + \
        "\nS1.bin1,nomatch,,0.0,,,S1.bin1.fa,,,\n"
    _, db = build(tmp_path, [("x.classifications.csv", text)])
    got = bins(db)["S1.bin1"]
    assert got["tax"] == UNCLASSIFIED and got["status"] == "nomatch"


# --- sourmash lca classify (existing) -------------------------------------------

def test_sourmash_lca_per_bin_files(tmp_path):
    _, db = build(tmp_path, sorted(LCA.glob("*.csv")))
    got = bins(db)
    assert got["S1.bin1"]["tax"] == ECOLI and got["S1.bin1"]["status"] == "found"
    assert got["S1.bin3"]["tax"] == BSUB_LCA
    # 2.0.0 left nomatch bins with the text 'null' as taxonomic_id (P7)
    assert got["S1.bin2"]["tax"] == UNCLASSIFIED and got["S1.bin2"]["status"] == "nomatch"
    assert {v["method"] for v in got.values()} == {"sourmash_lca"}
    assert {v["id_type"] for v in got.values()} == {"integer"}
    assert_one_unclassified_row(db)


def test_sourmash_lca_reads_all_rows(tmp_path):
    """F6: 2.0.0 read only the first data line of each file."""
    lines = [f.read_text().splitlines() for f in sorted(LCA.glob("*.csv"))]
    text = "\n".join([lines[0][0]] + [l[1] for l in lines]) + "\n"
    _, db = build(tmp_path, [("all.lca.csv", text)])
    got = bins(db)
    assert got["S1.bin1"]["tax"] == ECOLI
    assert got["S1.bin3"]["tax"] == BSUB_LCA


@pytest.mark.parametrize("text", ["", "ID,status,superkingdom,phylum,class,order,family,genus,species,strain\n"],
                         ids=["empty", "header-only"])
def test_sourmash_lca_tolerates_empty_files(tmp_path, text):
    """F6: 2.0.0 raised StopIteration on empty and header-only files."""
    _, db = build(tmp_path, [LCA / "S1.bin1.lca.csv", ("S1.bin3.lca.csv", text)], "--classification", "sourmash_lca")
    got = bins(db)
    assert got["S1.bin1"]["tax"] == ECOLI
    assert got["S1.bin3"]["tax"] == UNCLASSIFIED and got["S1.bin3"]["status"] == "absent"


# --- GTDB-Tk (existing) -----------------------------------------------------------

@pytest.mark.parametrize("mode", [[], ["--gtdbtk"], ["--classification", "gtdbtk"]],
                         ids=["auto", "legacy-flag", "explicit"])
def test_gtdbtk(tmp_path, mode):
    _, db = build(tmp_path, [GTDB / "S1.bac120.summary.tsv"], *mode)
    got = bins(db)
    assert got["S1.bin1"]["tax"] == ECOLI and got["S1.bin1"]["status"] == "classified"
    assert got["S1.bin3"]["tax"][5:] == ("g__Bacillus", "s__")   # 2.0.0 keeps empty-prefix ranks
    assert got["S1.bin2"]["tax"] == UNCLASSIFIED and got["S1.bin2"]["status"] == "absent"
    assert {v["method"] for v in got.values()} == {"gtdbtk"}
    assert_one_unclassified_row(db)


def test_gtdbtk_unclassified_label(tmp_path):
    """GTDB-Tk writes 'Unclassified Bacteria' for genomes it cannot place (P7)."""
    lines = (GTDB / "S1.bac120.summary.tsv").read_text().splitlines()
    fields = lines[1].split("\t")
    fields[1] = "Unclassified Bacteria"
    _, db = build(tmp_path, [("S1.bac120.summary.tsv", "\n".join([lines[0], "\t".join(fields)]) + "\n")])
    got = bins(db)["S1.bin1"]
    assert got["tax"] == UNCLASSIFIED and got["status"] == "unclassified"


# --- mode selection and errors ------------------------------------------------------

def test_explicit_mode_contradicting_files_is_an_error(tmp_path):
    res, _ = build(tmp_path, [TAX / "S1.bin1.classifications.csv"], "--classification", "sourmash_lca", check=False)
    assert res.returncode != 0
    assert "S1.bin1.classifications.csv" in res.stderr + res.stdout


def test_mixed_types_in_one_sample_is_an_error(tmp_path):
    res, _ = build(tmp_path, [TAX / "S1.bin1.classifications.csv", LCA / "S1.bin3.lca.csv"], check=False)
    assert res.returncode != 0
    assert "mixed" in (res.stderr + res.stdout).lower()


def test_legacy_flag_conflicting_with_classification_is_an_error(tmp_path):
    res, _ = build(tmp_path, [GTDB / "S1.bac120.summary.tsv"], "--gtdbtk", "--classification", "sourmash_lca",
                   check=False)
    assert res.returncode != 0


def test_unrecognised_file_only_is_an_error(tmp_path):
    res, _ = build(tmp_path, [("notes.txt", "hello,world\n1,2\n")], check=False)
    assert res.returncode != 0
    assert "notes.txt" in res.stderr + res.stdout


def test_no_classification_file_at_all(tmp_path):
    """All bins of a sample unmatched: sourmash wrote no file; every bin is unclassified."""
    _, db = build(tmp_path, [], "--classification", "sourmash_tax")
    got = bins(db)
    assert {v["tax"] for v in got.values()} == {UNCLASSIFIED}
    assert {v["status"] for v in got.values()} == {"absent"}


# --- schema additions (P4) -------------------------------------------------------------

def test_pankegg_info_table(tmp_path):
    import pankegg
    _, db = build(tmp_path, [TAX / "S1.all.classifications.csv"])
    con = sqlite3.connect(db)
    info = dict(con.execute("SELECT key, value FROM pankegg_info").fetchall())
    con.close()
    assert info["pankegg_version"] == pankegg.__version__
    assert info["classification_methods"] == "sourmash_tax"


# --- review findings (step 10) ---------------------------------------------------------

def test_directories_and_binary_files_in_the_glob_are_skipped(tmp_path):
    """gtdbtk_out/* also matches align/, classify/...; signature files are gzip."""
    import gzip
    (tmp_path / "cls" / "classify").mkdir(parents=True)
    (tmp_path / "cls" / "S1.bin1.sig.gz").write_bytes(gzip.compress(b"xxxx"))
    res, db = build(tmp_path, [GTDB / "S1.bac120.summary.tsv"])
    assert res.returncode == 0, res.stderr
    assert "S1.bin1.sig.gz" in res.stderr          # warned about, by name
    assert bins(db)["S1.bin1"]["tax"] == ECOLI


def test_missing_classification_directory_is_an_error(tmp_path):
    """A typo in classification_dir must not silently give an all-unclassified database."""
    csv_path = write(tmp_path / "samples.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"S1,{S1}/eggnog/*.emapper.annotations,no_such_dir/*.csv,{S1}/checkm2/S1_checkm2_report.tsv\n")
    res = run_make_db(csv_path, tmp_path / "out", "t", cwd=tmp_path, check=False)
    assert res.returncode == 1
    assert "no_such_dir" in res.stderr


def test_existing_empty_classification_directory_is_allowed(tmp_path):
    (tmp_path / "cls").mkdir()
    res, db = build(tmp_path, [])
    assert res.returncode == 0, res.stderr
    assert {v["status"] for v in bins(db).values()} == {"absent"}


@pytest.mark.parametrize("fixture", [TAX / "S1.bin1.classifications.csv", LCA / "S1.bin1.lca.csv",
                                     GTDB / "S1.bac120.summary.tsv"], ids=["tax", "lca", "gtdbtk"])
def test_utf8_bom_is_tolerated(tmp_path, fixture):
    _, db = build(tmp_path, [(fixture.name, "﻿" + fixture.read_text())])
    assert bins(db)["S1.bin1"]["tax"] == ECOLI
