"""The web app opens databases built by this version and by 2.0.0 (acceptance criterion 7).

Uses Flask's test client: no server, no network.
"""

import shutil

import pytest

pytest.importorskip("flask")

from tests.helpers import FIX, run_make_db, write  # noqa: E402

GET_PAGES = [
    "/", "/bin", "/map", "/kegg", "/taxonomy", "/comparison", "/pathway_stat",
    "/pathway_stat?q=map00010", "/sample_vs_sample", "/bin_vs_bin", "/taxonomy_comparison",
    "/compar_full", "/get_samples", "/get_bins_list", "/get_scatterplot_all_samples",
]


@pytest.fixture(scope="module")
def databases(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("app_dbs")
    dbs = {"2.0.0": tmp / "old.db"}
    shutil.copy(FIX / "db_2.0.0" / "s1_lca_2.0.0.db", dbs["2.0.0"])
    for name, cls in [("new_tax", f"{FIX}/sourmash_tax_genome/S1.bin*.classifications.csv"),
                      ("new_lca", f"{FIX}/sourmash_lca/*.lca.csv")]:
        csv_path = write(tmp / f"{name}.csv",
                         "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                         f"S1,{FIX}/s1/eggnog/*.emapper.annotations,{cls},"
                         f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n")
        run_make_db(csv_path, tmp, name, "--quiet")
        dbs[name] = tmp / f"{name}.db"
    return dbs


@pytest.fixture
def client_for():
    from pankegg.app import app
    app.config["TESTING"] = True

    def make(db):
        app.config["PANKEGG_DB_PATH"] = str(db)
        return app.test_client()
    yield make
    app.config.pop("PANKEGG_DB_PATH", None)


@pytest.mark.parametrize("db_kind", ["2.0.0", "new_tax", "new_lca"])
@pytest.mark.parametrize("page", GET_PAGES)
def test_page_serves(databases, client_for, db_kind, page):
    res = client_for(databases[db_kind]).get(page)
    assert res.status_code == 200, f"{page} on {db_kind}: {res.status_code}\n{res.data[:500]!r}"
    assert b"[ERROR]" not in res.data


@pytest.mark.parametrize("db_kind", ["new_tax", "new_lca"])
def test_unclassified_bins_are_listed(databases, client_for, db_kind):
    """New DBs: every bin is listed, unclassified ones included (2.0.0 hid lca 'nomatch' bins)."""
    html = client_for(databases[db_kind]).get("/bin").data.decode()
    for name in ("S1.bin1", "S1.bin2", "S1.bin3"):
        assert name in html, f"{name} missing from /bin on {db_kind}"


def test_2_0_0_database_lists_its_classified_bins(databases, client_for):
    html = client_for(databases["2.0.0"]).get("/bin").data.decode()
    assert "S1.bin1" in html and "S1.bin3" in html


@pytest.mark.osf
@pytest.mark.parametrize("name", ["sourmash_example.db", "gtdbtk_example.db"])
def test_published_2_0_0_databases(test_data_dir, client_for, name):
    client = client_for(test_data_dir / name)
    for page in GET_PAGES:
        res = client.get(page)
        assert res.status_code == 200, f"{page} on {name}: {res.status_code}"


@pytest.mark.parametrize("db_kind", ["2.0.0", "new_tax", "new_lca"])
def test_classified_bin_count(databases, client_for, db_kind):
    """Visualisation > taxonomy: S1.bin2 has no classification in every DB, so 2 of 3 bins are classified."""
    res = client_for(databases[db_kind]).post("/get_taxonomy_data", data={"rank": "_genus_"})
    assert res.status_code == 200
    info = res.get_json()["S1"]["bins_info"]
    assert info == {"classified_bins": 2, "total_bins": 3}, info
