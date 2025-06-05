#!/usr/bin/env python

# main.py
import argparse
import os
import sys
import csv
from lib.db_utils import *
from importlib.resources import files

def get_resource_path(relative_path):
    """
    Returns the absolute path to a resource file.
    If running as __main__, resolves relative to this script's directory.
    Otherwise (imported as a package), attempts to use importlib.resources.
    """
    # Try importlib.resources if available and __package__ is set
    try:
        if __package__:
            from importlib.resources import files
            return str(files(__package__) / relative_path)
    except Exception:
        pass
    # Fallback: use file relative to the script location
    return os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))

default_db_path = get_resource_path('data/pankegg.db')
default_pathway_file = get_resource_path('data/kegg_map_orthologs.tsv')
default_ko_file = get_resource_path('data/ko.txt')
default_csv_file = get_resource_path('data/sample_path.csv')

TABLES_TO_DROP = [
    'taxonomy', 'bin', 'map', 'kegg', 'bin_map_kegg',
    'bin_map', 'map_kegg', 'bin_extra', 'bin_extra_kegg',
    'sample'
]

def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Process KEGG data and store it in a database.',
        epilog='Format du fichier CSV attendu: Sample name, Annotation_dir, classification_dir, Checkm2_dir'
    )
    parser.add_argument('-i', '--input', required=True, help='Path to the input CSV file.')
    parser.add_argument('-o', '--output', default='pankegg', help='Name for the output database file (without extension).')
    parser.add_argument('--output_dir', default='./db_output', help='Directory path for the output database file.')
    parser.add_argument('--gtdbtk', action='store_true', help='Use GTDBtk classification instead of Sourmash')
    return parser.parse_args()

def main():
    print("Starting...")
    args = parse_arguments()
    csv_file_path = args.input
    database_name = args.output
    directory_output = args.output_dir

    if not directory_output.endswith('/'):
        directory_output += '/'
    if not os.path.exists(directory_output):
        os.makedirs(directory_output)
    
    # Test 1: Output path validation
    database_path = os.path.join(directory_output, f'{database_name}.db')
    print(f"[DEBUG] Output DB path: {os.path.abspath(database_path)}")  

    # TEST 2: Input CSV validation
    try:
        check_input_csv(csv_file_path)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # TEST 3: File existence and content
    failures = check_required_files_and_headers(csv_file_path)
    if failures:
        print("[ERROR] File/existence/content issues detected:")
        for line, sample, msg in failures:
            print(f"  Line {line} (Sample {sample}): {msg}")
        sys.exit(1)

    # TEST 9: Classification mode (gtdbtk/sourmash) consistency
    failures = check_classification_mode_per_row(csv_file_path, args.gtdbtk)
    if failures:
        print("[ERROR] Classification mode mismatch detected on these lines:")
        for line, sample, msg in failures:
            print(f"  Line {line} (Sample {sample}): {msg}")
        sys.exit(1)

    # DB creation
    conn = connect_db(database_path)
    cur = conn.cursor()
    drop_all_tables(cur, TABLES_TO_DROP)
    create_tables(cur)

    # TEST 4: Schema check
    try:
        check_db_schema(cur)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Load auxiliary data
    ko_translate_table = load_ko_descriptions(default_ko_file)
    map_translate_table = load_pathways(default_pathway_file)

    # Main loading loop
    with open(csv_file_path, mode='r', newline='') as csvfile:
        csvreader = csv.DictReader(csvfile)
        for row in csvreader:
            sample = row['Sample name']
            annotation_path = row['Annotation_dir']
            sourmash_txt_dir = row['classification_dir']
            checkm2_dir = row['Checkm2_dir']

            print("Processing:", sample)
            sample_id = add_sample_in_db(cur, sample)
            sample_preliminary_process(cur, annotation_path, sample_id)
            if args.gtdbtk:
                process_gtdbtk_taxonomy_files(cur, sourmash_txt_dir, annotation_path, sample_id)
            else:
                process_taxonomy_files(cur, sourmash_txt_dir, sample_id)
            add_bin_quality_values(cur, checkm2_dir, sample_id)
            map_ko_dict = process_annotation_file(cur, annotation_path, map_translate_table, sample_id)
            set_ko(cur, ko_translate_table, map_ko_dict)
            link_maps_to_kos(cur, map_ko_dict, map_translate_table)
            set_full_annot_table(cur, annotation_path, sample_id)
            link_bin_to_map_keg(cur, annotation_path, sample_id)

            # TEST 8: Per-sample duplicate bins
            duplicates = check_duplicate_bins(cur, sample_id)
            if duplicates:
                print(f"[WARN] Duplicate bins for sample {sample}: {duplicates}")

    # TEST 5: Bin mapping consistency check (orphans)
    issues = check_bin_consistency(cur)
    if issues:
        print(f"[WARN] Bin mapping issues: {issues}")

    conn.commit()
    cur.close()
    conn.close()

    print("Programme successfully completed.")
    print("Database:", database_name, "Created at directory:", database_path)

if __name__ == "__main__":
    main()

