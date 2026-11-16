"""eggNOG-mapper annotations (brief §3.5; finding F3).

Raw emapper output (several '##' lines, a '#query' header, '##' footer lines)
and the legacy stripped file (one '##' line, then the header) must give
identical database content.
"""

from pathlib import Path

from tests.helpers import FIX, run_make_db, write
from tests.regression.summarise_db import summarise, unchanged_part

RAW = FIX / "raw_eggnog_header" / "S3.439.emapper.annotations"
LEGACY = FIX / "legacy_eggnog" / "S3.439.emapper.annotations"
LCA_S3 = ("ID,status,superkingdom,phylum,class,order,family,genus,species,strain\n"
          "S3.439,found,d__Bacteria,p__Bacillota,c__Bacilli,o__Bacillales,f__Bacillaceae,"
          "g__Bacillus,s__Bacillus subtilis,\n")
CHECKM2_S3 = "Name\tCompleteness\tContamination\nS3.439\t80.0\t1.0\n"


def emapper_wrap(legacy_text):
    """Turn a legacy file into what emapper writes: header block, '#query' header, data, footer."""
    raw_lines = RAW.read_text().splitlines(keepends=True)
    head = [l for l in raw_lines[:5] if l.startswith("##")]
    foot = [l for l in raw_lines if l.startswith("##")][len(head):]
    body = [l for l in legacy_text.splitlines(keepends=True) if not l.startswith("##")]
    return "".join(head + body + foot)


def build_s3(tmp_path, annotation):
    d = tmp_path / annotation.parent.name
    write(d / "ann" / annotation.name, annotation.read_text())
    write(d / "lca" / "S3.439.csv", LCA_S3)
    write(d / "checkm2.tsv", CHECKM2_S3)
    csv_path = write(d / "samples.csv", "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                                        "S3,ann/*.emapper.annotations,lca/*.csv,checkm2.tsv\n")
    run_make_db(csv_path, d / "out", cwd=d)
    return summarise(d / "out" / "test.db")


def test_reader_ignores_all_double_hash_lines():
    from pankegg.db_utils import read_eggnog_annotations
    raw_fields, raw_rows = read_eggnog_annotations(str(RAW))
    legacy_fields, legacy_rows = read_eggnog_annotations(str(LEGACY))
    assert raw_fields == legacy_fields
    assert raw_fields[0] == "#query" and {"KEGG_ko", "KEGG_Pathway", "GOs"} <= set(raw_fields)
    assert raw_rows == legacy_rows
    assert len(raw_rows) == 3
    assert not any(r["#query"].startswith("#") for r in raw_rows)


def test_raw_and_legacy_fixture_give_identical_db(tmp_path):
    raw = build_s3(tmp_path, RAW)
    legacy = build_s3(tmp_path, LEGACY)
    assert raw == legacy
    assert raw["samples"]["S3"]["bins"]["S3.439"]["taxonomy"][5] == "g__Bacillus"
    # Every data row is stored in bin_extra ('-' included). The one KO (K12950) has KEGG_Pathway
    # '-': 2.0.0 dropped it, since 2.1.0 it is in the kegg table and linked to its bin.
    assert raw["samples"]["S3"]["counts"]["bin_extra"] == 3
    assert raw["samples"]["S3"]["counts"]["bin_extra_kegg"] == 1
    assert raw["global"]["counts"]["kegg"] == 1


def test_raw_emapper_s1_matches_2_0_0_db(tmp_path):
    """Wrap the legacy S1 files in emapper's header/footer: same DB as 2.0.0 built from legacy files."""
    for src in sorted((FIX / "s1" / "eggnog").glob("*.emapper.annotations")):
        write(tmp_path / "raw" / src.name, emapper_wrap(src.read_text()))
    csv_path = write(tmp_path / "samples.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"S1,{tmp_path}/raw/*.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                     f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n")
    run_make_db(csv_path, tmp_path / "out")
    import json
    expected = json.loads((FIX / "db_2.0.0" / "s1_lca_2.0.0.json").read_text())
    assert unchanged_part(summarise(tmp_path / "out" / "test.db")) == unchanged_part(expected)
