"""Flask routes of the summary and cross-module pages. Data comes from pankegg.insights."""

from flask import Response, abort, render_template, request, session

from . import insights


def _flag(name, default=True):
    # A ticked box arrives as name=0&name=1 (hidden field, then the checkbox): the last value counts.
    values = request.args.getlist(name)
    if not values:
        return default
    return values[-1].lower() in ("1", "true", "on", "yes")


def _csv_response(text, filename):
    return Response(text, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def register(app, get_db_connection, pathway_groups):

    def _rank():
        rank = request.args.get("rank", "genus")
        return rank if rank in insights.RANKS else "genus"

    map_groups = {number: group for group, numbers in (pathway_groups or {}).items() for number in numbers}

    # --- overview (home) --------------------------------------------------------------
    @app.route("/")
    def home():
        session.setdefault('gtdb_filter', False)             # defaults of the bin list, as before
        session.setdefault('selected_sort_option', 'option1')
        conn = get_db_connection()
        try:
            data = insights.overview(conn)
        finally:
            conn.close()
        return render_template("index.html", data=data, figs=insights.overview_figures(data))

    # --- one bin ------------------------------------------------------------------------
    @app.route("/bin/<int:bin_id>")
    def bin_detail(bin_id):
        conn = get_db_connection()
        try:
            report = insights.bin_report(conn, bin_id, map_groups)
            modules = insights.bin_modules(conn, bin_id) if report else []
            same_name = insights.namesakes(conn, report["bin"]) if report else []
            modules_available = insights.has_modules(conn)
        finally:
            conn.close()
        if report is None:
            abort(404, description=f"No bin with id {bin_id}")
        return render_template("bin_detail.html", report=report, figs=insights.bin_figures(report),
                               modules=modules, modules_available=modules_available, same_name=same_name,
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    # --- pathway x taxon ------------------------------------------------------------------
    @app.route("/pathway_taxon")
    def pathway_taxon():
        groups = pathway_groups or {}
        default_group = "1.1 Carbohydrate metabolism" if "1.1 Carbohydrate metabolism" in groups else "all"
        group = request.args.get("group", default_group)
        only = set(groups[group]) if group in groups else None
        conn = get_db_connection()
        try:
            data = insights.pathway_taxon(conn, _rank(), only, _flag("unclassified"))
        finally:
            conn.close()
        if request.args.get("format") == "csv":
            return _csv_response(insights.csv_text(
                ["pathway", "name", "taxa_carrying", "bins_carrying"] + data["taxa"],
                [[r["number"], r["name"], r["n_taxa"], r["n_bins"]] + r["values"] for r in data["rows"]]),
                f"pathway_by_{data['rank']}.csv")
        return render_template("pathway_taxon.html", data=data, figs=insights.pathway_taxon_figures(data),
                               groups=list(groups), group=group if only is not None else "all",
                               ranks=insights.RANKS, unclassified=_flag("unclassified"),
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    def _level(conn):
        levels = insights.available_levels(conn)
        level = request.args.get("level", "pathway")
        return (level if level in levels else "pathway"), levels

    # --- core and accessory ----------------------------------------------------------------
    @app.route("/core_accessory")
    def core_accessory():
        conn = get_db_connection()
        try:
            level, levels = _level(conn)
            variables = sorted(insights.sample_conditions(conn))
            variable = request.args.get("by") if request.args.get("by") in variables else None
            data = insights.core_accessory(conn, level, _flag("unclassified"), variable)
        finally:
            conn.close()
        if request.args.get("format") == "csv":
            return _csv_response(insights.csv_text(
                ["id", "name", "category", "n_samples", "samples"],
                [[r["id"], r["name"], r["category"], r["n_samples"], ";".join(r["samples"])] for r in data["rows"]]),
                f"core_accessory_{level}.csv")
        return render_template("core_accessory.html", data=data, figs=insights.core_accessory_figures(data),
                               levels=levels, unclassified=_flag("unclassified"), variables=variables,
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    # --- similarity -----------------------------------------------------------------------------
    @app.route("/similarity")
    def similarity():
        entity = request.args.get("entity", "sample")
        entity = entity if entity in ("sample", "bin") else "sample"
        conn = get_db_connection()
        try:
            level, levels = _level(conn)
            if "level" not in request.args:
                level = "ko"
            data = insights.similarity(conn, entity, level, _flag("unclassified"))
            conditions = insights.sample_conditions(conn)
        finally:
            conn.close()
        if request.args.get("format") == "csv":
            return _csv_response(insights.csv_text(
                [entity] + data["labels"], [[lab] + row for lab, row in zip(data["labels"], data["matrix"])]),
                f"similarity_{entity}_{level}.csv")
        return render_template("similarity.html", data=data, figs=insights.similarity_figures(data),
                               levels=levels, unclassified=_flag("unclassified"), conditions=conditions,
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    # --- two-group comparison ------------------------------------------------------------------------
    @app.route("/group_compare")
    def group_compare():
        a, b = request.args.get("a", ""), request.args.get("b", "rest")
        quality = request.args.get("quality", "all")
        quality = quality if quality in insights.QUALITY_FILTERS else "all"
        conn = get_db_connection()
        try:
            level, levels = _level(conn)
            options = insights.group_options(conn)
            result = insights.group_compare(conn, a, b, level, quality) if a else None
        finally:
            conn.close()
        labels = {value: label for _, opts in options for value, label in opts}
        label_a = labels.get(a, a)
        label_b = "all other bins" if b == "rest" else labels.get(b, b)
        if result and request.args.get("format") == "csv":
            if result["error"]:
                abort(400, description=result["error"])
            return _csv_response(insights.csv_text(
                ["id", "name", "bins_with_a", "n_a", "percent_a", "bins_with_b", "n_b", "percent_b",
                 "odds_ratio", "p_value", "q_value"],
                [[r["id"], r["name"], r["a"], result["n_a"], r["pct_a"], r["b"], result["n_b"], r["pct_b"],
                  r["odds_ratio"], f"{r['p']:.6g}", f"{r['q']:.6g}"] for r in result["rows"]]),
                f"group_comparison_{level}.csv")
        figs = insights.group_compare_figures(result, label_a, label_b) if result and not result["error"] else {}
        return render_template("group_compare.html", result=result, figs=figs, options=options, levels=levels,
                               a=a, b=b, level=level, quality=quality, label_a=label_a, label_b=label_b,
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    # --- KEGG modules -------------------------------------------------------------------------------
    @app.route("/module")
    def module_list():
        conn = get_db_connection()
        try:
            available = insights.has_modules(conn)
            rows = insights.module_list(conn, _flag("unclassified"))
        finally:
            conn.close()
        if request.args.get("format") == "csv":
            return _csv_response(insights.csv_text(
                ["module", "name", "steps", "bins_with_part", "bins_complete", "samples_with_a_complete_bin",
                 "best_percent", "mean_percent_of_bins_with_part"],
                [[r["number"], r["name"], r["steps"], r["n_bins"], r["complete_bins"], r["complete_samples"],
                  r["best"], r["mean"]] for r in rows]), "modules.csv")
        return render_template("module_list.html", rows=rows, available=available,
                               unclassified=_flag("unclassified"),
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    @app.route("/module/<number>")
    def module_detail(number):
        conn = get_db_connection()
        try:
            report = insights.module_report(conn, number, _flag("unclassified"), _rank())
        finally:
            conn.close()
        if report is None:
            abort(404, description=f"No module {number} in this database")
        if request.args.get("format") == "csv":
            return _csv_response(insights.csv_text(
                ["sample", "bin", *insights.RANKS, "checkm2_completeness", "checkm2_contamination", "module",
                 "module_completeness_percent", "steps_complete", "steps_total", "kos"],
                [[b["sample"], b["name"], *[b["lineage"][r] or "" for r in insights.RANKS], b["completeness"],
                  b["contamination"], number, b["module_completeness"], b["steps_complete"], b["steps_total"],
                  ";".join(b["kos"])] for b in report["bins"]]), f"{number}_bins.csv")
        return render_template("module_detail.html", report=report, figs=insights.module_figures(report),
                               ranks=insights.RANKS,
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

    # --- search ----------------------------------------------------------------------------------------
    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()[:200]
        conn = get_db_connection()
        try:
            result = insights.search(conn, q)
        finally:
            conn.close()
        return render_template("search.html", result=result, q=q, limit=insights.SEARCH_LIMIT)

    @app.route("/favicon.ico")
    def favicon():
        return Response(status=204)

    # --- pathway page ---------------------------------------------------------------
    @app.route("/pathway_stat", methods=["GET"])
    def pathway_stat():
        q = request.args.get("q", "").strip()
        conn = get_db_connection()
        try:
            pathways = insights.list_pathways(conn)
            common = dict(pathways=pathways, q=q, ranks=insights.RANKS, per_id_help=insights.PER_ID_HELP,
                          module_help=insights.MODULE_HELP)
            if not q:
                return render_template("pathway_stat.html", **common)
            matches = insights.find_pathways(conn, q)
            if not matches:
                return render_template("pathway_stat.html", not_found=q, **common), 404
            if len(matches) > 1:
                return render_template("pathway_stat.html", matches=matches, **common)
            report = insights.pathway_report(conn, matches[0][0], _flag("unclassified"), _rank())
            return render_template("pathway_stat.html", report=report, figs=insights.pathway_figures(report),
                                   **common)
        finally:
            conn.close()

    @app.route("/pathway_stat/export", methods=["GET"])
    def pathway_stat_export():
        what = request.args.get("what", "bins")
        if what not in ("bins", "matrix", "missing"):
            abort(400, description="what must be bins, matrix or missing")
        conn = get_db_connection()
        try:
            matches = insights.find_pathways(conn, request.args.get("q", ""))
            if len(matches) != 1:
                abort(404, description="No single pathway matches this query")
            report = insights.pathway_report(conn, matches[0][0], _flag("unclassified"), _rank())
        finally:
            conn.close()
        return _csv_response(insights.pathway_csv(report, what), f"{matches[0][0]}_{what}.csv")
