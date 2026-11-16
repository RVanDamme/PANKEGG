"""pankegg_make_db: build a PANKEGG SQLite database from eggNOG-mapper,
CheckM2 and bin-classification (sourmash or GTDB-Tk) outputs.

Uses only the Python standard library.
"""

import argparse
import csv
import logging
import os
import sys
import traceback

from . import __version__, resource_path
from .db_utils import *
from .modules import ModuleSet, load_modules

log = logging.getLogger("pankegg")

default_pathway_file = resource_path('data', 'kegg_map_orthologs.tsv')
default_ko_file = resource_path('data', 'ko.txt')
default_module_file = resource_path('data', 'kegg_modules.tsv')

TABLES_TO_DROP = [
    'taxonomy', 'bin', 'map', 'kegg', 'bin_map_kegg',
    'bin_map', 'map_kegg', 'bin_extra', 'bin_extra_kegg',
    'sample', 'pankegg_info', 'module', 'bin_module', 'sample_metadata'
]

EPILOG = """\
input CSV (-i), one row per sample:
  Sample name,Annotation_dir,classification_dir,Checkm2_dir
  Each path may be a glob pattern; relative paths are resolved from the
  current directory.
    Annotation_dir      eggNOG-mapper annotations, one file per bin
                        (*.emapper.annotations raw from emapper, or the
                        stripped *.annotations.tsv of earlier MUFFIN runs)
    classification_dir  sourmash tax genome csv_summary files, sourmash lca
                        classify CSVs, or GTDB-Tk *.summary.tsv
    Checkm2_dir         CheckM2 quality report(s) (Name, Completeness,
                        Contamination)

bin names:
  A bin has the same name in all three inputs after removing
  .emapper.annotations / .annotations.tsv / .annotations from annotation file
  names and .fa / .fna / .fasta (optionally .gz) from any identifier.
  Bins without a classification are stored as unclassified.

exit status: 0 on success, 1 on an input or processing error, 2 on a usage
error. Messages go to stderr; no partial database is left on failure.
"""


class InputError(Exception):
    """Inputs that cannot be used; the message explains which and why."""


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        prog='pankegg_make_db',
        description='Build a PANKEGG SQLite database from eggNOG-mapper annotations, '
                    'CheckM2 quality reports and bin classifications (sourmash or GTDB-Tk).',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--version', action='version', version=f'pankegg_make_db {__version__}')
    parser.add_argument('-i', '--input', required=True, help='Path to the input CSV file (see below).')
    parser.add_argument('-o', '--output', default='pankegg',
                        help='Name of the output database, without extension (default: pankegg).')
    parser.add_argument('--output_dir', default='./db_output',
                        help='Directory for the output database (default: ./db_output).')
    parser.add_argument(
        '--classification', choices=('auto',) + CLASSIFICATION_METHODS, default='auto',
        help='Bin classification input: sourmash_tax (sourmash tax genome csv_summary), '
             'sourmash_lca (sourmash lca classify), gtdbtk (GTDB-Tk *.summary.tsv), or auto '
             '(default: detected per sample from the file headers).')
    parser.add_argument(
        '--metadata', metavar='FILE',
        help='Sample metadata: a tab-separated file with one line per sample, "sample<TAB>condition". '
             'Conditions are free text. With a header line starting with "sample", any number of '
             'further columns are stored as variables. Used by pankegg_app to colour and group samples.')
    parser.add_argument('--gtdbtk', action='store_true',
                        help='Same as --classification gtdbtk (kept for compatibility).')
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument('-q', '--quiet', action='store_true', help='Print only warnings and errors.')
    verbosity.add_argument('-v', '--verbose', action='store_true', help='Print details for every input file.')
    return parser.parse_args(argv)


def classification_mode(args):
    """--classification, with the 2.0.0 --gtdbtk flag as an alias of --classification gtdbtk."""
    mode = getattr(args, 'classification', 'auto') or 'auto'
    if getattr(args, 'gtdbtk', False):
        if mode not in ('auto', 'gtdbtk'):
            raise InputError(f"--gtdbtk conflicts with --classification {mode}")
        mode = 'gtdbtk'
    return mode


def setup_logging(args):
    level = logging.INFO
    if getattr(args, 'quiet', False):
        level = logging.WARNING
    elif getattr(args, 'verbose', False):
        level = logging.DEBUG
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    log.handlers[:] = [handler]
    log.setLevel(level)
    log.propagate = False


def _line_failures(title, failures):
    return title + "\n" + "\n".join(f"  Line {line} (Sample {sample}): {msg}" for line, sample, msg in failures)


def validate_inputs(args):
    """Check the input CSV and every file it points to; read the classifications. No DB access."""
    csv_file_path = args.input
    if not os.path.isfile(csv_file_path):
        raise InputError(f"input CSV not found: {csv_file_path}")
    try:
        check_input_csv(csv_file_path)
    except ValueError as e:
        raise InputError(f"{csv_file_path}: {e}") from None

    failures = check_required_files_and_headers(csv_file_path)
    if failures:
        raise InputError(_line_failures("File/existence/content issues detected:", failures))

    mode = classification_mode(args)
    plan, failures, notes = resolve_classifications(csv_file_path, mode)
    if failures:
        raise InputError(_line_failures("Classification input problems:", failures))
    for line, sample, msg in notes:
        log.warning(f"Line {line} (Sample {sample}): {msg}")

    metadata = ([], {})
    metadata_file = getattr(args, 'metadata', None)
    if metadata_file:
        if not os.path.isfile(metadata_file):
            raise InputError(f"metadata file not found: {metadata_file}")
        try:
            variables, values, warnings = read_sample_metadata(metadata_file, list(plan))
        except (ValueError, UnicodeDecodeError, csv.Error) as e:
            raise InputError(str(e)) from None
        for msg in warnings:
            log.warning(msg)
        metadata = (variables, values)
    return mode, plan, metadata


def build_database(cur, csv_file_path, plan, metadata=((), {})):
    drop_all_tables(cur, TABLES_TO_DROP)
    create_tables(cur)
    check_db_schema(cur)

    ko_translate_table = load_ko_descriptions(default_ko_file)
    map_translate_table = load_pathways(default_pathway_file)
    module_set = ModuleSet(load_modules(default_module_file))
    module_ids = add_modules(cur, module_set)

    with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as csvfile:
        for row in csv.DictReader(csvfile):
            sample = row['Sample name']
            annotation_path = row['Annotation_dir']
            checkm2_dir = row['Checkm2_dir']
            method, records = plan[sample]

            sample_id = add_sample_in_db(cur, sample)
            add_sample_metadata(cur, sample_id, metadata[1].get(sample, {}))
            sample_preliminary_process(cur, annotation_path, sample_id)
            not_annotated = process_classifications(cur, sample_id, method, records)
            if not_annotated:
                log.debug(f"Sample {sample}: classified bins without annotation file, ignored: {not_annotated}")
            add_bin_quality_values(cur, checkm2_dir, sample_id)
            map_ko_dict = process_annotation_file(cur, annotation_path, map_translate_table, sample_id)
            set_ko(cur, ko_translate_table, map_ko_dict)
            add_all_kos(cur, ko_translate_table, annotation_path)  # also KOs without a pathway
            link_maps_to_kos(cur, map_ko_dict, map_translate_table)
            set_full_annot_table(cur, annotation_path, sample_id)
            link_bin_to_map_keg(cur, annotation_path, sample_id)
            add_bin_modules(cur, annotation_path, sample_id, module_set, module_ids)

            duplicates = check_duplicate_bins(cur, sample_id)
            if duplicates:
                log.warning(f"Duplicate bins for sample {sample}: {duplicates}")
            n_bins, n_classified = cur.execute(
                "SELECT COUNT(*), SUM(COALESCE(t._kingdom_, '') != '') "
                "FROM bin b LEFT JOIN taxonomy t ON t.id = b.taxonomic_id WHERE b.sample_id = ?",
                (sample_id,)).fetchone()
            log.info(f"Sample {sample}: {n_bins} bins, {n_classified or 0} classified ({method or 'none'})")

    issues = check_bin_consistency(cur)
    if issues:
        log.warning(f"Bin mapping issues: {issues}")

    methods = sorted({m for m, _ in plan.values() if m})
    for key, value in (('pankegg_version', __version__), ('schema_version', SCHEMA_VERSION),
                       ('classification_methods', ','.join(methods)),
                       ('metadata_variables', ','.join(metadata[0]))):
        cur.execute(INSERT_INFO, (key, value))


def run(args):
    mode, plan, metadata = validate_inputs(args)

    os.makedirs(args.output_dir, exist_ok=True)
    database_path = os.path.abspath(os.path.join(args.output_dir, f'{args.output}.db'))
    log.info(f"Building {database_path} from {len(plan)} sample(s), classification: {mode}")

    # Write to a temporary file and move it into place at the end, so a failed
    # run never leaves a partial database (and keeps an existing one intact).
    tmp_path = f"{database_path}.tmp-{os.getpid()}"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    try:
        conn = connect_db(tmp_path)
        try:
            cur = conn.cursor()
            build_database(cur, args.input, plan, metadata)
            conn.commit()
            cur.close()
        finally:
            conn.close()
        os.replace(tmp_path, database_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    log.info(f"Database written: {database_path}")
    return database_path


def main(argv=None):
    args = parse_arguments() if argv is None else parse_arguments(argv)
    setup_logging(args)
    try:
        run(args)
    except InputError as e:
        log.error(str(e))
        return 1
    except Exception as e:  # report, do not dump a traceback unless --verbose
        log.error(f"{type(e).__name__}: {e}")
        log.debug(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
