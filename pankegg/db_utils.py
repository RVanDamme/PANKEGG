# db_utils.py

import sqlite3
import csv
import glob
import logging
import os
from .sql_commands import *
from .binnames import normalise_bin_name, bin_name_from_annotation_file
from .classification import (METHODS as CLASSIFICATION_METHODS, ClassificationError,
                             apply_sample, detect_file_type, resolve_sample)

log = logging.getLogger("pankegg")


def connect_db(path):
    return sqlite3.connect(path)


def create_tables(cur):
    for table, sql in CREATE_TABLES.items():
        cur.execute(sql)
    # conn.commit()


def drop_all_tables(cur, tables):
    for table in tables:
        cur.execute(DROP_TABLE.format(table_name=table))
    # conn.commit()


def drop_table(conn, table_name):
    cur = conn.cursor()
    cur.execute(DROP_TABLE.format(table_name=table_name))
    conn.commit()


def insert_taxonomy(cur, tax_data):
    # Check if entry exist already
    cur.execute(SELECT_TAXONOMY_ID, tax_data[2:9])
    result = cur.fetchone()
    if result:
        return result[0]
    else:
        # Insert new taxonomic entry
        cur.execute(INSERT_TAXONOMY, tax_data[2:9])
        return cur.lastrowid


def get_or_create_taxonomy(cur, ranks):
    """Id of the taxonomy row with exactly these 7 ranks (NULLs included), created if needed."""
    ranks = tuple(ranks)
    cur.execute(SELECT_TAXONOMY_ID, ranks)
    result = cur.fetchone()
    if result:
        return result[0]
    cur.execute(INSERT_TAXONOMY, ranks)
    return cur.lastrowid


def insert_bin(cur, bin_name, taxonomic_id, sample_id):
    cur.execute(SELECT_BIN_ID, (bin_name, sample_id))
    bin_id = cur.fetchone()
    if not bin_id:  # Insert only if the bin does not exist for this sample
        cur.execute(INSERT_BIN, (bin_name, taxonomic_id, sample_id))

def load_pathways(pathway_file):
    """Load Pathways data from file and store in a dict."""
    pathways_dict = {}
    with open(pathway_file, 'r') as file:
        reader = csv.reader(file, delimiter='\t')
        for row in reader:
            map_id = row[0].strip()
            pathway_description = row[1].strip() if len(row) > 1 else None
            # pathways_orthologs_number = int(row[2].strip())
            pathways_orthologs_number = row[2].split(",")
            #  print(pathways_orthologs_number)
            #  pathways_dict[map_id] = pathway_description
            pathways_dict[map_id] = [pathway_description, pathways_orthologs_number]
    return pathways_dict


def load_ko_descriptions(ko_file):
    """Load Kegg orthologs description from file and store in a dict."""
    ko_dict = {}
    with open(ko_file, 'r') as file:
        reader = csv.reader(file, delimiter='\t')
        for row in reader:
            ko_id = row[0].strip()
            description = row[1].split(";") if len(row) > 1 else ["Unknown"]
            ko_dict[ko_id] = description
    return ko_dict

def read_eggnog_annotations(path):
    """Read an eggNOG-mapper annotation file (brief §3.5).

    Accepts the raw file written by emapper (several '##' lines, a header line
    starting with '#query', '##' footer lines) and the legacy stripped file
    (one '##' line, then the header). Every line starting with '##' is ignored;
    the header is the line starting with '#query' (or, failing that, the first
    remaining line).

    Returns (fieldnames, rows) with rows as dicts keyed by the header.
    """
    with open(path, 'r', newline='', encoding='utf-8-sig') as fh:
        lines = [line for line in fh if not line.startswith('##')]
    start = next((i for i, line in enumerate(lines) if line.startswith('#query')), 0)
    reader = csv.DictReader(lines[start:], delimiter='\t')
    rows = list(reader)
    return list(reader.fieldnames or []), rows


# Tests

# Input CSV Validation
def check_input_csv(input_csv):
    required_cols = {'Sample name', 'Annotation_dir', 'classification_dir', 'Checkm2_dir'}
    sample_names = set()
    with open(input_csv, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("the input CSV is empty (expected the header line "
                             "'Sample name,Annotation_dir,classification_dir,Checkm2_dir')")
        if not required_cols.issubset(reader.fieldnames):
            raise ValueError(f"CSV missing required columns: {required_cols - set(reader.fieldnames)}")
        for i, row in enumerate(reader, 2):
            for field in required_cols:
                if not row.get(field):
                    raise ValueError(f"Blank field '{field}' at line {i}")
            name = row['Sample name']
            if name in sample_names:
                raise ValueError(f"Duplicate sample name '{name}' at line {i}")
            sample_names.add(name)


# File Existence and Header Detection
def check_required_files_and_headers(csv_file):
    failures = []
    required_annot_cols = {'KEGG_Pathway', 'KEGG_ko'}
    required_quality_cols = {'Name', 'Completeness', 'Contamination'}
    with open(csv_file, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 2):
            sample = row['Sample name']
            ann_files = sorted(glob.glob(row['Annotation_dir']))
            if not ann_files:
                failures.append((i, sample, f"No annotation files found for pattern: {row['Annotation_dir']}"))
            for annot in ann_files:
                try:
                    header, _ = read_eggnog_annotations(annot)
                    if not header:
                        failures.append((i, sample, f"Annotation file {annot} is empty"))
                        continue
                    if not required_annot_cols.issubset(header):
                        failures.append((i, sample, f"Annotation file {annot} missing columns: {required_annot_cols - set(header)}"))
                except Exception as e:
                    failures.append((i, sample, f"Cannot read annotation file {annot}: {e}"))
            q_files = sorted(glob.glob(row['Checkm2_dir']))
            if not q_files:
                failures.append((i, sample, f"No quality report files found for pattern: {row['Checkm2_dir']}"))
            for qfile in q_files:
                try:
                    with open(qfile, 'r', encoding='utf-8-sig') as qf:
                        header = qf.readline().strip().split('\t')
                        if not required_quality_cols.issubset(header):
                            failures.append((i, sample, f"Quality file {qfile} missing columns: {required_quality_cols - set(header)}"))
                except Exception as e:
                    failures.append((i, sample, f"Cannot read quality file {qfile}: {e}"))
    return failures


# Database Schema Verification
def check_db_schema(cur):
    expected_tables = {'bin', 'taxonomy', 'sample', 'map', 'kegg', 'bin_map', 'map_kegg', 'bin_extra', 'bin_extra_kegg', 'bin_map_kegg'}
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = set(name for (name,) in cur.fetchall())
    if not expected_tables.issubset(tables):
        missing = expected_tables - tables
        raise RuntimeError(f"Database is missing tables: {missing}")


# Bin Mapping Consistency
def check_bin_consistency(cur):
    cur.execute("SELECT bin.id, bin.bin_name FROM bin LEFT JOIN taxonomy ON bin.taxonomic_id=taxonomy.id WHERE taxonomy.id IS NULL")
    missing_taxa = cur.fetchall()
    cur.execute("SELECT bin.id, bin.bin_name FROM bin LEFT JOIN sample ON bin.sample_id=sample.id WHERE sample.id IS NULL")
    missing_sample = cur.fetchall()
    issues = []
    if missing_taxa:
        issues.append(f"Bins missing taxonomy: {[b for _, b in missing_taxa]}")
    if missing_sample:
        issues.append(f"Bins missing sample: {[b for _, b in missing_sample]}")
    return issues


# File Read/Parse Exception Wrapper
def safe_open_file(filepath, mode='r', encoding=None):
    try:
        return open(filepath, mode, encoding=encoding) if encoding else open(filepath, mode)
    except Exception as e:
        raise IOError(f"Failed to open {filepath}: {e}")


# Flask DB Connection Test (to use in pankegg_app.py)
def print_db_status(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("[Flask] Tables in DB:", [r[0] for r in cur.fetchall()])


# Duplicate/Blank Bin Name Check (per sample)
def check_duplicate_bins(cur, sample_id):
    cur.execute("SELECT bin_name, COUNT(*) FROM bin WHERE sample_id=? GROUP BY bin_name HAVING COUNT(*)>1", (sample_id,))
    duplicates = cur.fetchall()
    return [b for b, _ in duplicates]


# Classification mode check
def resolve_classifications(csv_file, requested='auto'):
    """Choose and read the classification files of every sample before the DB is written.

    Returns (plan, failures, warnings): plan maps sample name to
    (method, records); failures and warnings are (line, sample, message) tuples.
    """
    plan, failures, warnings = {}, [], []
    with open(csv_file, 'r', newline='', encoding='utf-8-sig') as f:
        for i, row in enumerate(csv.DictReader(f), 2):  # line numbers as in the file (header = 1)
            sample = row['Sample name']
            try:
                method, records, notes = resolve_sample(row['classification_dir'], requested)
            except (ClassificationError, OSError, UnicodeDecodeError, csv.Error) as e:
                failures.append((i, sample, str(e)))
                continue
            plan[sample] = (method, records)
            warnings.extend((i, sample, n) for n in notes)
    return plan, failures, warnings


def check_classification_mode_per_row(csv_file, gtdbtk_flag=False):
    """2.0.0 interface: failures only. gtdbtk_flag=True requires GTDB-Tk files, otherwise auto-detect."""
    return resolve_classifications(csv_file, 'gtdbtk' if gtdbtk_flag else 'auto')[1]


# Data process

# def process_pathways_and_kos(cur, pathway, maps_dict, pathways_dict, kos, bin_map_list):
#     if pathway not in bin_map_list:
#         bin_map_list.append(pathway)
#
#     if pathway not in maps_dict:
#         # Tente d'insérer le pathway dans la base de données si ce n'est pas déjà fait
#         description = pathways_dict.get(pathway, "Description not available")  # Utilise une description par défaut si non trouvée
#         cur.execute(INSERT_MAP, (description, pathway, pathway))
#         maps_dict[pathway] = kos
#     else:
#         map_ko_list = maps_dict.get(pathway)
#         original_length = len(map_ko_list)
#         map_ko_list.extend([ko for ko in kos if ko not in map_ko_list])
#         if len(map_ko_list) > original_length:
#             maps_dict[pathway] = map_ko_list


def process_pathways_and_kos(cur, pathway, maps_dict, pathways_dict, kos, bin_map_list):
    """
    Process the pathways and associated KEGG Orthology identifiers (KOs), and inserts them into the database.

    Args:
        cur (sqlite3.Cursor): Database cursor for executing SQL commands.
        pathway (str): The pathway map number (e.g., "map00010").
        maps_dict (dict): Dictionary tracking the current state of pathways and associated KOs in the database.
        pathways_dict (dict): Dictionary containing pathway descriptions and number of orthologs.
        kos (list): List of KEGG Orthology identifiers associated with the pathway.
        bin_map_list (list): List tracking which pathways have been processed.
    """
    if pathway not in bin_map_list:
        bin_map_list.append(pathway)

    if pathway not in maps_dict:
        # Retrieve the pathway information from the pathways_dict, using a default if not found
        pathway_info = pathways_dict.get(pathway, ["Description not available", []])
        description, total_orthologs = pathway_info  # Extract both description and total orthologs

        # Attempt to insert the pathway into the database if it's not already done
        cur.execute(INSERT_MAP, (description, pathway, len(total_orthologs), pathway))
        maps_dict[pathway] = kos

    else:
        # If the pathway is already in maps_dict, update it with any new KOs
        map_ko_list = maps_dict.get(pathway, []).copy()
        original_length = len(map_ko_list)
        # Extend the list only with new, unique KOs
        map_ko_list.extend([ko for ko in kos if ko not in map_ko_list])
        if len(map_ko_list) > original_length:
            maps_dict[pathway] = map_ko_list


def link_bins_to_pathways(cur, bin_name, bin_map_list, sample_id):
    for map_number in bin_map_list:
        cur.execute(SELECT_BIN_ID, (bin_name, sample_id))  # Include sample_id
        bin_id = cur.fetchone()
        if bin_id:
            bin_id = bin_id[0]
            cur.execute(SELECT_MAP_ID, (map_number,))
            map_id = cur.fetchone()
            if map_id:
                map_id = map_id[0]
                cur.execute(INSERT_BIN_MAP, (bin_id, map_id, bin_id, map_id))


def link_maps_to_kos(cur, maps_dict, map_translate_table):
    for map_name in maps_dict:
        cur.execute(SELECT_MAP_ID, (map_name,))
        map_id = cur.fetchone()
        if map_id:
            map_id = map_id[0]
            for ko in maps_dict.get(map_name):
                if not ko == "":
                    ko_entry = ko.split(":")[1]
                    map_kegg_list = map_translate_table.get(map_name, [None, []])[1]
                    # try:
                    #     map_kegg_list = map_translate_table.get(map_name)[1]
                    # except:
                    #     map_kegg_list = []
                    ko_is_in_map = 0
                    if ko_entry in map_kegg_list:
                        ko_is_in_map = 1

                    cur.execute(SELECT_KEGG_ID, (ko_entry,))
                    ko_id = cur.fetchone()
                    if ko_id:
                        ko_id = ko_id[0]
                        # Insert joint in bin_map if doesn't exist
                        cur.execute(INSERT_MAP_KEGG, (map_id, ko_id, ko_is_in_map, map_id, ko_id, ko_is_in_map))


def add_bin_quality_values(cur, quality_report_path, sample_id):  # Include sample_id
    """CheckM2 values; quality_report_path may be a glob pattern (all matching reports are read)."""
    for path in sorted(glob.glob(quality_report_path)) or [quality_report_path]:
        with open(path, 'r', newline='', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for line, row in enumerate(reader, 2):
                bin_name = normalise_bin_name(row['Name'])
                try:
                    completeness = float(row['Completeness'])
                    contamination = float(row['Contamination'])
                except (TypeError, ValueError):
                    raise ValueError(f"{path} line {line}: Completeness and Contamination must be numbers "
                                     f"(bin {bin_name!r})") from None

                # Update with sample_id to ensure correct association
                cur.execute(UPDATE_BIN_QUALITY, (completeness, contamination, bin_name, sample_id))


def set_ko(cur, kegg_translate_table, maps_dict):
    unique_kos = set()
    for kos in maps_dict.values():
        unique_kos.update(kos)
    unique_ko_list = sorted(unique_kos)  # sorted: same kegg ids whatever the hash seed
    for ko in unique_ko_list:
        if not ko == "":
            ko_id = ko.split(":")[1]
            kegg_info = kegg_translate_table.get(ko_id)
            if kegg_info:
                kegg_name = kegg_info[0]
                kegg_full_name = kegg_info[1]
                cur.execute(INSERT_KEGG, (ko_id, kegg_name, kegg_full_name, ko_id))

            else:
                cur.execute(INSERT_KEGG, (ko_id, "null", "null", ko_id))


def process_classifications(cur, sample_id, method, records):
    """Store bin classifications for one sample (every mode); bins without one become unclassified."""
    return apply_sample(cur, sample_id, method, records, get_or_create_taxonomy)


def sample_preliminary_process(cur, annotation_files_path, sample_id):
    for filename in sorted(glob.glob(annotation_files_path)):
        name_part = bin_name_from_annotation_file(filename)

        cur.execute(SELECT_BIN_ID, (name_part, sample_id))  # Ensure unique bins per sample
        bin_id = cur.fetchone()
        if not bin_id:
            insert_bin(cur, name_part, None, sample_id)  # classification set later


def process_annotation_file(cur, annotation_files_path, pathways_dict, sample_id):
    maps_dict = {}

    for filename in sorted(glob.glob(annotation_files_path)):
        bin_name = bin_name_from_annotation_file(filename)
        fieldnames, rows = read_eggnog_annotations(filename)

        # Ensure 'KEGG_Pathway' exists
        if 'KEGG_Pathway' not in fieldnames:
            log.warning(f"Skipping {filename}: 'KEGG_Pathway' column not found")
            continue

        bin_map_list = []
        for row in rows:
            kegg_pathways = row.get('KEGG_Pathway', '')  # Use get() to avoid KeyError
            kegg_kos = row.get('KEGG_ko', '')

            kos = kegg_kos.split(',')
            if kegg_pathways:
                for pathway in kegg_pathways.split(','):
                    pathway = pathway.strip()
                    if pathway.startswith('map'):
                        process_pathways_and_kos(cur, pathway, maps_dict, pathways_dict, kos, bin_map_list)
            else:
                pathway = bin_name + "_not_mapped"
                process_pathways_and_kos(cur, pathway, maps_dict, pathways_dict, kos, bin_map_list)

        link_bins_to_pathways(cur, bin_name, bin_map_list, sample_id)

    return maps_dict

def link_full_line_with_kos(cur, bin_id, kegg_gos, kegg_kos, kegg_free_desc):
    # Insert the full annotation line
    cur.execute(INSERT_BIN_EXTRA, (bin_id, kegg_gos, kegg_kos, kegg_free_desc))
    kegg_extra_line_id = cur.lastrowid

    if kegg_extra_line_id and kegg_kos:  # Ensure kegg_kos is not None or empty
        kos = kegg_kos.split(',')
        for ko in kos:
            if ":" not in ko:  # Skip invalid KO entries
                #print(f"Skipping invalid KEGG_ko entry: {ko}")
                continue

            ko_entry = ko.split(":")[1]  # Extract KO ID safely

            # Check if KO entry exists in the database
            cur.execute(SELECT_KEGG_ID, (ko_entry,))
            ko_id = cur.fetchone()

            if ko_id:
                ko_id = ko_id[0]
                cur.execute(INSERT_BIN_EXTRA_KEGG, (kegg_extra_line_id, ko_id, kegg_extra_line_id, ko_id))
            else:
                #print(f"Warning: KEGG ID {ko_entry} not found in the database")
                continue


def set_full_annot_table(cur, annotation_files_path, sample_id):
    for filename in sorted(glob.glob(annotation_files_path)):
        bin_name = bin_name_from_annotation_file(filename)

        cur.execute(SELECT_BIN_ID, (bin_name, sample_id))
        bin_id = cur.fetchone()
        if not bin_id:
            continue
        bin_id = bin_id[0]

        fieldnames, rows = read_eggnog_annotations(filename)
        if 'KEGG_ko' not in fieldnames:
            log.warning(f"Skipping {filename}: 'KEGG_ko' column not found")
            continue  # Skip this file instead of crashing

        for row in rows:
            # Use get() to avoid crashing
            kegg_kos = row.get('KEGG_ko', None)
            kegg_gos = row.get('GOs', None)
            kegg_free_desc = row.get('eggNOG free text desc.', None)

            if kegg_kos:
                link_full_line_with_kos(cur, bin_id, kegg_gos, kegg_kos, kegg_free_desc)

# def link_bin_to_map_keg(cur, annotation_files_path):
#     for filename in sorted(glob.glob(annotation_files_path)):
#         with open(filename, 'r', newline='') as file:
#             base_name = os.path.basename(filename)
#             name_part = base_name.split('.')[0] + '.' + base_name.split('.')[1]
#             bin_name = name_part + ".fa"
#
#             cur.execute(SELECT_BIN_ID, (bin_name,))
#             bin_id = cur.fetchone()[0]  # Supposons qu'il y a toujours un bin_id valide
#
#             reader = csv.DictReader(file, delimiter='\t')
#             for row in reader:
#                 kegg_pathways = row['KEGG_Pathway']
#                 kegg_kos = row['KEGG_ko']
#                 kos = kegg_kos.split(',')
#
#                 for pathway in kegg_pathways.split(',') if kegg_pathways else [name_part + "_not_mapped"]:
#                     pathway = pathway.strip()
#                     if pathway.startswith('map'):
#                         cur.execute(SELECT_MAP_ID, (pathway,))
#                         map_id = cur.fetchone()[0]
#
#                         for ko_entry in kos:
#                             ko_id = ko_entry.split(":")[1]
#                             cur.execute(SELECT_KEGG_ID, (ko_id,))
#                             kegg_id = cur.fetchone()[0]  # Supposons que kegg_id est toujours valide
#
#                             cur.execute(SELECT_MAP_KEGG_ID, (map_id, kegg_id,))
#                             map_kegg_id = cur.fetchone()[0]  # Supposons que map_kegg_id est toujours valide
#
#                             cur.execute(INSERT_BIN_MAP_KEGG, (bin_id, map_kegg_id, bin_id, map_kegg_id))


def count_map_kegg_ids(cur):
    query = """
    SELECT map_kegg_id, COUNT(bin_id) as bin_count
    FROM bin_map_kegg
    GROUP BY map_kegg_id
    ORDER BY bin_count DESC;
    """
    cur.execute(query)
    results = cur.fetchall()
    return results


def total_shared_associations(cur):
    # Sum the shared association
    # Where each bin_count is the number of bins sharing the same map_kegg_id.
    query = """
    SELECT SUM(bin_count)
    FROM (
        SELECT COUNT(bin_id) as bin_count
        FROM bin_map_kegg
        GROUP BY map_kegg_id
    ) as counts;
    """
    cur.execute(query)
    result = cur.fetchone()  # Fetch the result which is the total sum of shared associations
    return result[0] if result else 0  # Return the sum or 0 if the result is None


def link_kegg_to_map(cur, kos, map_id, bin_id):
    for ko_entry in kos:
        if ko_entry:
            ko_id = ko_entry.split(":")[1]
            cur.execute(SELECT_KEGG_ID, (ko_id,))
            kegg_id = cur.fetchone()[0]  # Consider kegg_id as always valid

            cur.execute(SELECT_MAP_KEGG_ID, (map_id, kegg_id,))
            map_kegg_id = cur.fetchone()[0]  # Consider map_kegg_id as always valid

            cur.execute(INSERT_BIN_MAP_KEGG, (bin_id, map_kegg_id, bin_id, map_kegg_id))


def link_bin_to_map_keg(cur, annotation_files_path, sample_id):
    for filename in sorted(glob.glob(annotation_files_path)):
        bin_name = bin_name_from_annotation_file(filename)

        cur.execute(SELECT_BIN_ID, (bin_name, sample_id))
        bin_id = cur.fetchone()
        if not bin_id:
            log.warning(f"No bin found for {bin_name} ({filename})")
            continue
        bin_id = bin_id[0]

        fieldnames, rows = read_eggnog_annotations(filename)
        log.debug(f"Reading {filename}: bin {bin_name}, {len(rows)} rows, columns {fieldnames}")

        no_pathway = 0
        for row in rows:
            if 'KEGG_Pathway' not in row:
                no_pathway += 1
                continue  # Skip row if the column is missing

            kegg_pathways = row.get('KEGG_Pathway', '')  # Use .get() to avoid KeyError
            kegg_kos = row.get('KEGG_ko', '')

            if not kegg_pathways or kegg_pathways == '-':
                no_pathway += 1
                continue  # Skip empty pathway rows

            kos = kegg_kos.split(',')

            for pathway in kegg_pathways.split(','):
                pathway = pathway.strip()
                if pathway.startswith('map'):
                    cur.execute(SELECT_MAP_ID, (pathway,))
                    map_id = cur.fetchone()
                    if not map_id:
                        log.debug(f"No map found for pathway {pathway} ({filename})")
                        continue
                    map_id = map_id[0]

                    link_kegg_to_map(cur, kos, map_id, bin_id)

        if no_pathway:
            log.debug(f"{filename}: {no_pathway} rows without a KEGG pathway")

def add_sample_in_db(cur, name):
    cur.execute(INSERT_SAMPLE, (name,))
    return cur.lastrowid
