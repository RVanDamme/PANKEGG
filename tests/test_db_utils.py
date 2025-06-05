import os
import sqlite3
import csv

import pytest

from lib.db_utils import (
    load_pathways,
    load_ko_descriptions,
    check_input_csv,
    check_required_files_and_headers,
    check_classification_mode_per_row,
    check_db_schema,
    check_bin_consistency,
    check_duplicate_bins,
)

TEST_DATA_URL = "https://osf.io/download/5v3zc/"

def test_load_pathways_basic():
    path = os.path.join('data', 'kegg_map_orthologs.tsv')
    pathways = load_pathways(path)
    assert 'map00010' in pathways, "Known pathway 'map00010' should be loaded"
    assert isinstance(pathways['map00010'], list), "Expected list of KOs for 'map00010'"

def test_load_ko_descriptions_basic():
    path = os.path.join('data', 'ko.txt')
    ko = load_ko_descriptions(path)
    assert 'K00001' in ko, "Expected KO 'K00001' to be loaded"

def test_check_input_csv_duplicate(tmp_path):
    csv_path = tmp_path / 'input.csv'
    with csv_path.open('w') as f:
        f.write('Sample name,Annotation_dir,classification_dir,Checkm2_dir\n')
        f.write('sample1,a,b,c\n')
        f.write('sample1,a2,b2,c2\n')
    with pytest.raises(ValueError):
        check_input_csv(str(csv_path))

def test_check_input_csv_missing_column(tmp_path):
    csv_path = tmp_path / 'input.csv'
    with csv_path.open('w') as f:
        f.write('Sample name,Annotation_dir,classification_dir\n')
        f.write('sample1,a,b\n')
    with pytest.raises(ValueError):
        check_input_csv(str(csv_path))

def test_check_required_files_and_headers_success(test_data_dir):
    csv_file = test_data_dir / 'sourmash_example.csv'
    failures = check_required_files_and_headers(str(csv_file))
    assert failures == [], f"Unexpected header or file issues: {failures}"

def test_check_classification_mode(test_data_dir):
    csv_file = test_data_dir / 'sourmash_example.csv'
    failures = check_classification_mode_per_row(str(csv_file), gtdbtk_flag=False)
    assert failures == [], f"Classification mode mismatches: {failures}"

def test_db_schema_valid(test_data_dir):
    db_path = test_data_dir / 'sourmash_example.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        check_db_schema(cur)
    except RuntimeError as e:
        pytest.fail(f"Database schema invalid: {e}")
    conn.close()

def test_bin_consistency(test_data_dir):
    db_path = test_data_dir / 'sourmash_example.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    assert check_bin_consistency(cur) == [], "Inconsistent bins detected"
    conn.close()

def test_check_duplicate_bins(test_data_dir):
    db_path = test_data_dir / 'sourmash_example.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id FROM sample')
    sample_ids = [row[0] for row in cur.fetchall()]
    for sid in sample_ids:
        assert check_duplicate_bins(cur, sid) == [], f"Duplicate bins found for sample {sid}"
    conn.close()

