# Changelog

All notable changes to PANKEGG. Versions follow [semantic versioning](https://semver.org/).

## [2.1.0] — unreleased

Makes `pankegg_make_db` usable as an installed standalone tool and as a step of the
MUFFIN nf-core pipeline. Existing commands, input CSVs and databases keep working.

### Added
- **`sourmash tax genome` input** (`--output-format csv_summary`, `*.classifications.csv`):
  one or several bins per file; bin name from `query_name`; `below_threshold` calls are
  stored with their partial lineage.
- **`--classification auto|sourmash_tax|sourmash_lca|gtdbtk`**. `auto` (default) recognises
  the format of each sample from the file headers. `--gtdbtk` is kept as an alias of
  `--classification gtdbtk`.
- **Two packages from one source**: `pankegg` (database builder + web app, as before) and
  `pankegg-makedb` (database builder only, no dependencies beyond the Python standard
  library), built with `python tools/build_makedb.py`.
- `--version` for `pankegg_make_db` and `pankegg_app`; `-q/--quiet` and `-v/--verbose`.
- Database (additive, schema 2.1): `bin.classification_method`, `bin.classification_status`
  and a `pankegg_info` table (`pankegg_version`, `schema_version`, `classification_methods`).
  Databases from 2.0.0 still open in `pankegg_app`.
- `generate_input_sourmash_tax_by_sample.sh` and `generate_input_sourmash_tax_by_tool.sh`.
- `Checkm2_dir` accepts glob patterns like the other CSV columns.
- `pankegg_app` also reads `FLASK_SECRET_KEY` from a `.env` file in the directory it is started from (or a parent directory).
- Classification globs: directories and binary files are skipped with a warning; a pattern whose directory does not exist is an error; UTF-8 byte-order marks are accepted in every input.

### Fixed
- `pip install` (not editable) produced a broken `pankegg_make_db`: KEGG reference data,
  templates and the example database were not installed. They now live inside the
  `pankegg` package.
- Raw eggNOG-mapper output (several `##` lines before the `#query` header, `##` footer) was
  rejected; every `##` line is now ignored. Stripped files give identical results.
- Bin names: the "first two dot-separated parts" rule broke names such as `SemiBin_12` or
  `a.b.c`, and only `.fa` was removed from IDs. One rule now applies to all inputs: strip
  `.emapper.annotations`, `.annotations.tsv`, `.annotations` and `.fa`/`.fna`/`.fasta`
  (optionally `.gz`).
- `sourmash lca classify` files: every row is read (only the first was), and empty or
  header-only files no longer crash.
- Bins without a classification are stored as unclassified in every mode. Previously
  `sourmash lca` `nomatch` bins kept a dangling `taxonomic_id` (`'null'`) and were hidden
  from most app pages. GTDB-Tk `Unclassified …` genomes are unclassified too.
- The web app counted unclassified bins as classified in the taxonomy chart.
- Same inputs now always give the same database (input files sorted; row ids no longer
  depend on the Python hash seed).
- Errors go to stderr with exit status 1 (2 for usage errors) and no traceback; a failed run
  leaves no partial database and keeps an existing one. Output reduced from thousands of
  lines to one per sample. Help text in English.

### Changed
- Code moved from `lib/` and the top-level scripts into the `pankegg` package
  (`pankegg.make_db`, `pankegg.app`, …). `python pankegg_make_db.py` and
  `python pankegg_app.py` still work from a copy of the repository. The top-level `lib`
  module is no longer installed.
- Packaging metadata in `pyproject.toml` (`setup.py` and `MANIFEST.in` removed); the version
  is defined once in `pankegg/__init__.py`. Requires Python ≥ 3.9 (3.13 recommended).
- `pytest` is no longer a runtime dependency (`pip install "pankegg[dev]"` for tests).
- Tests run offline from small fixtures; `pytest --run-osf` adds the comparison with the
  OSF example data and the 2.0.0 databases. CI no longer hides CLI failures and tests a
  clean install of both packages.

## [2.0.0]

See the [GitHub release](https://github.com/RVanDamme/PANKEGG/releases/tag/2.0.0).
