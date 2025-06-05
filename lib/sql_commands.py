# sql_commands.py

CREATE_TABLES = {
    "taxonomy": """
        CREATE TABLE IF NOT EXISTS taxonomy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            _kingdom_ VARCHAR(255),
            _phylum_ VARCHAR(255),
            _class_ VARCHAR(255),
            _order_ VARCHAR(255),
            _family_ VARCHAR(255),
            _genus_ VARCHAR(255),
            _species_ VARCHAR(255)
        );
    """,
    "sample": """
        CREATE TABLE IF NOT EXISTS sample (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_name VARCHAR(255),
            metadata VARCHAR(255)
        );
    """,
    "bin": """
        CREATE TABLE IF NOT EXISTS bin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_name VARCHAR(255),
            completeness FLOAT,
            contamination FLOAT,
            taxonomic_id INT,
            sample_id INT,
            FOREIGN KEY (taxonomic_id) REFERENCES taxonomy(id),
            FOREIGN KEY (sample_id) REFERENCES sample(id)
        );
    """,
    "map": """
        CREATE TABLE IF NOT EXISTS map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pathway_name VARCHAR(255),
            map_number INT,
            pathway_total_orthologs INT
        );
    """,
    "kegg": """
        CREATE TABLE IF NOT EXISTS kegg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ko_id VARCHAR(255),
            kegg_name VARCHAR(255),
            kegg_full_name VARCHAR(255)
        );
    """,
    "bin_map": """
        CREATE TABLE IF NOT EXISTS bin_map (
            bin_id INT,
            map_id INT,
            PRIMARY KEY (bin_id, map_id),
            FOREIGN KEY (bin_id) REFERENCES bin(id),
            FOREIGN KEY (map_id) REFERENCES map(id)
        );
    """,
    "map_kegg": """
        CREATE TABLE IF NOT EXISTS map_kegg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INT,
            kegg_id INT,
            real_pathway_id INT,
            FOREIGN KEY (map_id) REFERENCES map(id),
            FOREIGN KEY (kegg_id) REFERENCES kegg(id)
        );
    """,
    "bin_extra": """
        CREATE TABLE IF NOT EXISTS bin_extra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id INT,
            go VARCHAR(255),
            ko VARCHAR(255),
            eggnog_desc VARCHAR(255),
            FOREIGN KEY (bin_id) REFERENCES bin(id)
        );
    """,
    "bin_extra_kegg": """
        CREATE TABLE IF NOT EXISTS bin_extra_kegg (
            extra_id INT,
            kegg_id INT,
            PRIMARY KEY (extra_id, kegg_id),
            FOREIGN KEY (extra_id) REFERENCES bin_extra(id),
            FOREIGN KEY (kegg_id) REFERENCES kegg(id)
        );
    """,
    "bin_map_kegg": """
        CREATE TABLE IF NOT EXISTS bin_map_kegg (
            bin_id INT,
            map_kegg_id INT,
            PRIMARY KEY (bin_id, map_kegg_id),
            FOREIGN KEY (bin_id) REFERENCES bin(id),
            FOREIGN KEY (map_kegg_id) REFERENCES map_kegg(id)
    );
    """
}

# Delete Table
DROP_TABLE = "DROP TABLE IF EXISTS {table_name}"

# Insert different data
INSERT_TAXONOMY = """
    INSERT INTO taxonomy (_kingdom_, _phylum_, _class_, _order_, _family_, _genus_, _species_)
    VALUES (?, ?, ?, ?, ?, ?, ?);
"""

INSERT_BIN = """
    INSERT INTO Bin (bin_name, taxonomic_id, sample_id)
    VALUES (?, ?, ?);
"""

INSERT_SAMPLE = """
    INSERT INTO sample (sample_name)
    VALUES (?);
"""

# Select data
SELECT_TAXONOMY_ID = """
    SELECT id FROM taxonomy WHERE
    _kingdom_ = ? AND _phylum_ = ? AND _class_ = ? AND _order_ = ? AND
    _family_ = ? AND _genus_ = ? AND _species_ = ?;
"""

# sql_commands.py

# Commands to insert data in tables

# INSERT_MAP = """
#     INSERT INTO map (pathway_name, map_number)
#     SELECT ?, ?
#     WHERE NOT EXISTS (
#         SELECT 1 FROM map WHERE map_number = ?
#     );
# """

INSERT_MAP = """
    INSERT INTO map (pathway_name, map_number, pathway_total_orthologs)
    SELECT ?, ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM map WHERE map_number = ?
    );
"""

INSERT_KEGG = """
    INSERT INTO kegg (ko_id, kegg_name, kegg_full_name)
    SELECT ?, ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM kegg WHERE ko_id = ?
    );
"""

INSERT_BIN_MAP = """
    INSERT INTO bin_map (bin_id, map_id)
    SELECT ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM bin_map WHERE bin_id = ? AND map_id = ?
    );
"""

INSERT_MAP_KEGG = """
    INSERT INTO map_kegg (map_id, kegg_id, real_pathway_id)
    SELECT ?, ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM map_kegg WHERE map_id = ? AND kegg_id = ? AND real_pathway_id = ?
    );
"""

SELECT_MAP_ID = "SELECT id FROM map WHERE map_number = ?"

SELECT_MAP_KEGG_ID = "SELECT id FROM map_kegg WHERE map_id = ? AND kegg_id = ?"

SELECT_KEGG_ID = "SELECT id FROM kegg WHERE ko_id = ?"

INSERT_BIN_EXTRA = """
    INSERT INTO bin_extra (bin_id, go, ko, eggnog_desc) VALUES (?, ?, ?, ?);
"""

INSERT_BIN_EXTRA_KEGG = """
    INSERT INTO bin_extra_kegg (extra_id, kegg_id)
    SELECT ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM bin_extra_kegg WHERE extra_id = ? AND kegg_id = ?
    );
"""

INSERT_BIN_MAP_KEGG = """
    INSERT INTO bin_map_kegg (bin_id, map_kegg_id)
    SELECT ?, ?
    WHERE NOT EXISTS (
        SELECT 1 FROM bin_map_kegg WHERE bin_id = ? AND map_kegg_id = ?
    );
"""

SELECT_BIN_ID = "SELECT id FROM bin WHERE bin_name = ? AND sample_id = ?"

# SELECT_BIN_ID = "SELECT id FROM bin WHERE bin_name = ?"

UPDATE_BIN_QUALITY = """
   UPDATE Bin SET completeness = ?, contamination = ? WHERE bin_name = ? AND sample_id = ?

"""

UPDATE_BIN_TAXONOMY = """
   UPDATE Bin SET taxonomic_id = ? WHERE bin_name = ? AND sample_id = ?
"""
