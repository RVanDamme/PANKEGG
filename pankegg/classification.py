"""Bin classification inputs (brief §3.1-3.3, §4).

Three formats, detected from the header line:

* ``sourmash_tax`` - ``sourmash tax genome --output-format csv_summary``
  (``query_name``, ``status``, ``lineage``; one or many rows per file)
* ``sourmash_lca`` - ``sourmash lca classify`` (``ID``, ``status``, ranks)
* ``gtdbtk``       - GTDB-Tk ``*.summary.tsv`` (``user_genome``, ``classification``)

Readers yield ``(bin_name, status, ranks)`` where ``ranks`` is a list of the
seven ranks kingdom..species, or ``None`` for "no classification". Every bin
known from the annotation files but absent from the classification files is
stored as unclassified (one shared taxonomy row with all ranks NULL) with
status ``absent``.
"""

import csv
import glob

from .binnames import normalise_bin_name

METHODS = ("sourmash_tax", "sourmash_lca", "gtdbtk")
RANKS = 7
UNCLASSIFIED = (None,) * RANKS
ABSENT = "absent"  # status of a bin with no row in any classification file


class ClassificationError(ValueError):
    """Classification inputs that cannot be used; the message names the file(s)."""


def detect_file_type(path):
    """``sourmash_tax``, ``sourmash_lca``, ``gtdbtk``, ``empty`` or ``unknown`` from the header line."""
    with open(path, "r", newline="", encoding="utf-8") as fh:
        first = fh.readline()
    if not first.strip():
        return "empty"
    delimiter = "\t" if "\t" in first else ","
    header = {h.strip() for h in next(csv.reader([first], delimiter=delimiter))}
    if {"user_genome", "classification"} <= header:
        return "gtdbtk"
    if {"query_name", "status", "lineage"} <= header:
        return "sourmash_tax"
    if {"ID", "status"} <= header:
        return "sourmash_lca"
    return "unknown"


def _pad(ranks):
    ranks = list(ranks)[:RANKS]
    return ranks + [None] * (RANKS - len(ranks))


def read_sourmash_tax(path):
    """``sourmash tax genome`` csv_summary. The bin is ``query_name`` (not ``query_filename``).

    ``below_threshold`` rows keep their (possibly truncated) lineage; missing
    ranks are NULL (decision P3). ``nomatch`` or an empty lineage is unclassified.
    """
    with open(path, "r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = normalise_bin_name(row.get("query_name") or "")
            if not name:
                continue
            status = (row.get("status") or "").strip()
            lineage = (row.get("lineage") or "").strip()
            if status == "nomatch" or not lineage or lineage.lower() == "unclassified":
                yield name, status, None
            else:
                yield name, status, _pad(r.strip() or None for r in lineage.split(";"))


def read_sourmash_lca(path):
    """``sourmash lca classify``: every row (F6). Rank values are kept as written
    (empty ranks stay empty strings, as in PANKEGG 2.0.0); ``nomatch`` is unclassified."""
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for row in reader:
            if not row or not row[0].strip():
                continue
            name = normalise_bin_name(row[0])
            status = row[1].strip() if len(row) > 1 else ""
            if status == "nomatch":
                yield name, status, None
            else:
                yield name, status, (row[2:2 + RANKS] + [""] * RANKS)[:RANKS]


def read_gtdbtk(path):
    """GTDB-Tk summary. 'Unclassified ...' labels and empty classifications are unclassified."""
    with open(path, "r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            name = normalise_bin_name(row.get("user_genome") or "")
            if not name:
                continue
            tax_line = (row.get("classification") or "").strip()
            if not tax_line or tax_line.lower().startswith("unclassified"):
                yield name, "unclassified", None
            else:
                yield name, "classified", _pad(t if t else None for t in tax_line.split(";"))


READERS = {"sourmash_tax": read_sourmash_tax, "sourmash_lca": read_sourmash_lca, "gtdbtk": read_gtdbtk}


def resolve_sample(pattern, requested="auto"):
    """Pick the reader for one sample's classification files and read them.

    Returns ``(method, records, warnings)`` where ``records`` maps bin name to
    ``(status, ranks)``. ``method`` is ``None`` only in auto mode when the
    sample has no classification file at all. Raises ClassificationError.
    """
    files = sorted(glob.glob(pattern))
    kinds = {fp: detect_file_type(fp) for fp in files}
    by_kind = {}
    for fp, kind in kinds.items():
        by_kind.setdefault(kind, []).append(fp)
    known = sorted(k for k in by_kind if k in METHODS)
    warnings = []

    if len(known) > 1:
        detail = "; ".join(f"{k}: {', '.join(by_kind[k])}" for k in known)
        raise ClassificationError(f"mixed classification types in one sample ({detail})")
    if requested != "auto" and known and known[0] != requested:
        raise ClassificationError(
            f"--classification {requested} was requested but these files are {known[0]}: "
            + ", ".join(by_kind[known[0]]))
    if not known and by_kind.get("unknown"):
        raise ClassificationError(
            "No recognizable classification files found: " + ", ".join(by_kind["unknown"]))
    for fp in by_kind.get("unknown", []):
        warnings.append(f"ignoring {fp}: not a recognised classification file")
    if not files:
        warnings.append(f"no classification file matches {pattern!r}; all bins of this sample are unclassified")

    method = known[0] if known else (None if requested == "auto" else requested)
    records, origin = {}, {}
    for fp in by_kind.get(method, []):
        for name, status, ranks in READERS[method](fp):
            value = (status, tuple(ranks) if ranks is not None else None)
            if name in records and records[name] != value:
                raise ClassificationError(
                    f"bin {name!r} is classified differently in {origin[name]} and {fp}")
            records[name], origin[name] = value, fp
    return method, records, warnings


def apply_sample(cur, sample_id, method, records, get_taxonomy_id):
    """Store the classification of every bin of one sample; unlisted bins become unclassified.

    Returns the bin names that appear in the classification files but not in the annotations.
    """
    known = {name for (name,) in cur.execute("SELECT bin_name FROM bin WHERE sample_id = ?", (sample_id,))}
    for name in sorted(records):
        if name not in known:
            continue
        status, ranks = records[name]
        tax_id = get_taxonomy_id(cur, ranks if ranks is not None else UNCLASSIFIED)
        cur.execute(
            "UPDATE bin SET taxonomic_id = ?, classification_method = ?, classification_status = ? "
            "WHERE bin_name = ? AND sample_id = ?",
            (tax_id, method, status, name, sample_id))
    for name in sorted(known - set(records)):
        tax_id = get_taxonomy_id(cur, UNCLASSIFIED)
        cur.execute(
            "UPDATE bin SET taxonomic_id = ?, classification_method = ?, classification_status = ? "
            "WHERE bin_name = ? AND sample_id = ?",
            (tax_id, method, ABSENT, name, sample_id))
    return sorted(set(records) - known)
