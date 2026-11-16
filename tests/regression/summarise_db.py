"""Summarise a PANKEGG database by names, not by internal row IDs.

Used to compare databases built by different PANKEGG versions: the row IDs
may differ (input files are processed in sorted order since 2.1.0), but the
samples, bins, taxonomy, quality values and every link between bins, maps and
KOs must be the same.

Usage:  python tests/regression/summarise_db.py DB.sqlite > summary.json
"""

import hashlib
import json
import sqlite3
import sys

RANKS = ["_kingdom_", "_phylum_", "_class_", "_order_", "_family_", "_genus_", "_species_"]


def _digest(rows):
    """Order-independent digest of a multiset of tuples."""
    lines = sorted(json.dumps(list(r), ensure_ascii=False) for r in rows)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _taxonomy(row):
    """Taxonomy as a list of 7 ranks, or None when the bin is unclassified.

    2.0.0 stored unclassified bins either with a dangling taxonomic_id (the text
    'null') or linked to a row where every rank is NULL; both mean the same.
    """
    if row is None or all(v is None for v in row):
        return None
    return list(row)


def summarise(db_path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    summary = {"samples": {}, "global": {}}

    samples = cur.execute("SELECT id, sample_name FROM sample ORDER BY sample_name").fetchall()
    for sample_id, sample_name in samples:
        bins = {}
        for bin_id, bin_name, comp, cont, tax_id in cur.execute(
            "SELECT id, bin_name, completeness, contamination, taxonomic_id FROM bin WHERE sample_id=?",
            (sample_id,),
        ).fetchall():
            tax = cur.execute(
                f"SELECT {', '.join(RANKS)} FROM taxonomy WHERE id=?", (tax_id,)
            ).fetchone()
            bins[bin_name] = {
                "completeness": comp,
                "contamination": cont,
                "taxonomy": _taxonomy(tax),
            }

        bin_map = cur.execute(
            """SELECT b.bin_name, m.map_number FROM bin_map bm
               JOIN bin b ON b.id=bm.bin_id JOIN map m ON m.id=bm.map_id
               WHERE b.sample_id=?""",
            (sample_id,),
        ).fetchall()
        bin_map_kegg = cur.execute(
            """SELECT b.bin_name, m.map_number, k.ko_id, mk.real_pathway_id FROM bin_map_kegg bmk
               JOIN bin b ON b.id=bmk.bin_id JOIN map_kegg mk ON mk.id=bmk.map_kegg_id
               JOIN map m ON m.id=mk.map_id JOIN kegg k ON k.id=mk.kegg_id
               WHERE b.sample_id=?""",
            (sample_id,),
        ).fetchall()
        bin_extra = cur.execute(
            """SELECT b.bin_name, e.go, e.ko, e.eggnog_desc FROM bin_extra e
               JOIN bin b ON b.id=e.bin_id WHERE b.sample_id=?""",
            (sample_id,),
        ).fetchall()
        bin_extra_kegg = cur.execute(
            """SELECT b.bin_name, e.ko, k.ko_id FROM bin_extra_kegg ek
               JOIN bin_extra e ON e.id=ek.extra_id JOIN bin b ON b.id=e.bin_id
               JOIN kegg k ON k.id=ek.kegg_id WHERE b.sample_id=?""",
            (sample_id,),
        ).fetchall()

        summary["samples"][sample_name] = {
            "n_bins": len(bins),
            "bins": dict(sorted(bins.items())),
            "counts": {
                "bin_map": len(bin_map),
                "bin_map_kegg": len(bin_map_kegg),
                "bin_extra": len(bin_extra),
                "bin_extra_kegg": len(bin_extra_kegg),
            },
            "digests": {
                "bin_map": _digest(bin_map),
                "bin_map_kegg": _digest(bin_map_kegg),
                "bin_extra": _digest(bin_extra),
                "bin_extra_kegg": _digest(bin_extra_kegg),
            },
        }

    kegg = cur.execute("SELECT ko_id, kegg_name, kegg_full_name FROM kegg").fetchall()
    maps = cur.execute("SELECT map_number, pathway_name, pathway_total_orthologs FROM map").fetchall()
    map_kegg = cur.execute(
        """SELECT m.map_number, k.ko_id, mk.real_pathway_id FROM map_kegg mk
           JOIN map m ON m.id=mk.map_id JOIN kegg k ON k.id=mk.kegg_id"""
    ).fetchall()
    summary["global"] = {
        "counts": {"kegg": len(kegg), "map": len(maps), "map_kegg": len(map_kegg)},
        "digests": {"kegg": _digest(kegg), "map": _digest(maps), "map_kegg": _digest(map_kegg)},
    }
    con.close()
    return summary


if __name__ == "__main__":
    json.dump(summarise(sys.argv[1]), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


# --- comparing with a 2.0.0 database when content was added on purpose ----------------------
# Since 2.1.0, KOs whose KEGG_Pathway is '-' are kept: the kegg table and the bin_extra_kegg
# links grow. Everything else must be identical, and nothing that 2.0.0 stored may disappear.

GROWING = ("kegg", "bin_extra_kegg")


def unchanged_part(summary):
    """The summary without the tables that are allowed to grow."""
    out = json.loads(json.dumps(summary))
    for key in GROWING:
        out["global"]["counts"].pop(key, None)
        out["global"]["digests"].pop(key, None)
        for sample in out["samples"].values():
            sample["counts"].pop(key, None)
            sample["digests"].pop(key, None)
    return out


def _growing_rows(db_path):
    con = sqlite3.connect(db_path)
    kegg = set(con.execute("SELECT ko_id, kegg_name, kegg_full_name FROM kegg"))
    links = set(con.execute(
        """SELECT s.sample_name, b.bin_name, e.ko, e.go, e.eggnog_desc, k.ko_id FROM bin_extra_kegg ek
           JOIN bin_extra e ON e.id=ek.extra_id JOIN bin b ON b.id=e.bin_id
           JOIN sample s ON s.id=b.sample_id JOIN kegg k ON k.id=ek.kegg_id"""))
    con.close()
    return kegg, links


def added_since_2_0_0(old_db, new_db):
    """Assert that the 2.0.0 KOs and KO links are all still there; return what was added."""
    old_kegg, old_links = _growing_rows(old_db)
    new_kegg, new_links = _growing_rows(new_db)
    assert old_kegg <= new_kegg, f"KOs lost: {sorted(old_kegg - new_kegg)[:5]}"
    assert old_links <= new_links, f"KO links lost: {sorted(old_links - new_links)[:5]}"
    return {"kegg": len(new_kegg - old_kegg), "bin_extra_kegg": len(new_links - old_links)}
