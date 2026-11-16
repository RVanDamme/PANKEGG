"""Summaries and cross-module views of a PANKEGG database (web app only).

Query helpers take an open ``sqlite3`` connection and return plain Python
structures, so they can be tested without a browser. They work on databases
built by 2.0.0 as well: columns and tables added later are optional.

Two completeness measures are used (see docs/dev/APP_REVIEW.md):

* pathway per-ID completeness: distinct KOs of a KEGG map found, divided by
  all KOs drawn on that map;
* module completeness: fraction of the steps of a KEGG module that are
  satisfied (databases built by 2.1.0 or later).
"""

import csv
import io
import re
from collections import Counter, defaultdict

from . import resource_path

RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
RANK_COLUMNS = [f"_{r}_" for r in RANKS]
UNCLASSIFIED = "Unclassified"

PER_ID_HELP = (
    "Pathway per-ID completeness is the number of distinct KOs of a KEGG map found in a bin "
    "(or sample), divided by all KOs drawn on that map. A map collects every alternative route "
    "and every group of organisms, so no single genome reaches 100%: use it to compare bins, "
    "not to decide that a pathway is complete."
)
MODULE_HELP = (
    "Module completeness is the fraction of the steps of a KEGG module that are satisfied. "
    "A module is a small functional unit defined as steps with alternatives (one KO or another), "
    "complexes (several KOs together) and optional parts, so 100% means that every required "
    "step has at least one of its alternatives."
)


# --- schema helpers ----------------------------------------------------------------

def table_columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def has_table(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def db_info(conn):
    """Contents of pankegg_info ({} for databases built before 2.1.0)."""
    if not has_table(conn, "pankegg_info"):
        return {}
    return {r[0]: r[1] for r in conn.execute("SELECT key, value FROM pankegg_info")}


# --- reference data shipped with the package ------------------------------------------

_reference = {}


def reference_pathway_kos():
    """{map_number: [KO, ...]} from the KEGG reference list shipped with PANKEGG."""
    if "pathway_kos" not in _reference:
        data = {}
        with open(resource_path("data", "kegg_map_orthologs.tsv"), encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3:
                    data[parts[0]] = [k for k in parts[2].split(",") if k]
        _reference["pathway_kos"] = data
    return _reference["pathway_kos"]


def reference_ko_names():
    """{KO: description} from the KEGG KO list shipped with PANKEGG."""
    if "ko_names" not in _reference:
        data = {}
        with open(resource_path("data", "ko.txt"), encoding="utf-8") as fh:
            for line in fh:
                ko, _, name = line.rstrip("\n").partition("\t")
                if ko:
                    data[ko] = name
        _reference["ko_names"] = data
    return _reference["ko_names"]


# --- bins ---------------------------------------------------------------------------

def _clean_rank(value):
    """A rank value for display, or None when it carries no name ('', 's__', NULL)."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or re.fullmatch(r"[a-z]__", value):
        return None
    return value


def quality_tier(completeness, contamination):
    """MIMAG tier from completeness and contamination only (rRNA/tRNA criteria are not in the database)."""
    if completeness is None or contamination is None:
        return "not assessed"
    if completeness >= 90 and contamination < 5:
        return "high"
    if completeness >= 50 and contamination < 10:
        return "medium"
    return "low"


def load_bins(conn, include_unclassified=True):
    """Every bin with its sample, quality, lineage and classification.

    ``classified`` is True when the bin has a named kingdom/domain. ``confidence`` is
    'classified', 'low confidence' (sourmash below_threshold) or 'unclassified'.
    """
    cols = table_columns(conn, "bin")
    extra = ", b.classification_method, b.classification_status" if "classification_status" in cols else ", NULL, NULL"
    rows = conn.execute(
        f"""SELECT b.id, b.bin_name, s.sample_name, s.id, b.completeness, b.contamination,
                   t._kingdom_, t._phylum_, t._class_, t._order_, t._family_, t._genus_, t._species_{extra}
            FROM bin b JOIN sample s ON s.id = b.sample_id
            LEFT JOIN taxonomy t ON t.id = b.taxonomic_id
            ORDER BY s.sample_name, b.bin_name""").fetchall()
    bins = []
    for r in rows:
        lineage = {rank: _clean_rank(r[6 + i]) for i, rank in enumerate(RANKS)}
        classified = lineage["kingdom"] is not None
        status = r[14]
        if not classified:
            confidence = "unclassified"
        elif status == "below_threshold":
            confidence = "low confidence"
        else:
            confidence = "classified"
        if not classified and not include_unclassified:
            continue
        bins.append({
            "id": r[0], "name": r[1], "sample": r[2], "sample_id": r[3],
            "completeness": r[4], "contamination": r[5],
            "lineage": lineage, "classified": classified, "confidence": confidence,
            "method": r[13], "status": status,
            "tier": quality_tier(r[4], r[5]),
            "label": f"{r[1]} [{r[2]}]",
        })
    return bins


def taxon_of(bin_, rank):
    return bin_["lineage"].get(rank) or UNCLASSIFIED


# --- pathways -------------------------------------------------------------------------

def list_pathways(conn):
    """[(map_number, name, total_orthologs)] for real KEGG maps present in the database."""
    return [tuple(r) for r in conn.execute(
        "SELECT map_number, pathway_name, pathway_total_orthologs FROM map "
        "WHERE map_number LIKE 'map%' ORDER BY map_number")]


def find_pathways(conn, query):
    """Pathways matching a map ID ('map00010', '00010'), an exact name or part of a name.

    Returns a list; one element means an unambiguous match.
    """
    query = (query or "").strip()
    if not query:
        return []
    pathways = list_pathways(conn)
    token = query.split()[0].lower()
    if re.fullmatch(r"(map|ko)?\d{5}", token):
        number = "map" + token[-5:]
        return [p for p in pathways if p[0] == number]
    exact = [p for p in pathways if (p[1] or "").lower() == query.lower()]
    if exact:
        return exact
    return [p for p in pathways if query.lower() in (p[1] or "").lower()]


def pathway_bin_kos(conn, map_number):
    """{bin_id: set(KO)} for the KOs of one map (reference KOs only) found in each bin."""
    found = defaultdict(set)
    for bin_id, ko in conn.execute(
            """SELECT bmk.bin_id, k.ko_id FROM map m
               JOIN map_kegg mk ON mk.map_id = m.id AND mk.real_pathway_id = 1
               JOIN kegg k ON k.id = mk.kegg_id
               JOIN bin_map_kegg bmk ON bmk.map_kegg_id = mk.id
               WHERE m.map_number = ?""", (map_number,)):
        found[bin_id].add(ko)
    return found


def ko_names(conn, kos):
    """{KO: short name} from the database, completed from the shipped KEGG list."""
    names = {}
    kos = list(kos)
    for i in range(0, len(kos), 500):
        chunk = kos[i:i + 500]
        for ko, name, full in conn.execute(
                f"SELECT ko_id, kegg_name, kegg_full_name FROM kegg WHERE ko_id IN ({','.join('?' * len(chunk))})",
                chunk):
            names[ko] = " ".join(x for x in (name, full) if x and x != "None").strip()
    ref = reference_ko_names()
    for ko in kos:
        if not names.get(ko):
            names[ko] = ref.get(ko, "")
    return names


def pathway_report(conn, map_number, include_unclassified=True, rank="genus", max_matrix_kos=200):
    """Everything the pathway page shows for one KEGG map."""
    row = conn.execute("SELECT map_number, pathway_name, pathway_total_orthologs FROM map WHERE map_number = ?",
                       (map_number,)).fetchone()
    if row is None:
        return None
    reference = reference_pathway_kos().get(map_number, [])
    total = row[2] or len(reference)
    bins = load_bins(conn, include_unclassified)
    found = pathway_bin_kos(conn, map_number)
    n_hidden = len(load_bins(conn, True)) - len(bins) if not include_unclassified else 0

    def pct(n):
        return round(100.0 * n / total, 2) if total else 0.0

    for b in bins:
        b["kos"] = sorted(found.get(b["id"], ()))
        b["pathway_completeness"] = pct(len(b["kos"]))

    samples = []
    by_sample = defaultdict(list)
    for b in bins:
        by_sample[b["sample"]].append(b)
    for name in sorted(by_sample):
        union = set().union(*(b["kos"] for b in by_sample[name]))
        samples.append({"name": name, "kos": sorted(union), "completeness": pct(len(union)),
                        "bins": by_sample[name]})

    all_found = set().union(*(b["kos"] for b in bins)) if bins else set()
    ko_bins = Counter(ko for b in bins for ko in b["kos"])
    missing = [k for k in reference if k not in all_found]
    names = ko_names(conn, list(all_found) + missing)

    # KO x bin matrix: most widespread KOs first, bins grouped by sample then by completeness.
    matrix_kos = [k for k, _ in sorted(ko_bins.items(), key=lambda kv: (-kv[1], kv[0]))]
    shown_kos = matrix_kos[:max_matrix_kos]
    matrix_bins = sorted(bins, key=lambda b: (b["sample"], -b["pathway_completeness"], b["name"]))

    carriers = defaultdict(list)
    for b in bins:
        carriers[taxon_of(b, rank)].append(b["pathway_completeness"])
    carriers = sorted(
        ({"taxon": t, "n_bins": len(v), "n_with": sum(1 for x in v if x > 0),
          "mean": round(sum(v) / len(v), 2), "max": max(v)} for t, v in carriers.items()),
        key=lambda c: (-c["mean"], c["taxon"]))

    return {
        "pathway": {"number": row[0], "name": row[1], "total_orthologs": total},
        "bins": bins, "samples": samples,
        "found_kos": sorted(all_found), "missing_kos": missing, "ko_names": names,
        "total_completeness": pct(len(all_found)),
        "matrix": {"kos": shown_kos, "bins": matrix_bins, "n_kos_total": len(matrix_kos),
                   "ko_bins": dict(ko_bins)},
        "carriers": carriers, "rank": rank,
        "include_unclassified": include_unclassified, "n_hidden": n_hidden,
    }


# --- Plotly figures (built here, drawn by the templates) ---------------------------------

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
           "#bcbd22", "#17becf", "#393b79", "#ad494a", "#637939", "#7b4173", "#843c39", "#3182bd"]


def colour_map(values):
    """Stable colour per distinct value, in sorted order; any number of values."""
    return {v: PALETTE[i % len(PALETTE)] for i, v in enumerate(sorted(set(values), key=str))}


def pathway_figures(report):
    figs = {}
    m = report["matrix"]
    names = report["ko_names"]
    if m["kos"] and m["bins"]:
        kos = list(reversed(m["kos"]))  # most widespread at the top
        z = [[1 if ko in set(b["kos"]) else 0 for b in m["bins"]] for ko in kos]
        text = [[f"{ko} {names.get(ko, '')}<br>{b['label']}<br>{'present' if v else 'absent'}"
                 for b, v in zip(m["bins"], zrow)] for ko, zrow in zip(kos, z)]
        figs["matrix"] = {
            "data": [{"type": "heatmap", "z": z, "x": [b["label"] for b in m["bins"]], "y": kos,
                      "text": text, "hoverinfo": "text", "showscale": False, "xgap": 1, "ygap": 1,
                      "colorscale": [[0, "#eeeeee"], [1, "#1f77b4"]], "zmin": 0, "zmax": 1}],
            "layout": {"height": max(320, 14 * len(kos) + 220), "margin": {"l": 80, "r": 20, "t": 30, "b": 190},
                       "xaxis": {"tickangle": -60, "type": "category"}, "yaxis": {"type": "category", "dtick": 1}},
        }
    if report["bins"]:
        colours = colour_map(b["sample"] for b in report["bins"])
        data = []
        for s in report["samples"]:
            data.append({
                "type": "box", "name": s["name"], "y": [b["pathway_completeness"] for b in s["bins"]],
                "boxpoints": "all", "jitter": 0.5, "pointpos": 0, "marker": {"color": colours[s["name"]], "size": 8},
                "line": {"width": 1}, "fillcolor": "rgba(0,0,0,0)",
                "text": [f"{b['name']}<br>{taxon_of(b, 'genus')}<br>CheckM2 completeness "
                         f"{b['completeness'] if b['completeness'] is not None else 'n/a'}%" for b in s["bins"]],
                "hovertemplate": "%{text}<br>pathway per-ID completeness %{y}%<extra></extra>",
            })
        figs["distribution"] = {
            "data": data,
            "layout": {"height": 380, "showlegend": False, "margin": {"t": 30},
                       "yaxis": {"title": {"text": "Pathway per-ID completeness (%)"}, "rangemode": "tozero"}},
        }
    carriers = report["carriers"][:30]
    if carriers:
        carriers = list(reversed(carriers))
        figs["carriers"] = {
            "data": [{"type": "bar", "orientation": "h", "y": [c["taxon"] for c in carriers],
                      "x": [c["mean"] for c in carriers],
                      "text": [f"{c['n_with']}/{c['n_bins']} bins" for c in carriers], "textposition": "auto",
                      "marker": {"color": "#2ca02c"},
                      "hovertemplate": "%{y}<br>mean %{x}%<br>%{text} carry at least one KO<extra></extra>"}],
            "layout": {"height": max(260, 26 * len(carriers) + 120), "margin": {"l": 260, "t": 30},
                       "xaxis": {"title": {"text": "Mean pathway per-ID completeness of the bins (%)"}}},
        }
    return figs


# --- CSV ----------------------------------------------------------------------------------

def csv_text(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def pathway_csv(report, what="bins"):
    if what == "matrix":
        bins = report["matrix"]["bins"]
        kos = sorted(report["matrix"]["ko_bins"], key=lambda k: (-report["matrix"]["ko_bins"][k], k))
        sets = [set(b["kos"]) for b in bins]
        return csv_text(["ko", "ko_name"] + [b["label"] for b in bins],
                        [[ko, report["ko_names"].get(ko, "")] + [1 if ko in s else 0 for s in sets] for ko in kos])
    if what == "missing":
        return csv_text(["ko", "ko_name"], [[k, report["ko_names"].get(k, "")] for k in report["missing_kos"]])
    return csv_text(
        ["sample", "bin", *RANKS, "classification", "checkm2_completeness", "checkm2_contamination",
         "pathway", "pathway_per_id_completeness_percent", "n_kos", "kos"],
        [[b["sample"], b["name"], *[b["lineage"][r] or "" for r in RANKS], b["confidence"],
          b["completeness"], b["contamination"], report["pathway"]["number"], b["pathway_completeness"],
          len(b["kos"]), ";".join(b["kos"])] for b in report["bins"]])
