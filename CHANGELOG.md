# Changelog

All notable changes to PANKEGG. Versions follow [semantic versioning](https://semver.org/).

## [2.1.0] — unreleased

Makes `pankegg_make_db` usable as an installed standalone tool and as a step of the
MUFFIN nf-core pipeline. Existing commands, input CSVs and databases keep working.

### Added — web app
- **Overview** page replaces the static home: counts, bin quality tiers per sample, completeness and
  contamination, taxonomy sunburst, classification confidence, per-sample summary, most widespread
  and rarest pathways.
- **Bin details** page for every bin (`/bin/<id>`), linked from the bin list.
- **Pathway Stats** reworked: search by pathway name or map ID, KO × bin matrix, completeness per
  sample, mean completeness by taxon, KOs of the map found in no bin, optional exclusion of
  unclassified bins, CSV exports.
- **Modules**: KEGG module completeness per bin, with a steps × bins view of what is missing.
- **Pathways by taxon** (with functional redundancy), **Core and accessory**, **Similarity**
  (clustered Jaccard heatmap between samples or bins) and **Compare two groups** (Fisher's exact
  test per pathway, KO or module with Benjamini–Hochberg q-values). All with CSV export.
- Sample metadata is used to colour the sample PCA and to group samples or bins by condition.
- Plotly 2.35.2 and Bootstrap 5.3.3 are shipped in the package: the app works without internet.
- The existing completeness measure is now called **pathway per-ID completeness**, and every page
  that shows it or module completeness explains the difference.

### Added — database builder
- **KEGG module completeness** per bin (new tables `module`, `bin_module`), computed from all KOs
  of a bin and the 583 KEGG module definitions shipped in `pankegg/data/kegg_modules.tsv`. Completeness
  is the mean score of the module's steps (best alternative per step; partly present steps count
  partly); a module is complete at 100%.
- **`--metadata FILE`**: sample metadata as a `sample<TAB>condition` file with free-text conditions;
  with a header, any number of variables (new table `sample_metadata`).
- **KOs without a KEGG pathway are kept** (`KEGG_Pathway` = `-`). They were dropped before, so
  rebuilt databases hold more KOs (OSF Sourmash example: 1,580 → 2,514); nothing is removed.
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
- `scripts/generate_input_sourmash_tax_by_sample.sh` and `scripts/generate_input_sourmash_tax_by_tool.sh`.
- `Checkm2_dir` accepts glob patterns like the other CSV columns.
- `pankegg_app` also reads `FLASK_SECRET_KEY` from a `.env` file in the directory it is started from (or a parent directory).
- Classification globs: directories and binary files are skipped with a warning; a pattern whose directory does not exist is an error; UTF-8 byte-order marks are accepted in every input.

### Fixed
- Web app: the "Both" column of the common-pathways tables was the sum of the two samples, not
  their overlap; Bin vs Bin mixed bins that have the same name in different samples; the bin PCA
  failed with fewer than 3 bins and the taxonomy heatmap with a single taxon; `/bin_query` returned
  an error; names and search terms shown in page titles are escaped; an unknown taxonomic rank
  in a URL is rejected instead of reaching the database.
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
- Repository tidied: the `generate_input_*.sh` helper scripts moved to `scripts/`; the unused
  `pankegg/data/sample_path.csv` (local paths of a developer's computer) and the unreferenced
  `pip_requirements.txt` (duplicating `pyproject.toml`) were removed; dead code removed.
- **`pankegg_app` listens on `127.0.0.1` with the Flask debugger off** (it was `0.0.0.0` with the
  debugger on, which let anyone on the network run code on the computer). New options `--host`,
  `--port` and `--debug`; use `--host 0.0.0.0` to serve other computers.
- The Map and Kegg pages are **paginated** (25 pathways or 100 KOs per page by default; 25, 50, 100
  or 250 selectable) and sorted by ID. Filters are kept across pages and exports still contain
  everything. On the OSF example the Kegg page went from 9.2 MB to 0.4 MB.
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
