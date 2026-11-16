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
    # Two samples that share bin names (as SemiBin2 bins do); S2 has only two of the three bins.
    csv_path = write(tmp / "two.csv",
                     "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n"
                     f"S1,{FIX}/s1/eggnog/*.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                     f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n"
                     f"S2,{FIX}/s1/eggnog/S1.bin[12].emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                     f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n")
    run_make_db(csv_path, tmp, "two", "--quiet")
    dbs["two"] = tmp / "two.db"
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


def test_dotenv_in_current_directory_is_used(tmp_path):
    """Installed users keep .env (FLASK_SECRET_KEY) where they start pankegg_app."""
    import subprocess
    import sys
    from tests.helpers import REPO
    (tmp_path / ".env").write_text("FLASK_SECRET_KEY=from_cwd_env\n")
    probe = write(tmp_path / "probe.py", f"import sys; sys.path.insert(0, {str(REPO)!r})\n"
                                         "from pankegg.app import app; print(app.secret_key)\n")
    env = {k: v for k, v in __import__("os").environ.items() if k != "FLASK_SECRET_KEY"}
    out = subprocess.run([sys.executable, str(probe)], cwd=tmp_path, env=env,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "from_cwd_env"


# --- phase 2, A1: wrong numbers and offline assets ---------------------------------------

def test_common_pathways_both_is_an_overlap(databases, client_for):
    rows = client_for(databases["two"]).post("/get_common_pathways_data",
                                             data={"sample1": "S1", "sample2": "S2"}).get_json()
    assert rows
    for r in rows:
        assert r["both"] is (r["sample1"] > 0 and r["sample2"] > 0), r
        assert r["sample1"] + r["sample2"] > 0, "pathways absent from both samples are not listed"
    assert any(not r["both"] for r in rows), "S1.bin3 pathways are only in S1"


def test_bin_vs_bin_is_per_sample(databases, client_for):
    """S1.bin1 exists in both samples; comparing it within S1 must not count the S2 bin."""
    rows = client_for(databases["two"]).post(
        "/get_common_pathways_for_bins",
        data={"sample1": "S1", "bin1": "S1.bin1", "sample2": "S1", "bin2": "S1.bin3"}).get_json()
    assert rows
    assert max(r["bin1"] for r in rows) == 1 and max(r["bin2"] for r in rows) == 1
    for r in rows:
        assert r["both"] is (r["bin1"] > 0 and r["bin2"] > 0)


def test_bin_pca_with_two_bins(databases, client_for):
    res = client_for(databases["two"]).post("/get_pca_data", data={"sample": "S2"})
    assert res.status_code == 200
    data = res.get_json()
    assert "error" in data or len(data["bins"]) == 2


def test_sample_pca_with_too_few_samples_explains_itself(databases, client_for):
    res = client_for(databases["two"]).post("/compar_full", data={"pca_type": "maps"})
    assert res.status_code == 200
    assert "at least 3 samples" in res.get_json()["error"]


def test_taxonomy_heatmap_with_one_taxon_is_not_a_server_error(databases, client_for):
    res = client_for(databases["new_lca"]).post("/get_heatmap_data_for_taxonomy",
                                                data={"sample": "S1", "rank": "_kingdom_"})
    assert res.status_code == 200 and "error" in res.get_json()


def test_bin_query_serves(databases, client_for):
    assert client_for(databases["two"]).get("/bin_query", follow_redirects=True).status_code == 200


def test_assets_are_served_locally(databases, client_for):
    client = client_for(databases["two"])
    html = client.get("/").data.decode()
    assert "cdn." not in html and "https://" not in html.split("<body")[0], "page must work offline"
    for asset in ("plotly.min.js", "bootstrap.min.css", "bootstrap.bundle.min.js"):
        res = client.get(f"/static/vendor/{asset}")
        assert res.status_code == 200 and len(res.data) > 50_000, asset


# --- phase 2, A2: pathway page -------------------------------------------------------------

@pytest.fixture(scope="module")
def a_pathway(databases):
    """A pathway carried by some but not all bins of the two-sample database."""
    import sqlite3
    from pankegg import insights
    con = sqlite3.connect(databases["two"])
    best = None
    for number, name, total in insights.list_pathways(con):
        rep = insights.pathway_report(con, number)
        n = sum(1 for b in rep["bins"] if b["kos"])
        if 0 < n < len(rep["bins"]) and (best is None or len(rep["found_kos"]) > best[2]):
            best = (number, name, len(rep["found_kos"]))
    con.close()
    return best


def test_pathway_report_numbers(databases, a_pathway):
    import sqlite3
    from pankegg import insights
    number, name, n_found = a_pathway
    con = sqlite3.connect(databases["two"])
    rep = insights.pathway_report(con, number)
    reference = insights.reference_pathway_kos()[number]
    assert set(rep["found_kos"]) <= set(reference)
    assert set(rep["missing_kos"]) == set(reference) - set(rep["found_kos"])
    assert len(rep["bins"]) == 5 and {b["sample"] for b in rep["bins"]} == {"S1", "S2"}
    for b in rep["bins"]:
        assert b["pathway_completeness"] == round(100 * len(b["kos"]) / rep["pathway"]["total_orthologs"], 2)
    assert all(rep["ko_names"][k] for k in rep["found_kos"])
    # unclassified toggle: S1.bin2 (lca nomatch) exists in both samples
    hidden = insights.pathway_report(con, number, include_unclassified=False)
    assert len(hidden["bins"]) == 3 and hidden["n_hidden"] == 2
    assert all(b["classified"] for b in hidden["bins"])
    con.close()


def test_pathway_search_by_name_and_id(databases, client_for, a_pathway):
    number, name, _ = a_pathway
    client = client_for(databases["two"])
    for q in (number, number[3:], name, name.upper(), f"{number} {name}"):
        html = client.get("/pathway_stat", query_string={"q": q}).data.decode()
        assert f"{number} — " in html and "plot-matrix" in html, q
    assert client.get("/pathway_stat?q=zzzz-no-such-pathway").status_code == 404
    several = client.get("/pathway_stat?q=metabolism").data.decode()
    assert "Several pathways match" in several


def test_pathway_page_unclassified_toggle(databases, client_for, a_pathway):
    client = client_for(databases["two"])
    shown = client.get("/pathway_stat", query_string={"q": a_pathway[0]}).data.decode()
    hidden = client.get("/pathway_stat", query_string={"q": a_pathway[0], "unclassified": "0"}).data.decode()
    assert "S1.bin2" in shown and "S1.bin2" not in hidden
    assert "2 unclassified bins are hidden" in hidden


def test_pathway_csv_exports(databases, client_for, a_pathway):
    import csv as csvmod
    import io
    client = client_for(databases["two"])
    q = {"q": a_pathway[0]}
    res = client.get("/pathway_stat/export", query_string={**q, "what": "bins"})
    assert res.status_code == 200 and res.mimetype == "text/csv"
    rows = list(csvmod.DictReader(io.StringIO(res.data.decode())))
    assert len(rows) == 5 and {"sample", "bin", "genus", "pathway_per_id_completeness_percent", "kos"} <= set(rows[0])
    matrix = list(csvmod.reader(io.StringIO(client.get("/pathway_stat/export",
                                                       query_string={**q, "what": "matrix"}).data.decode())))
    assert matrix[0][:2] == ["ko", "ko_name"] and len(matrix[0]) == 2 + 5
    assert len(matrix) - 1 == a_pathway[2]
    assert all(set(r[2:]) <= {"0", "1"} for r in matrix[1:])
    missing = client.get("/pathway_stat/export", query_string={**q, "what": "missing"}).data.decode()
    assert missing.startswith("ko,ko_name")
    assert len(client.get("/pathway_stat/export",
                          query_string={**q, "what": "bins", "unclassified": "0"}).data.decode().splitlines()) == 4


@pytest.mark.parametrize("db_kind", ["2.0.0", "new_tax"])
def test_pathway_page_on_old_and_new_db(databases, client_for, db_kind):
    """2.0.0 databases have no classification columns and a dangling taxonomic_id for S1.bin2."""
    import sqlite3
    from pankegg import insights
    con = sqlite3.connect(databases[db_kind])
    number = next(n for n, _, _ in insights.list_pathways(con) if insights.pathway_report(con, n)["found_kos"])
    con.close()
    html = client_for(databases[db_kind]).get("/pathway_stat", query_string={"q": number}).data.decode()
    assert "S1.bin2" in html and "plot-distribution" in html
