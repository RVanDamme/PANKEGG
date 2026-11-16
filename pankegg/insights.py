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


# --- overview ---------------------------------------------------------------------------------

TIERS = ["high", "medium", "low", "not assessed"]
TIER_COLOURS = {"high": "#2ca02c", "medium": "#ff7f0e", "low": "#d62728", "not assessed": "#bbbbbb"}
CONFIDENCES = ["classified", "low confidence", "unclassified"]
CONFIDENCE_COLOURS = {"classified": "#1f77b4", "low confidence": "#aec7e8", "unclassified": "#bbbbbb"}


def bin_pathways(conn):
    """{bin_id: set(map_number)} for real KEGG maps."""
    out = defaultdict(set)
    for bin_id, number in conn.execute(
            "SELECT bm.bin_id, m.map_number FROM bin_map bm JOIN map m ON m.id = bm.map_id "
            "WHERE m.map_number LIKE 'map%'"):
        out[bin_id].add(number)
    return out


def bin_kos(conn):
    """{bin_id: set(KO)}: every KO annotated in a bin, with or without a pathway."""
    out = defaultdict(set)
    for bin_id, ko in conn.execute(
            "SELECT bmk.bin_id, k.ko_id FROM bin_map_kegg bmk JOIN map_kegg mk ON mk.id = bmk.map_kegg_id "
            "JOIN kegg k ON k.id = mk.kegg_id"):
        out[bin_id].add(ko)
    for bin_id, ko in conn.execute(
            "SELECT e.bin_id, k.ko_id FROM bin_extra_kegg ek JOIN bin_extra e ON e.id = ek.extra_id "
            "JOIN kegg k ON k.id = ek.kegg_id"):
        out[bin_id].add(ko)
    return out


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else round((values[mid - 1] + values[mid]) / 2, 2)


def overview(conn):
    bins = load_bins(conn)
    pathways = bin_pathways(conn)
    kos = bin_kos(conn)
    names = {n: name for n, name, _ in list_pathways(conn)}
    samples = []
    for sample in sorted({b["sample"] for b in bins}):
        sb = [b for b in bins if b["sample"] == sample]
        samples.append({
            "name": sample, "n_bins": len(sb),
            "tiers": {t: sum(1 for b in sb if b["tier"] == t) for t in TIERS},
            "confidence": {c: sum(1 for b in sb if b["confidence"] == c) for c in CONFIDENCES},
            "median_completeness": _median(b["completeness"] for b in sb),
            "median_contamination": _median(b["contamination"] for b in sb),
            "n_pathways": len(set().union(*(pathways.get(b["id"], set()) for b in sb))) if sb else 0,
            "n_kos": len(set().union(*(kos.get(b["id"], set()) for b in sb))) if sb else 0,
            "n_genera": len({b["lineage"]["genus"] for b in sb if b["lineage"]["genus"]}),
        })
    sample_of = {b["id"]: b["sample"] for b in bins}
    spread = defaultdict(lambda: [set(), set()])
    for bin_id, maps in pathways.items():
        for number in maps:
            spread[number][0].add(bin_id)
            spread[number][1].add(sample_of.get(bin_id))
    spread = sorted(({"number": n, "name": names.get(n, ""), "n_bins": len(v[0]), "n_samples": len(v[1])}
                     for n, v in spread.items()), key=lambda p: (-p["n_bins"], p["number"]))
    all_kos = set().union(*kos.values()) if kos else set()
    return {
        "bins": bins, "samples": samples, "info": db_info(conn),
        "counts": {
            "samples": len(samples), "bins": len(bins), "pathways": len(spread), "kos": len(all_kos),
            "classified": sum(1 for b in bins if b["classified"]),
            "high": sum(1 for b in bins if b["tier"] == "high"),
            "medium": sum(1 for b in bins if b["tier"] == "medium"),
            "genera": len({b["lineage"]["genus"] for b in bins if b["lineage"]["genus"]}),
        },
        "most_widespread": spread[:10],
        "rarest": sorted(spread, key=lambda p: (p["n_bins"], p["number"]))[:10],
    }


def _stacked(samples, key, categories, colours, ytitle):
    return {
        "data": [{"type": "bar", "name": c, "x": [s["name"] for s in samples],
                  "y": [s[key][c] for s in samples], "marker": {"color": colours[c]}}
                 for c in categories if any(s[key][c] for s in samples)],
        "layout": {"barmode": "stack", "height": 340, "margin": {"t": 30},
                   "xaxis": {"type": "category"}, "yaxis": {"title": {"text": ytitle}, "dtick": None},
                   "legend": {"orientation": "h", "y": -0.25}},
    }


def taxonomy_sunburst(bins, ranks=("kingdom", "phylum", "class", "order", "family", "genus")):
    """Bins per lineage as a sunburst; a lineage stops at its last named rank."""
    counts, labels, parents = Counter(), {}, {}
    for b in bins:
        path = []
        for rank in ranks:
            value = b["lineage"][rank]
            if value is None:
                break
            path.append(value)
        if not path:
            path = [UNCLASSIFIED]
        for depth in range(1, len(path) + 1):
            node = "/".join(path[:depth])
            counts[node] += 1
            labels[node] = path[depth - 1]
            parents[node] = "/".join(path[:depth - 1])
    ids = sorted(counts)
    return {
        "data": [{"type": "sunburst", "ids": ids, "labels": [labels[i] for i in ids],
                  "parents": [parents[i] for i in ids], "values": [counts[i] for i in ids],
                  "branchvalues": "total", "maxdepth": 4,
                  "hovertemplate": "%{label}<br>%{value} bins<extra></extra>"}],
        "layout": {"height": 520, "margin": {"t": 10, "l": 10, "r": 10, "b": 10}},
    }


def overview_figures(data):
    figs = {}
    if data["samples"]:
        figs["quality"] = _stacked(data["samples"], "tiers", TIERS, TIER_COLOURS, "Bins")
        figs["classification"] = _stacked(data["samples"], "confidence", CONFIDENCES, CONFIDENCE_COLOURS, "Bins")
        figs["taxonomy"] = taxonomy_sunburst(data["bins"])
        colours = colour_map(b["sample"] for b in data["bins"])
        figs["scatter"] = {
            "data": [{"type": "scatter", "mode": "markers", "name": s["name"],
                      "x": [b["completeness"] for b in data["bins"] if b["sample"] == s["name"]],
                      "y": [b["contamination"] for b in data["bins"] if b["sample"] == s["name"]],
                      "text": [b["name"] for b in data["bins"] if b["sample"] == s["name"]],
                      "marker": {"size": 9, "color": colours[s["name"]]},
                      "hovertemplate": "%{text}<br>completeness %{x}%<br>contamination %{y}%<extra>" + s["name"] + "</extra>"}
                     for s in data["samples"]],
            "layout": {"height": 340, "margin": {"t": 30},
                       "xaxis": {"title": {"text": "CheckM2 completeness (%)"}},
                       "yaxis": {"title": {"text": "CheckM2 contamination (%)"}},
                       "shapes": [{"type": "line", "x0": 90, "x1": 90, "y0": 0, "y1": 5, "line": {"dash": "dot", "color": "#2ca02c"}},
                                  {"type": "line", "x0": 90, "x1": 100, "y0": 5, "y1": 5, "line": {"dash": "dot", "color": "#2ca02c"}},
                                  {"type": "line", "x0": 50, "x1": 50, "y0": 0, "y1": 10, "line": {"dash": "dot", "color": "#ff7f0e"}},
                                  {"type": "line", "x0": 50, "x1": 100, "y0": 10, "y1": 10, "line": {"dash": "dot", "color": "#ff7f0e"}}],
                       "legend": {"orientation": "h", "y": -0.3}},
        }
    return figs


# --- one bin -----------------------------------------------------------------------------------

def bin_report(conn, bin_id, map_groups=None):
    """Quality, lineage and functional content of one bin. ``map_groups``: {map_number: KEGG category}."""
    bins = [b for b in load_bins(conn) if b["id"] == bin_id]
    if not bins:
        return None
    b = bins[0]
    map_groups = map_groups or {}
    pathways = []
    for number, name, total, n in conn.execute(
            """SELECT m.map_number, m.pathway_name, m.pathway_total_orthologs, COUNT(DISTINCT mk.kegg_id)
               FROM bin_map_kegg bmk JOIN map_kegg mk ON mk.id = bmk.map_kegg_id AND mk.real_pathway_id = 1
               JOIN map m ON m.id = mk.map_id
               WHERE bmk.bin_id = ? AND m.map_number LIKE 'map%'
               GROUP BY m.id ORDER BY m.map_number""", (bin_id,)):
        pathways.append({"number": number, "name": name, "n_kos": n, "total": total,
                         "completeness": round(100.0 * n / total, 2) if total else 0.0,
                         "category": map_groups.get(number, "Not in a KEGG category")})
    categories = defaultdict(list)
    for p in pathways:
        categories[p["category"]].append(p["completeness"])
    categories = sorted(({"category": c, "n_pathways": len(v), "mean": round(sum(v) / len(v), 2)}
                         for c, v in categories.items()), key=lambda c: c["category"])
    n_sample_bins = conn.execute("SELECT COUNT(*) FROM bin WHERE sample_id = ?", (b["sample_id"],)).fetchone()[0]
    return {"bin": b, "pathways": pathways, "categories": categories,
            "n_kos": len(bin_kos_of(conn, bin_id)), "n_sample_bins": n_sample_bins}


def bin_kos_of(conn, bin_id):
    kos = {r[0] for r in conn.execute(
        "SELECT k.ko_id FROM bin_map_kegg bmk JOIN map_kegg mk ON mk.id = bmk.map_kegg_id "
        "JOIN kegg k ON k.id = mk.kegg_id WHERE bmk.bin_id = ?", (bin_id,))}
    kos |= {r[0] for r in conn.execute(
        "SELECT k.ko_id FROM bin_extra_kegg ek JOIN bin_extra e ON e.id = ek.extra_id "
        "JOIN kegg k ON k.id = ek.kegg_id WHERE e.bin_id = ?", (bin_id,))}
    return kos


def bin_figures(report):
    figs = {}
    top = sorted(report["pathways"], key=lambda p: -p["completeness"])[:25]
    if top:
        top = list(reversed(top))
        figs["pathways"] = {
            "data": [{"type": "bar", "orientation": "h", "x": [p["completeness"] for p in top],
                      "y": [f"{p['number']} {p['name']}"[:60] for p in top],
                      "text": [f"{p['n_kos']}/{p['total']} KOs" for p in top], "textposition": "auto",
                      "marker": {"color": "#1f77b4"}}],
            "layout": {"height": 26 * len(top) + 120, "margin": {"l": 420, "t": 20},
                       "xaxis": {"title": {"text": "Pathway per-ID completeness (%)"}}},
        }
    cats = list(reversed(report["categories"]))
    if cats:
        figs["categories"] = {
            "data": [{"type": "bar", "orientation": "h", "x": [c["n_pathways"] for c in cats],
                      "y": [c["category"][:55] for c in cats],
                      "text": [f"mean {c['mean']}%" for c in cats], "textposition": "auto",
                      "marker": {"color": "#9467bd"}}],
            "layout": {"height": 24 * len(cats) + 120, "margin": {"l": 400, "t": 20},
                       "xaxis": {"title": {"text": "Pathways with at least one KO"}}},
        }
    return figs


# --- features shared by the cross-module pages -------------------------------------------------

LEVELS = {"pathway": "KEGG pathways", "ko": "KOs"}


def available_levels(conn):
    levels = dict(LEVELS)
    if has_table(conn, "bin_module"):
        levels["module"] = "KEGG modules (complete)"
    return levels


def features(conn, level):
    """({bin_id: set(feature id)}, {feature id: name}) for 'pathway', 'ko' or 'module'.

    A pathway is present when the bin has at least one of its KOs; a module when it is complete.
    """
    if level == "ko":
        sets = bin_kos(conn)
        return sets, ko_names(conn, set().union(*sets.values()) if sets else [])
    if level == "module":
        return module_sets(conn)
    return bin_pathways(conn), {n: name for n, name, _ in list_pathways(conn)}


def module_sets(conn, threshold=100.0):
    if not has_table(conn, "bin_module"):
        return {}, {}
    sets = defaultdict(set)
    for bin_id, number in conn.execute(
            "SELECT bm.bin_id, m.module_number FROM bin_module bm JOIN module m ON m.id = bm.module_id "
            "WHERE bm.completeness >= ?", (threshold,)):
        sets[bin_id].add(number)
    return sets, {r[0]: r[1] for r in conn.execute("SELECT module_number, module_name FROM module")}


# --- pathway x taxon ------------------------------------------------------------------------------

def bin_pathway_completeness(conn):
    """{(bin_id, map_number): per-ID completeness %}"""
    out = {}
    for bin_id, number, total, n in conn.execute(
            """SELECT bmk.bin_id, m.map_number, m.pathway_total_orthologs, COUNT(DISTINCT mk.kegg_id)
               FROM bin_map_kegg bmk JOIN map_kegg mk ON mk.id = bmk.map_kegg_id AND mk.real_pathway_id = 1
               JOIN map m ON m.id = mk.map_id WHERE m.map_number LIKE 'map%'
               GROUP BY bmk.bin_id, m.id"""):
        out[(bin_id, number)] = round(100.0 * n / total, 2) if total else 0.0
    return out


def pathway_taxon(conn, rank="genus", only_maps=None, include_unclassified=True):
    """Mean per-ID completeness of each pathway in the bins of each taxon, and functional redundancy.

    ``only_maps`` restricts the matrix (not the redundancy table) to some map numbers.
    """
    bins = load_bins(conn, include_unclassified)
    completeness = bin_pathway_completeness(conn)
    names = {n: name for n, name, _ in list_pathways(conn)}
    groups = defaultdict(list)
    for b in bins:
        groups[taxon_of(b, rank)].append(b["id"])
    taxa = sorted(groups, key=lambda t: (t == UNCLASSIFIED, t))
    present = sorted({number for (_, number) in completeness})
    rows = []
    for number in present:
        values, carriers, n_bins = [], [], 0
        for taxon in taxa:
            vals = [completeness.get((bid, number), 0.0) for bid in groups[taxon]]
            values.append(round(sum(vals) / len(vals), 2))
            with_it = sum(1 for v in vals if v > 0)
            n_bins += with_it
            if with_it and taxon != UNCLASSIFIED:
                carriers.append(taxon)
        if n_bins:
            rows.append({"number": number, "name": names.get(number, ""), "values": values,
                         "n_taxa": len(carriers), "taxa": carriers, "n_bins": n_bins})
    shown = [r for r in rows if only_maps is None or r["number"] in only_maps]
    return {"rank": rank, "taxa": taxa, "taxon_bins": {t: len(groups[t]) for t in taxa},
            "rows": shown, "redundancy": sorted(rows, key=lambda r: (r["n_taxa"], r["number"])),
            "n_bins": len(bins)}


def pathway_taxon_figures(data):
    rows = list(reversed(data["rows"]))
    if not rows or not data["taxa"]:
        return {}
    x = [f"{t} ({data['taxon_bins'][t]})" for t in data["taxa"]]
    return {"matrix": {
        "data": [{"type": "heatmap", "z": [r["values"] for r in rows], "x": x,
                  "y": [f"{r['number']} {r['name']}"[:55] for r in rows],
                  "colorscale": "Viridis", "zmin": 0, "colorbar": {"title": {"text": "mean %"}},
                  "hovertemplate": "%{y}<br>%{x}<br>mean per-ID completeness %{z}%<extra></extra>"}],
        "layout": {"height": max(360, 16 * len(rows) + 240), "margin": {"l": 390, "t": 20, "b": 200},
                   "xaxis": {"tickangle": -60, "type": "category"}, "yaxis": {"type": "category", "dtick": 1}},
    }}


# --- core and accessory ------------------------------------------------------------------------------

def core_accessory(conn, level="pathway", include_unclassified=True):
    """Features by the number of samples that carry them (in at least one bin)."""
    bins = load_bins(conn, include_unclassified)
    sets, names = features(conn, level)
    samples = sorted({b["sample"] for b in bins})
    by_sample = {s: set() for s in samples}
    for b in bins:
        by_sample[b["sample"]] |= sets.get(b["id"], set())
    where = defaultdict(list)
    for s in samples:
        for f in by_sample[s]:
            where[f].append(s)
    n = len(samples)

    def category(k):
        if n > 1 and k == n:
            return "core"
        return "unique" if k == 1 else "shared"

    rows = sorted(({"id": f, "name": names.get(f, ""), "samples": ss, "n_samples": len(ss),
                    "category": category(len(ss))} for f, ss in where.items()),
                  key=lambda r: (-r["n_samples"], r["id"]))
    combos = Counter(" + ".join(r["samples"]) for r in rows)
    return {
        "level": level, "samples": samples, "rows": rows,
        "counts": {c: sum(1 for r in rows if r["category"] == c) for c in ("core", "shared", "unique")},
        "by_n": {k: sum(1 for r in rows if r["n_samples"] == k) for k in range(1, n + 1)},
        "unique_per_sample": {s: sum(1 for r in rows if r["samples"] == [s]) for s in samples},
        "totals": {s: len(by_sample[s]) for s in samples},
        "combos": combos.most_common(25),
    }


def core_accessory_figures(data):
    if not data["rows"]:
        return {}
    n = len(data["samples"])
    ks = list(range(1, n + 1))
    colours = ["#d62728" if k == 1 else "#2ca02c" if (k == n and n > 1) else "#ff7f0e" for k in ks]
    combos = list(reversed(data["combos"]))
    return {
        "by_n": {"data": [{"type": "bar", "x": [str(k) for k in ks], "y": [data["by_n"][k] for k in ks],
                           "marker": {"color": colours}, "text": [data["by_n"][k] for k in ks], "textposition": "auto"}],
                 "layout": {"height": 340, "margin": {"t": 20}, "xaxis": {"title": {"text": "Number of samples carrying it"}, "type": "category"},
                            "yaxis": {"title": {"text": LEVELS.get(data["level"], data["level"])}}}},
        "combos": {"data": [{"type": "bar", "orientation": "h", "y": [c for c, _ in combos], "x": [v for _, v in combos],
                             "marker": {"color": "#1f77b4"}, "text": [v for _, v in combos], "textposition": "auto"}],
                   "layout": {"height": max(260, 24 * len(combos) + 110), "margin": {"l": 320, "t": 20},
                              "xaxis": {"title": {"text": "Features found in exactly these samples"}}}},
    }


# --- similarity ------------------------------------------------------------------------------------------

def jaccard(a, b):
    union = len(a | b)
    return round(len(a & b) / union, 4) if union else 0.0


def cluster_order(matrix):
    """Leaf order of an average-linkage clustering of a similarity matrix (input order if not possible)."""
    n = len(matrix)
    if n < 3:
        return list(range(n))
    try:
        from scipy.cluster.hierarchy import leaves_list, linkage
        from scipy.spatial.distance import squareform
        dist = [[0.0 if i == j else 1.0 - matrix[i][j] for j in range(n)] for i in range(n)]
        return [int(i) for i in leaves_list(linkage(squareform(dist, checks=False), method="average"))]
    except Exception:
        return list(range(n))


def similarity(conn, entity="sample", level="ko", include_unclassified=True):
    """Jaccard similarity between samples (bins pooled) or between bins, on shared features."""
    bins = load_bins(conn, include_unclassified)
    sets, _ = features(conn, level)
    if entity == "bin":
        labels = [b["label"] for b in bins]
        items = [sets.get(b["id"], set()) for b in bins]
    else:
        labels = sorted({b["sample"] for b in bins})
        items = [set().union(*(sets.get(b["id"], set()) for b in bins if b["sample"] == s)) for s in labels]
    matrix = [[1.0 if i == j else jaccard(a, b) for j, b in enumerate(items)] for i, a in enumerate(items)]
    order = cluster_order(matrix)
    return {"entity": entity, "level": level,
            "labels": [labels[i] for i in order], "sizes": [len(items[i]) for i in order],
            "matrix": [[matrix[i][j] for j in order] for i in order]}


def similarity_figures(data, label_colours=None):
    n = len(data["labels"])
    if n < 2:
        return {}
    trace = {"type": "heatmap", "z": data["matrix"], "x": data["labels"], "y": data["labels"],
             "zmin": 0, "zmax": 1, "colorscale": "Viridis", "colorbar": {"title": {"text": "Jaccard"}},
             "hovertemplate": "%{y}<br>%{x}<br>Jaccard %{z}<extra></extra>"}
    if n <= 15:
        trace["text"] = [[f"{v:.2f}" for v in row] for row in data["matrix"]]
        trace["texttemplate"] = "%{text}"
    side = max(420, min(1100, 26 * n + 260))
    return {"similarity": {"data": [trace],
                           "layout": {"height": side, "margin": {"l": 220, "b": 200, "t": 20},
                                      "xaxis": {"tickangle": -60, "type": "category"},
                                      "yaxis": {"type": "category", "autorange": "reversed"}}}}


# --- two-group comparison ---------------------------------------------------------------------------------

def fisher_exact_two_sided(a, b, c, d):
    """Two-sided Fisher's exact test p-value for the table [[a, b], [c, d]] (standard library only)."""
    from math import exp, lgamma

    def logcomb(n, k):
        return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)

    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if n == 0:
        return 1.0
    denom = logcomb(n, c1)

    def logp(x):
        return logcomb(r1, x) + logcomb(r2, c1 - x) - denom

    observed = logp(a)
    total = 0.0
    for x in range(max(0, c1 - r2), min(r1, c1) + 1):
        lp = logp(x)
        if lp <= observed + 1e-9:
            total += exp(lp)
    return min(1.0, total)


def benjamini_hochberg(pvalues):
    """q-values (false discovery rate) in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = running
    return q


def group_options(conn):
    """Choices for a group of bins: [(heading, [(value, label)])]."""
    bins = load_bins(conn)
    options = [("Samples", [(f"sample:{s}", f"{s} ({n} bins)")
                            for s, n in sorted(Counter(b["sample"] for b in bins).items())])]
    for variable, values in sorted(sample_conditions(conn).items()):
        counts = Counter(values.get(b["sample"]) for b in bins)
        options.append((f"Condition: {variable}",
                        [(f"condition:{variable}={v}", f"{v} ({counts[v]} bins)")
                         for v in sorted(set(values.values()), key=str)]))
    for rank in ("phylum", "class", "order", "family", "genus"):
        counts = Counter(b["lineage"][rank] for b in bins if b["lineage"][rank])
        if counts:
            options.append((rank.capitalize(), [(f"taxon:{rank}={t}", f"{t} ({n} bins)") for t, n in sorted(counts.items())]))
    options.append(("Other", [("unclassified", "Unclassified bins"), ("all", "All bins")]))
    return options


def sample_conditions(conn):
    """{variable: {sample_name: value}} from the sample metadata ({} when the database has none)."""
    if not has_table(conn, "sample_metadata"):
        return {}
    out = defaultdict(dict)
    for sample, variable, value in conn.execute(
            "SELECT s.sample_name, sm.variable, sm.value FROM sample_metadata sm JOIN sample s ON s.id = sm.sample_id"):
        out[variable][sample] = value
    return dict(out)


def select_bins(bins, selector, conditions=None):
    """Bins matching 'sample:NAME', 'taxon:RANK=VALUE', 'condition:VARIABLE=VALUE', 'unclassified' or 'all'."""
    kind, _, rest = (selector or "").partition(":")
    if kind == "all":
        return list(bins)
    if kind == "unclassified":
        return [b for b in bins if not b["classified"]]
    if kind == "sample":
        return [b for b in bins if b["sample"] == rest]
    key, _, value = rest.partition("=")
    if kind == "taxon" and key in RANKS:
        return [b for b in bins if b["lineage"][key] == value]
    if kind == "condition":
        values = (conditions or {}).get(key, {})
        return [b for b in bins if str(values.get(b["sample"])) == value]
    return []


QUALITY_FILTERS = {"all": ("high", "medium", "low", "not assessed"), "medium": ("high", "medium"), "high": ("high",)}


def group_compare(conn, selector_a, selector_b, level="pathway", quality="all"):
    """Per feature: bins carrying it in group A and in group B, Fisher's exact test and BH q-value.

    ``selector_b`` may be 'rest' (every bin not in A). The unit is the bin.
    """
    bins = [b for b in load_bins(conn) if b["tier"] in QUALITY_FILTERS.get(quality, QUALITY_FILTERS["all"])]
    conditions = sample_conditions(conn)
    group_a = select_bins(bins, selector_a, conditions)
    ids_a = {b["id"] for b in group_a}
    if selector_b == "rest":
        group_b = [b for b in bins if b["id"] not in ids_a]
    else:
        group_b = select_bins(bins, selector_b, conditions)
    ids_b = {b["id"] for b in group_b}
    result = {"level": level, "n_a": len(ids_a), "n_b": len(ids_b), "rows": [], "warnings": [], "error": None,
              "bins_a": group_a, "bins_b": group_b}
    if not ids_a or not ids_b:
        result["error"] = "Each group needs at least one bin (after the quality filter)."
        return result
    if ids_a & ids_b:
        result["error"] = (f"The two groups share {len(ids_a & ids_b)} bins; choose groups that do not overlap, "
                           "or compare group A with the rest.")
        return result
    if min(len(ids_a), len(ids_b)) < 5:
        result["warnings"].append(
            f"Small groups ({len(ids_a)} and {len(ids_b)} bins): the test has little power, and no feature may "
            "reach significance even when the groups differ.")
    sets, names = features(conn, level)
    in_a, in_b = Counter(), Counter()
    for bid in ids_a:
        in_a.update(sets.get(bid, ()))
    for bid in ids_b:
        in_b.update(sets.get(bid, ()))
    rows = []
    for f in sorted(set(in_a) | set(in_b)):
        a, c = in_a[f], in_b[f]
        b, d = len(ids_a) - a, len(ids_b) - c
        rows.append({"id": f, "name": names.get(f, ""), "a": a, "b": c,
                     "pct_a": round(100.0 * a / len(ids_a), 1), "pct_b": round(100.0 * c / len(ids_b), 1),
                     # Haldane-Anscombe correction keeps the odds ratio finite
                     "odds_ratio": round(((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5)), 3),
                     "p": fisher_exact_two_sided(a, b, c, d)})
    for row, q in zip(rows, benjamini_hochberg([r["p"] for r in rows])):
        row["q"] = q
    rows.sort(key=lambda r: (r["p"], -abs(r["pct_a"] - r["pct_b"]), r["id"]))
    result["rows"] = rows
    result["n_significant"] = sum(1 for r in rows if r["q"] < 0.05)
    return result


def group_compare_figures(result, label_a="Group A", label_b="Group B"):
    rows = result["rows"]
    if not rows:
        return {}
    data = []
    for name, keep, colour in (("q < 0.05", lambda r: r["q"] < 0.05, "#d62728"),
                               ("not significant", lambda r: r["q"] >= 0.05, "#9aa0a6")):
        sel = [r for r in rows if keep(r)]
        if sel:
            data.append({"type": "scatter", "mode": "markers", "name": name,
                         "x": [r["pct_a"] for r in sel], "y": [r["pct_b"] for r in sel],
                         "text": [f"{r['id']} {r['name']}<br>p = {r['p']:.3g}, q = {r['q']:.3g}" for r in sel],
                         "hovertemplate": "%{text}<br>A %{x}% · B %{y}%<extra></extra>",
                         "marker": {"color": colour, "size": 8, "opacity": 0.7}})
    return {"prevalence": {"data": data, "layout": {
        "height": 460, "margin": {"t": 20},
        "xaxis": {"title": {"text": f"Bins carrying it in {label_a} (%)"}, "range": [-3, 103]},
        "yaxis": {"title": {"text": f"Bins carrying it in {label_b} (%)"}, "range": [-3, 103]},
        "shapes": [{"type": "line", "x0": 0, "y0": 0, "x1": 100, "y1": 100, "line": {"dash": "dot", "color": "#bbbbbb"}}]}}}
