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


# --- phase 2, A3/A4: overview and bin page ---------------------------------------------------

def test_overview_numbers(databases):
    import sqlite3
    from pankegg import insights
    con = sqlite3.connect(databases["two"])
    data = insights.overview(con)
    con.close()
    assert data["counts"]["samples"] == 2 and data["counts"]["bins"] == 5
    assert data["counts"]["classified"] == 3          # S1.bin2 is a lca nomatch in both samples
    s1 = next(s for s in data["samples"] if s["name"] == "S1")
    assert s1["n_bins"] == 3 and sum(s1["tiers"].values()) == 3 and sum(s1["confidence"].values()) == 3
    assert s1["confidence"]["unclassified"] == 1
    assert s1["tiers"] == {"high": 1, "medium": 2, "low": 0, "not assessed": 0}   # 91.08/0.34 is the high one
    assert data["most_widespread"][0]["n_bins"] >= data["most_widespread"][-1]["n_bins"]
    figs = insights.overview_figures(data)
    sun = figs["taxonomy"]["data"][0]
    roots = [v for i, v, p in zip(sun["ids"], sun["values"], sun["parents"]) if p == ""]
    assert sum(roots) == 5, "every bin is counted once in the sunburst"


def test_low_confidence_is_reported(databases):
    import sqlite3
    from pankegg import insights
    con = sqlite3.connect(databases["new_tax"])
    by_name = {b["name"]: b for b in insights.load_bins(con)}
    con.close()
    assert by_name["S1.bin1"]["confidence"] == "classified"
    assert by_name["S1.bin3"]["confidence"] == "low confidence"     # below_threshold, domain only
    assert by_name["S1.bin2"]["confidence"] == "unclassified"


@pytest.mark.parametrize("db_kind", ["2.0.0", "new_tax", "two"])
def test_overview_and_bin_pages(databases, client_for, db_kind):
    import sqlite3
    client = client_for(databases[db_kind])
    html = client.get("/").data.decode()
    assert "Overview" in html and "plot-quality" in html and "plot-taxonomy" in html
    con = sqlite3.connect(databases[db_kind])
    ids = [r[0] for r in con.execute("SELECT id FROM bin")]
    con.close()
    for bin_id in ids:
        res = client.get(f"/bin/{bin_id}")
        assert res.status_code == 200 and b"CheckM2 completeness" in res.data
    assert client.get("/bin/99999").status_code == 404
    assert f"/bin/{ids[0]}" in client.get("/bin").data.decode(), "bin list links to the bin page"


# --- phase 2, A5-A8: cross-module pages --------------------------------------------------------

def _con(db):
    import sqlite3
    return sqlite3.connect(db)


def test_fisher_and_fdr_match_scipy():
    import random
    from scipy import stats
    from pankegg import insights
    rng = random.Random(1)
    for _ in range(500):
        a, b, c, d = (rng.randint(0, 12) for _ in range(4))
        assert abs(insights.fisher_exact_two_sided(a, b, c, d) - stats.fisher_exact([[a, b], [c, d]])[1]) < 1e-9
    ps = [rng.random() ** 3 for _ in range(60)]
    if hasattr(stats, "false_discovery_control"):
        expected = stats.false_discovery_control(ps, method="bh")
        assert all(abs(x - y) < 1e-12 for x, y in zip(insights.benjamini_hochberg(ps), expected))


def test_pathway_taxon(databases):
    from pankegg import insights
    con = _con(databases["two"])
    data = insights.pathway_taxon(con, "genus")
    comp = insights.bin_pathway_completeness(con)
    bins = insights.load_bins(con)
    assert data["taxa"][-1] == "Unclassified" and sum(data["taxon_bins"].values()) == 5
    row = data["rows"][0]
    for taxon, value in zip(data["taxa"], row["values"]):
        vals = [comp.get((b["id"], row["number"]), 0.0) for b in bins if insights.taxon_of(b, "genus") == taxon]
        assert value == round(sum(vals) / len(vals), 2)
    assert all("Unclassified" not in r["taxa"] and r["n_taxa"] == len(r["taxa"]) for r in data["redundancy"])
    assert [r["n_taxa"] for r in data["redundancy"]] == sorted(r["n_taxa"] for r in data["redundancy"])
    assert "Unclassified" not in insights.pathway_taxon(con, "genus", include_unclassified=False)["taxa"]
    con.close()


@pytest.mark.parametrize("level", ["pathway", "ko"])
def test_core_accessory(databases, level):
    from pankegg import insights
    con = _con(databases["two"])
    data = insights.core_accessory(con, level)
    sets, _ = insights.features(con, level)
    bins = insights.load_bins(con)
    s1 = set().union(*(sets.get(b["id"], set()) for b in bins if b["sample"] == "S1"))
    s2 = set().union(*(sets.get(b["id"], set()) for b in bins if b["sample"] == "S2"))
    con.close()
    assert data["counts"] == {"core": len(s1 & s2), "shared": 0, "unique": len(s1 ^ s2)}
    assert data["unique_per_sample"] == {"S1": len(s1 - s2), "S2": len(s2 - s1)}
    assert s2 <= s1 and data["unique_per_sample"]["S1"] > 0     # S2 is S1 without S1.bin3
    assert sum(v for _, v in data["combos"]) == len(data["rows"])


def test_similarity(databases):
    from pankegg import insights
    con = _con(databases["two"])
    samples = insights.similarity(con, "sample", "ko")
    assert sorted(samples["labels"]) == ["S1", "S2"]
    assert samples["matrix"][0][0] == 1.0 and 0 < samples["matrix"][0][1] < 1
    assert samples["matrix"][0][1] == samples["matrix"][1][0]
    bins = insights.similarity(con, "bin", "ko")
    con.close()
    i, j = bins["labels"].index("S1.bin1 [S1]"), bins["labels"].index("S1.bin1 [S2]")
    assert bins["matrix"][i][j] == 1.0, "the same annotation file in two samples is identical"
    assert abs(i - j) == 1, "clustering puts identical bins next to each other"


def test_group_compare(databases):
    from pankegg import insights
    con = _con(databases["two"])
    res = insights.group_compare(con, "sample:S1", "sample:S2", "ko")
    assert res["error"] is None and (res["n_a"], res["n_b"]) == (3, 2) and res["warnings"]
    sets, _ = insights.features(con, "ko")
    bins = insights.load_bins(con)
    row = res["rows"][0]
    assert row["a"] == sum(1 for b in bins if b["sample"] == "S1" and row["id"] in sets.get(b["id"], ()))
    assert all(0 <= r["p"] <= 1 and r["p"] <= r["q"] + 1e-12 <= 1 + 1e-12 for r in res["rows"])
    assert [r["p"] for r in res["rows"]] == sorted(r["p"] for r in res["rows"])
    rest = insights.group_compare(con, "taxon:genus=g__Escherichia", "rest", "pathway")
    assert (rest["n_a"], rest["n_b"]) == (2, 3)
    assert "share" in insights.group_compare(con, "sample:S1", "all", "ko")["error"]
    assert insights.group_compare(con, "sample:nope", "rest", "ko")["error"]
    assert insights.group_compare(con, "unclassified", "rest", "ko")["n_a"] == 2
    con.close()


NEW_PAGES = ["/pathway_taxon", "/pathway_taxon?rank=family&group=all&unclassified=0", "/pathway_taxon?format=csv",
             "/core_accessory", "/core_accessory?level=ko", "/core_accessory?level=ko&format=csv",
             "/similarity", "/similarity?entity=bin&level=pathway", "/similarity?format=csv",
             "/group_compare", "/group_compare?a=sample:S1&b=rest&level=ko",
             "/group_compare?a=sample:S1&b=rest&level=ko&format=csv", "/comparison"]


@pytest.mark.parametrize("db_kind", ["2.0.0", "new_tax", "two"])
@pytest.mark.parametrize("page", NEW_PAGES)
def test_new_pages_serve(databases, client_for, db_kind, page):
    res = client_for(databases[db_kind]).get(page)
    if "group_compare?a=" in page and db_kind != "two":
        # one sample only: group B (the rest) is empty, which is reported, not a crash
        assert res.status_code in (200, 400)
    else:
        assert res.status_code == 200, f"{page}: {res.status_code}"
