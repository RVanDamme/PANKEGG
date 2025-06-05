import sqlite3
import argparse
import pytest

import pankegg_make_db
from lib.db_utils import check_db_schema

@pytest.mark.usefixtures('test_data_dir')
def test_make_db_sourmash(tmp_path, test_data_dir, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    args = argparse.Namespace(
        input=str(test_data_dir / "sourmash_example.csv"),
        output="test_db",
        output_dir=str(output_dir),
        gtdbtk=False,
    )
    monkeypatch.setattr(pankegg_make_db, "parse_arguments", lambda: args)
    pankegg_make_db.main()
    db_path = output_dir / "test_db.db"
    assert db_path.exists(), "Database file was not created"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        check_db_schema(cur)
    except RuntimeError as e:
        pytest.fail(f"Generated database schema invalid: {e}")
    conn.close()

