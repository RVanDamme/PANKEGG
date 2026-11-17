import sqlite3
import argparse
import pytest

import pankegg_make_db
from pankegg.db_utils import check_db_schema


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


def test_make_db_offline(tmp_path, monkeypatch):
    """Same call style as above (2.0.0 namespace, no new options), offline fixtures."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(repo)
    args = argparse.Namespace(
        input=str(repo / "tests" / "fixtures" / "db_2.0.0" / "s1_lca_input.csv"),
        output="test_db",
        output_dir=str(tmp_path),
        gtdbtk=False,
    )
    monkeypatch.setattr(pankegg_make_db, "parse_arguments", lambda: args)
    assert pankegg_make_db.main() == 0
    conn = sqlite3.connect(tmp_path / "test_db.db")
    check_db_schema(conn.cursor())
    assert conn.execute("SELECT COUNT(*) FROM bin").fetchone()[0] == 3
    conn.close()
