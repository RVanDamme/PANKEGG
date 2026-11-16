"""Flask routes of the summary and cross-module pages. Data comes from pankegg.insights."""

from flask import Response, abort, render_template, request, session

from . import insights


def _flag(name, default=True):
    value = request.args.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "on", "yes")


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
        finally:
            conn.close()
        if report is None:
            abort(404, description=f"No bin with id {bin_id}")
        return render_template("bin_detail.html", report=report, figs=insights.bin_figures(report),
                               per_id_help=insights.PER_ID_HELP, module_help=insights.MODULE_HELP)

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
