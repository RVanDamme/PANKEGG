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


# --- phase 2, A9: KEGG modules in the app -----------------------------------------------------------

def test_module_pages(databases, client_for):
    from pankegg import insights
    con = _con(databases["two"])
    rows = insights.module_list(con)
    assert rows and all(0 < r["best"] <= 100 and r["n_bins"] >= r["complete_bins"] for r in rows)
    number = rows[0]["number"]
    report = insights.module_report(con, number)
    stored = dict(con.execute("SELECT bin_id, completeness FROM bin_module bm JOIN module m ON m.id=bm.module_id "
                              "WHERE m.module_number=?", (number,)))
    for b in report["bins"]:
        assert b["module_completeness"] == stored.get(b["id"], 0.0)
        assert len(b["step_scores"]) == len(report["steps"]) == report["module"]["steps_total"]
        assert round(100 * sum(b["step_scores"]) / len(b["step_scores"]), 0) == round(b["module_completeness"], 0)
    bin_id = report["bins"][0]["id"]
    con.close()
    client = client_for(databases["two"])
    assert number in client.get("/module").data.decode()
    assert client.get("/module?format=csv").data.decode().startswith("module,name,steps")
    detail = client.get(f"/module/{number}")
    assert detail.status_code == 200 and b"plot-steps" in detail.data
    assert client.get(f"/module/{number}?format=csv").data.decode().count("\n") == 6
    assert client.get("/module/M99999").status_code == 404
    assert "KEGG modules" in client.get(f"/bin/{bin_id}").data.decode()
    assert "Module completeness." in client.get("/pathway_taxon").data.decode(), "both measures explained"
    for page in ("/core_accessory?level=module", "/similarity?level=module",
                 "/group_compare?a=sample:S1&b=rest&level=module"):
        assert client.get(page).status_code == 200, page


def test_module_pages_on_2_0_0_db(databases, client_for):
    client = client_for(databases["2.0.0"])
    assert "rebuild it" in client.get("/module").data.decode()
    assert client.get("/module/M00001").status_code == 404
    assert client.get("/core_accessory?level=module").status_code == 200      # falls back to pathways


# --- phase 2, A10: sample metadata in the app ----------------------------------------------------------

@pytest.fixture(scope="module")
def meta_db(tmp_path_factory):
    """Four samples, two variables; D has no site and E-like 'not set' cases are covered by C."""
    tmp = tmp_path_factory.mktemp("meta_db")
    globs = {"A": "S1.bin*", "B": "S1.bin[12]", "C": "S1.bin[13]", "D": "S1.bin1"}
    rows = "".join(f"{s},{FIX}/s1/eggnog/{g}.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                   f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n" for s, g in globs.items())
    csv_path = write(tmp / "samples.csv", "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n" + rows)
    meta = write(tmp / "meta.tsv", "sample\tcondition\tsite\nA\tsick\tgut\nB\thealthy\tgut\nC\tsick\tskin\nD\thealthy\t\n")
    run_make_db(csv_path, tmp, "meta", "--metadata", str(meta), "--quiet")
    return tmp / "meta.db"


def test_conditions_drive_groups(meta_db):
    from pankegg import insights
    con = _con(meta_db)
    assert insights.sample_conditions(con) == {
        "condition": {"A": "sick", "B": "healthy", "C": "sick", "D": "healthy"},
        "site": {"A": "gut", "B": "gut", "C": "skin"}}
    headings = dict(insights.group_options(con))
    assert [v for v, _ in headings["Condition: condition"]] == ["condition:condition=healthy", "condition:condition=sick"]
    res = insights.group_compare(con, "condition:condition=sick", "condition:condition=healthy", "ko")
    assert res["error"] is None and (res["n_a"], res["n_b"]) == (5, 3)            # A(3)+C(2) vs B(2)+D(1)
    by_site = insights.core_accessory(con, "ko", variable="site")
    assert by_site["samples"] == ["gut", "not set", "skin"] and by_site["variable"] == "site"
    by_sample = insights.core_accessory(con, "ko")
    assert by_sample["samples"] == ["A", "B", "C", "D"] and by_sample["variable"] is None
    assert insights.core_accessory(con, "ko", variable="no-such-variable")["samples"] == ["A", "B", "C", "D"]
    con.close()


def test_conditions_in_pages(meta_db, client_for):
    client = client_for(meta_db)
    home = client.get("/").data.decode()
    assert "<th>condition</th>" in home and "<th>site</th>" in home and "healthy" in home
    assert "across values of" in client.get("/core_accessory").data.decode()
    assert "pooled by" in client.get("/core_accessory?by=condition&level=ko").data.decode()
    assert "Condition: site" in client.get("/group_compare").data.decode()
    res = client.get("/group_compare?a=condition:condition=sick&b=condition:condition=healthy&level=ko")
    assert res.status_code == 200 and b"plot-prevalence" in res.data
    assert "<th>condition</th>" in client.get("/similarity").data.decode()
    pca = client.post("/compar_full", data={"pca_type": "kos"}).get_json()
    assert pca["conditions"]["condition"]["A"] == "sick" and len(pca["pca_data"]) == 4


def test_no_metadata_no_condition_controls(databases, client_for):
    client = client_for(databases["two"])
    assert "across values of" not in client.get("/core_accessory").data.decode()
    assert "Condition:" not in client.get("/group_compare").data.decode()


# --- review of phase 2 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("page", ["/pathway_stat?q={q}", "/pathway_taxon?x=1", "/core_accessory?level=ko",
                                  "/similarity?entity=bin", "/module?x=1"])
def test_unclassified_switch_as_the_browser_sends_it(databases, client_for, a_pathway, page):
    """A ticked box is sent as unclassified=0&unclassified=1 (hidden field, then checkbox)."""
    client = client_for(databases["two"])
    url = page.format(q=a_pathway[0])
    on = client.get(url + "&unclassified=0&unclassified=1").data.decode()
    off = client.get(url + "&unclassified=0").data.decode()
    assert 'name="unclassified" value="1" checked' in on.replace("\n", " ").replace("  ", " ") or "checked" in on
    assert on != off
    if "pathway_stat" in page:
        assert "S1.bin2" in on and "S1.bin2" not in off


@pytest.fixture(scope="module")
def odd_names_db(tmp_path_factory):
    """Sample names and conditions with quotes, '=', '<' and the words 'None' and 'not set'."""
    tmp = tmp_path_factory.mktemp("odd")
    names = ["O'Brien farm", "x');alert('XSS", "<b>bold</b> & co", "plain"]
    rows = "".join(f"{n},{FIX}/s1/eggnog/S1.bin1.emapper.annotations,{FIX}/sourmash_lca/*.lca.csv,"
                   f"{FIX}/s1/checkm2/S1_checkm2_report.tsv\n" for n in names)
    csv_path = write(tmp / "samples.csv", "Sample name,Annotation_dir,classification_dir,Checkm2_dir\n" + rows)
    meta = write(tmp / "meta.tsv", "sample\ta=b\tstate\n"
                 f"{names[0]}\tx\tNone\n{names[1]}\ty=z\tnot set\n{names[2]}\tx\t<i>it</i>\n{names[3]}\t\t\n")
    run_make_db(csv_path, tmp, "odd", "--metadata", str(meta), "--quiet")
    return tmp / "odd.db"


def test_names_are_never_inside_inline_scripts(odd_names_db, client_for):
    from pankegg import insights
    con = _con(odd_names_db)
    number = next(n for n, _, _ in insights.list_pathways(con) if insights.pathway_report(con, n)["found_kos"])
    con.close()
    client = client_for(odd_names_db)
    html = client.get("/pathway_stat", query_string={"q": number}).data.decode()
    assert "onclick=\"openKoPanel(this)\"" in html and "alert(&#39;XSS" in html
    assert "openKoPanel(this, " not in html
    for page in ("/", "/bin", "/map", "/kegg", "/similarity", "/core_accessory?by=state", "/group_compare",
                 "/pathway_taxon", "/module", "/bin/1", "/map?bin_id=1", "/kegg?bin_id=1"):
        body = client.get(page).data.decode()
        assert "<b>bold</b>" not in body and "<i>it</i>" not in body, f"{page} renders names as HTML"


def test_selectors_with_odd_variables_and_values(odd_names_db):
    from pankegg import insights
    con = _con(odd_names_db)
    options = dict(insights.group_options(con))
    by_label = {label.split(" (")[0]: value for value, label in options["Condition: a=b"]}
    res = insights.group_compare(con, by_label["x"], "rest", "ko")
    assert (res["n_a"], res["n_b"]) == (2, 2), "variable names may contain '='"
    assert insights.group_compare(con, by_label["y=z"], "rest", "ko")["n_a"] == 1
    state = {label.split(" (")[0]: value for value, label in options["Condition: state"]}
    assert insights.group_compare(con, state["None"], "rest", "ko")["n_a"] == 1, "'None' is a value, not 'missing'"
    core = insights.core_accessory(con, "ko", variable="state")
    assert len(core["samples"]) == 4, "the value 'not set' and a missing value are different groups"
    con.close()


def test_one_rule_for_carrying_a_pathway(databases):
    """Overview, core/accessory, similarity and the group test agree with the pathway page."""
    from pankegg import insights
    con = _con(databases["two"])
    sets = insights.bin_pathways(con)
    comp = insights.bin_pathway_completeness(con)
    assert {(b, n) for b, s in sets.items() for n in s} == {k for k, v in comp.items() if v > 0}
    con.close()


@pytest.mark.parametrize("page, method, data", [
    ("/taxonomy?level=x", "get", None), ("/taxonomy?level=genus;drop", "get", None),
    ("/compar_full", "post", {"pca_type": "taxonomy", "taxonomy_level": "nope"})])
def test_unknown_ranks_are_not_server_errors(databases, client_for, page, method, data):
    res = getattr(client_for(databases["two"]), method)(page, data=data)
    assert res.status_code in (200, 400), res.status_code


# --- owner decisions after phase 2: local-only server by default, paginated Map and Kegg pages -------------

def test_server_defaults_to_localhost_without_debugger(monkeypatch):
    from click.testing import CliRunner
    from pankegg import app as app_module
    calls = []
    monkeypatch.setattr(app_module.app, "run", lambda **kw: calls.append(kw))
    runner = CliRunner()
    assert runner.invoke(app_module.start_server, []).exit_code == 0
    assert calls[-1] == {"host": "127.0.0.1", "port": 5000, "debug": False}
    res = runner.invoke(app_module.start_server, ["--host", "0.0.0.0", "--port", "8080", "--debug"])
    assert res.exit_code == 0 and calls[-1] == {"host": "0.0.0.0", "port": 8080, "debug": True}
    assert "debugger" in res.output.lower(), "exposing the debugger on the network is warned about"
    help_text = runner.invoke(app_module.start_server, ["--help"]).output
    assert "--host" in help_text and "--port" in help_text and "--d" in help_text


ROW = {"/map": r"<tr>\s*<td>(map\d{5})</td>", "/kegg": r"<tr>\s*<td>(K\d{5})</td>"}   # first cell of a row


def _rows(html, page):
    import re
    return len(re.findall(ROW[page], html))


@pytest.mark.parametrize("page, default", [("/map", 25), ("/kegg", 100)])
def test_list_pages_are_paginated(databases, client_for, page, default):
    import re
    marker = page
    client = client_for(databases["two"])
    first = client.get(page).data.decode()
    total = int(re.search(r"of (\d+)</", first).group(1))
    assert total > 10
    assert _rows(first, marker) == min(default, total)
    small = client.get(page, query_string={"per_page": 5}).data.decode()
    assert _rows(small, marker) == 5 and "page=2" in small
    last_page = -(-total // 5)
    seen = set()
    for n in range(1, last_page + 1):
        html = client.get(page, query_string={"per_page": 5, "page": n}).data.decode()
        ids = re.findall(ROW[page], html)
        assert 1 <= len(ids) <= 5 and not seen & set(ids)
        seen |= set(ids)
    assert len(seen) == total, "every row appears on exactly one page"
    # out-of-range and malformed values fall back to a valid page
    for bad in ({"page": 9999, "per_page": 5}, {"page": "abc"}, {"page": 0}, {"per_page": -3}, {"per_page": 10**9}):
        assert client.get(page, query_string=bad).status_code == 200


def test_pagination_keeps_filters(databases, client_for):
    client = client_for(databases["two"])
    html = client.post("/map", data={"filter_mode": "sample", "active_filters": ["S1"], "search_query": "metabolism",
                                     "per_page": "5"}).data.decode()
    link = next(h for h in __import__("re").findall(r'href="([^"]+)"', html) if "page=2" in h).replace("&amp;", "&")
    assert "active_filters=S1" in link and "search_query=metabolism" in link and "filter_mode=sample" in link
    page2 = client.get(link).data.decode()
    assert _rows(page2, "/map") >= 1 and "metabolism" in page2.lower()
    kegg = client.post("/kegg", data={"search_query": "kinase", "per_page": "5"}).data.decode()
    assert "kinase" in kegg.lower()
    assert _rows(client.get("/kegg", query_string={"search_query": "kinase", "per_page": 5}).data.decode(), "/kegg") \
        == _rows(kegg, "/kegg") > 0


def test_search_terms_in_titles_are_escaped(databases, client_for):
    client = client_for(databases["two"])
    for page, data in (("/map", {"search_query": "<b>x</b>"}), ("/map", {"taxon": "<b>x</b>"}),
                       ("/map", {"active_filters": "<b>x</b>"}), ("/kegg", {"search_query": "<b>x</b>"})):
        assert "<b>x</b>" not in client.post(page, data=data).data.decode(), (page, data)


# --- search and selection: bins with the same name in different samples ------------------------------------

def test_search_finds_and_distinguishes_bins(databases):
    from pankegg import insights
    con = _con(databases["two"])
    res = insights.search(con, "S1.bin1")
    assert [(b["name"], b["sample"]) for b in res["bins"]] == [("S1.bin1", "S1"), ("S1.bin1", "S2")]
    # every term must match: bin name, sample name or lineage, in any order
    assert [(b["name"], b["sample"]) for b in insights.search(con, "bin1 S2")["bins"]] == [("S1.bin1", "S2")]
    assert [(b["name"], b["sample"]) for b in insights.search(con, "s2 BIN1")["bins"]] == [("S1.bin1", "S2")]
    assert {(b["name"], b["sample"]) for b in insights.search(con, "escherichia s1")["bins"]} == \
        {("S1.bin1", "S1"), ("S1.bin1", "S2")}                      # "s1" also matches the bin name S1.bin1
    assert [b["sample"] for b in insights.search(con, "sample:S2 bin:bin1")["bins"]] == ["S2"]
    assert {b["sample"] for b in insights.search(con, "sample:S2")["bins"]} == {"S2"}
    assert len(insights.search(con, "sample:S2")["bins"]) == 2
    assert [b["name"] for b in insights.search(con, "unclassified sample:S1")["bins"]] == ["S1.bin2"]
    other = insights.search(con, "metabolism")
    assert other["pathways"] and not other["bins"]
    ko = insights.search(con, other and next(iter(insights.bin_kos(con)[1])))
    assert ko["kos"] and ko["kos"][0]["n_bins"] >= 1
    assert insights.search(con, "Escherichia")["taxa"][0]["n_bins"] == 2
    assert insights.search(con, "")["total"] == 0 and insights.search(con, "zzzz")["total"] == 0
    assert insights.search(con, "%")["total"] == 0, "'%' is a character, not a wildcard"
    con.close()


def test_search_page_and_navbar(databases, client_for):
    client = client_for(databases["two"])
    assert 'action="/search"' in client.get("/bin").data.decode(), "search box on every page"
    html = client.get("/search?q=bin1").data.decode()
    assert html.count(">S1.bin1</a>") == 2 and ">S1<" in html and ">S2<" in html
    assert client.get("/search?q=zzzz").status_code == 200 and client.get("/search").status_code == 200
    assert "<b>x</b>" not in client.get("/search", query_string={"q": "<b>x</b>"}).data.decode()
    assert client.get("/search", query_string={"q": "x" * 5000}).status_code == 200
    old = client_for(databases["2.0.0"]).get("/search?q=bin")
    assert old.status_code == 200 and b"S1.bin2" in old.data


def test_bin_page_lists_namesakes(databases, client_for):
    import sqlite3
    con = sqlite3.connect(databases["two"])
    s1_bin1, s2_bin1 = [r[0] for r in con.execute(
        "SELECT b.id FROM bin b JOIN sample s ON s.id=b.sample_id WHERE b.bin_name='S1.bin1' ORDER BY s.sample_name")]
    s1_bin3 = con.execute("SELECT id FROM bin WHERE bin_name='S1.bin3'").fetchone()[0]
    con.close()
    client = client_for(databases["two"])
    html = client.get(f"/bin/{s1_bin1}").data.decode()
    assert "same name" in html and f'href="/bin/{s2_bin1}"' in html
    assert "same name" not in client.get(f"/bin/{s1_bin3}").data.decode()


def test_bin_list_filters_by_sample_and_several_terms(databases, client_for):
    client = client_for(databases["two"])

    def bins(**params):
        import re
        html = client.get("/bin", query_string=params).data.decode()
        return sorted(re.findall(r'href="/bin/(\d+)"', html))

    everything = bins()
    assert len(everything) == 5
    only_s2 = bins(sample="S2")
    assert len(only_s2) == 2 and set(only_s2) < set(everything)
    assert len(bins(search_query="bin1")) == 2
    assert bins(search_query="%") == [], "'%' is a character, not a wildcard"
    assert bins(search_query="bin1 S2") == bins(search_query="bin1", sample="S2") and len(bins(search_query="bin1 S2")) == 1
    assert bins(sample="no-such-sample") == []
    assert 'name="sample"' in client.get("/bin").data.decode()
