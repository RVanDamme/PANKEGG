"""Bin names (brief §3.4; findings F4, F5).

The same bin must get the same name from the annotation file name, the
CheckM2 ``Name`` column and the classification ID.
"""

import pytest

from tests.helpers import (CHECKM2_HEADER, ECOLI, EGGNOG_SOURCES, LCA_HEADER,
                           bins_table, run_make_db, write)


@pytest.mark.parametrize("raw, expected", [
    ("S3.439", "S3.439"),
    ("SemiBin_12", "SemiBin_12"),
    ("a.b.c", "a.b.c"),
    ("S1.bin1.fa", "S1.bin1"),
    ("S1.bin1.fa.gz", "S1.bin1"),
    ("S1.bin1.fna", "S1.bin1"),
    ("S1.bin1.fna.gz", "S1.bin1"),
    ("S1.bin1.fasta", "S1.bin1"),
    ("S1.bin1.fasta.gz", "S1.bin1"),
    ("SemiBin_12.fa.gz", "SemiBin_12"),
    ("metabat_bins.189.fa", "metabat_bins.189"),
    (" S3.439 ", "S3.439"),
])
def test_normalise_bin_name(raw, expected):
    from pankegg.binnames import normalise_bin_name
    assert normalise_bin_name(raw) == expected


@pytest.mark.parametrize("filename, expected", [
    ("S3.439.emapper.annotations", "S3.439"),
    ("SemiBin_12.emapper.annotations", "SemiBin_12"),
    ("a.b.c.emapper.annotations", "a.b.c"),
    ("metabat_bins.189.annotations.tsv", "metabat_bins.189"),
    ("S1.bin1.fa.emapper.annotations", "S1.bin1"),
    ("S1.bin1.fa.gz.emapper.annotations", "S1.bin1"),
    ("S1.bin1.fna.gz.annotations", "S1.bin1"),
    ("dir/sub/S3.439.emapper.annotations", "S3.439"),
])
def test_bin_name_from_annotation_file(filename, expected):
    from pankegg.binnames import bin_name_from_annotation_file
    assert bin_name_from_annotation_file(filename) == expected


def test_unrecognised_annotation_suffix_keeps_2_0_0_rule(caplog):
    """Unknown suffix: keep the 2.0.0 result (first two dot parts) so existing DBs do not change."""
    from pankegg.binnames import bin_name_from_annotation_file
    with caplog.at_level("WARNING", logger="pankegg"):
        assert bin_name_from_annotation_file("x.y.z.tsv") == "x.y"
        assert bin_name_from_annotation_file("x.y.z.tsv") == "x.y"
        assert bin_name_from_annotation_file("nodots") == "nodots"
    messages = [r.getMessage() for r in caplog.records]
    assert sum("x.y.z.tsv" in m for m in messages) == 1, "warn once per file"
    assert any("2.0.0 naming rule" in m and "nodots" in m for m in messages)


def test_pipeline_bin_names_end_to_end(tmp_path):
    """F4/F5: names with zero or 2+ dots and .fa.gz/.fna.gz IDs resolve to one bin each."""
    bins = {  # bin name -> (annotation file name, CheckM2 Name, lca ID)
        "SemiBin_12": ("SemiBin_12.emapper.annotations", "SemiBin_12", "SemiBin_12.fa.gz"),
        "a.b.c": ("a.b.c.emapper.annotations", "a.b.c.fa", "a.b.c.fna.gz"),
        "S3.439": ("S3.439.emapper.annotations", "S3.439", "S3.439.fa"),
    }
    checkm2 = CHECKM2_HEADER
    for i, (name, (ann, cm_name, lca_id)) in enumerate(bins.items()):
        write(tmp_path / "ann" / ann, EGGNOG_SOURCES[i].read_text())
        write(tmp_path / "lca" / f"{name}.csv", LCA_HEADER + f"{lca_id},found,{ECOLI}\n")
        checkm2 += f"{cm_name}\t{90 + i}\t{i}.5\n"
    write(tmp_path / "checkm2.tsv", checkm2)
    csv_path = write(tmp_path / "samples.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     "S,ann/*,lca/*.csv,checkm2.tsv\n")
    run_make_db(csv_path, tmp_path / "out", cwd=tmp_path)
    table = bins_table(tmp_path / "out" / "test.db")
    assert table == {
        ("S", "SemiBin_12"): (90.0, 0.5, "g__Escherichia"),
        ("S", "a.b.c"): (91.0, 1.5, "g__Escherichia"),
        ("S", "S3.439"): (92.0, 2.5, "g__Escherichia"),
    }
