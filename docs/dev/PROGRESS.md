# PANKEGG update — progress

Specification: [`PANKEGG_update_brief.md`](PANKEGG_update_brief.md) (the kickoff prompt calls it `UPDATE_BRIEF.md`; same document).
Branch: `Update_Sourmash` (based on master `c09bf8a` + brief + fixtures).

## Now

- **Step:** done (all 10 steps). Waiting for the owner: merge, tag 2.1.0, publish (see `docs/dev/RELEASE.md`).
- **Next action:** none until the owner decides on the open points below.

## Steps

- [x] 0. Progress file, CI runs on this branch
- [x] 1. Baseline from OSF example CSVs (regression reference)
- [x] 2. Packaging: `pankegg` (full) + `pankegg-makedb` (light), single version, console scripts, `--version`, clean-install test
- [x] 3. Bin-name normalisation (brief 3.4)
- [x] 4. eggNOG reader: raw and legacy files (brief 3.5)
- [x] 5. Classification modes, tax genome reader, lca all rows, unclassified everywhere, schema additions
- [x] 6. CLI behaviour: stderr/exit codes, `--quiet`/`--verbose`, deterministic output, English help
- [x] 7. App check against new and 2.0.0 databases
- [x] 8. Offline tests, optional OSF test, CI without `|| true`, clean-install job, no committed `__pycache__`
- [x] 9. Docs, tax genome helper script, CHANGELOG
- [x] 10. Independent review against brief §7, fixes, acceptance report, release instructions

## Decisions

| Date | # | Decision |
|---|---|---|
| 2026-11-16 | P1 | Version **2.1.0**. 3.0.0 is kept for future integrations. |
| 2026-11-16 | P2 | `pip install pankegg` installs **everything** (make_db + web app). A separate light distribution **`pankegg-makedb`** installs only `pankegg_make_db` (standard library only). Both are built from this repo and ship the same `pankegg` import package; install one or the other (same pattern as `opencv-python` / `opencv-python-headless`). |
| 2026-11-16 | P3 | `below_threshold` rows from `sourmash tax genome`: store the partial lineage (missing ranks NULL) and record the status. |
| 2026-11-16 | P4 | Record classification method and status in the DB, additive only (new nullable columns on `bin`, new `pankegg_info` table, no timestamp). App must open 2.0.0 DBs. |
| 2026-11-16 | P5 | Publish to PyPI and Bioconda, mirroring P2: `pankegg` = full package, `pankegg-makedb` = parsing/DB-building only. Claude writes the steps; the owner tags and publishes. |
| 2026-11-16 | P6 | Add a `sourmash tax genome` variant of the input-CSV helper scripts. |
| 2026-11-16 | P7 | Normalise every "no classification" representation (lca `nomatch`, missing row, missing file, the old text `'null'` taxonomic_id) to one unclassified taxonomy row with all ranks NULL, as GTDB-Tk mode already does. |
| 2026-11-16 | — | Python: `requires-python >= 3.9`; recommended and primary test version 3.13; CI also tests 3.9. Raise the floor if a dependency forces it. |
| 2026-11-16 | — | Internal row IDs may differ from 2.0.0 (input files are sorted); allowed as long as samples, bins and all links between them are unchanged. Regression compares by names, not IDs. |
| 2026-11-16 | — | Tests run offline from fixtures committed in `tests/fixtures`; the OSF download test is optional. |
| 2026-11-16 | — | Bin names (step 3): `pankegg/binnames.py` strips `.emapper.annotations` / `.annotations.tsv` / `.annotations` from annotation file names and `.fa`/`.fna`/`.fasta` (+`.gz`) from every identifier. An annotation file without a known suffix keeps the 2.0.0 rule (first two dot parts) with a warning, so old inputs give the same DB. Side effect: the per-bin `<bin>_not_mapped` pseudo-pathway now uses the normalised name; it differs from 2.0.0 only when the annotation file name carried a FASTA extension before the suffix (e.g. `x.fa.emapper.annotations`: 2.0.0 `x.fa_not_mapped`, now `x_not_mapped`). |
| 2026-11-16 | P4 | Schema 2.1 (additive): `bin.classification_method` (`sourmash_tax`/`sourmash_lca`/`gtdbtk`) and `bin.classification_status` (tool status verbatim: `match`, `below_threshold`, `nomatch`, `found`, `disagree`; GTDB-Tk `classified`/`unclassified`; `absent` = bin has no row in any classification file); table `pankegg_info(key, value)` with `pankegg_version`, `schema_version`, `classification_methods`. |
| 2026-11-16 | P7 | Applied: lca `nomatch`, tax genome `nomatch`/empty lineage, GTDB-Tk `Unclassified …` labels and bins absent from every file all point to one shared taxonomy row with all ranks NULL. Taxonomy lookup uses `IS` so NULL-containing lineages are reused instead of duplicated (2.0.0 GTDB-Tk mode created one all-NULL row per unclassified bin). Non-empty ranks keep 2.0.0 values (lca empty ranks stay `''`, GTDB-Tk `s__` stays `s__`). |
| 2026-11-16 | — | Classification inputs (step 5): `--classification auto` is the default, so an old command without `--gtdbtk` on GTDB-Tk files now works instead of failing. Errors (before the DB is opened): mixed types in a sample, an explicit mode contradicting the files, only unrecognised files, the same bin classified differently in two files. Warnings: unrecognised files next to recognised ones (2.0.0 ignored them silently), no classification file at all (every bin unclassified, the "all bins unmatched" case). Bins present in a classification file but not in the annotations are ignored, as in 2.0.0. |
| 2026-11-16 | — | CLI (step 6): all messages via `logging` to stderr as `[LEVEL] message`; stdout stays empty. Default: one line per sample plus start/end (OSF example: 5 lines instead of 9,603); `-q/--quiet` warnings and errors only; `-v/--verbose` per-file details and tracebacks. Exit 0 / 1 (input or processing error) / 2 (usage). The DB is written to `<name>.db.tmp-<pid>` and moved into place at the end: no partial DB on failure, an existing DB survives a failed run. All globs sorted; KOs inserted in sorted order (2.0.0 iterated a `set`, so row ids depended on `PYTHONHASHSEED`). `Checkm2_dir` now accepts a glob like the other columns. |
| 2026-11-16 | — | App (step 7): one fix needed. Visualisation → taxonomy counted a bin as classified when it had any taxonomy row; with P7 unclassified bins have one (all NULL), so it now also requires a non-empty kingdom. This also corrects the count for 2.0.0 GTDB-Tk DBs. Composition charts now show lca `nomatch` bins as `Unknown` (as GTDB-Tk DBs already did) instead of leaving them out. All main pages serve 200 on 2.0.0 and new DBs (`tests/test_app.py`; real server checked with curl). |
| 2026-11-16 | — | Tests (step 8): default `pytest` is offline (no network attempt) and uses `tests/fixtures`; OSF tests are marked `osf` and run with `pytest --run-osf`. The OSF fixture no longer changes the working directory for the whole session (it did, which made later tests depend on test order). CI: `test` (Python 3.9 + 3.13, offline), `osf-regression`, `clean-install` (`python -m build` + `tools/build_makedb.py`, fresh venvs, run from an empty directory), `test-conda` (conda-lock env); no `\|\| true` left. |
| 2026-11-16 | — | Docs (step 9): `.qmd` sources and `README.md` edited together (README had drifted from the sources, so edits were made by hand, not regenerated). New: classification inputs table, bin-naming rule, the two packages, pipeline command lines, schema 2.1 columns, how to compare a new DB with a 2.0.0 one by content. Helper scripts `generate_input_sourmash_tax_by_{sample,tool}.sh` (tested). App also reads `.env` from the directory it is started from: after the move into `pankegg/`, installed users had no "PANKEGG dir" to put it in. `CHANGELOG.md` added. |
| 2026-11-16 | — | Review (step 10, fresh subagent, no blocker/major): fixed C1 directories/binary files in a classification glob crashed the run → skipped with a warning; C2 a `classification_dir` whose directory does not exist exited 0 with all bins unclassified → error (an existing empty directory is still allowed); C3 empty input CSV gave `TypeError` → clear message; C4 per-sample log counted classified bins by status → by taxonomy; C5 UTF-8 BOM rejected → accepted in every input; doc fixes (stale repo layout in CONTRIBUTING/reporting_bugs, `.env` lookup wording, NULL `classification_method`, stdout for --help/--version, `.env` sentences added to the .qmd sources, SQLite-version caveat and per-sample staging in RELEASE.md). Added OSF regression in auto mode for GTDB-Tk. |
| 2026-11-16 | — | Brief stays at `docs/dev/PANKEGG_update_brief.md`. |

## Notes

- Packaging (step 2): code in `pankegg/` (`make_db.py`, `app.py`, `db_utils.py`, `sql_commands.py`, `data/`,
  `templates/`); root `pankegg_make_db.py` / `pankegg_app.py` are wrappers for checkout use. Version only in
  `pankegg/__init__.py` (pyproject reads it; conda recipe reads it with `load_file_regex`; `codemeta.json`
  checked by `tests/test_version.py`). `setup.py`, `MANIFEST.in`, `lib/` and its committed `__pycache__` removed.
  Light distribution: `python tools/build_makedb.py` → `dist/pankegg_makedb-*.{tar.gz,whl}` (no `app.py`,
  no templates, no `pankegg.db`/`pathway_groups.txt`, no dependencies).
- F1 reproduced before the fix: installed 2.0.0 wheel → `FileNotFoundError: .../site-packages/data/ko.txt`;
  F7: wheel installs a top-level `lib` package.
- Pitfall found: a stale in-tree `build/` directory leaks old files into a wheel built with `pip wheel .`.
  The install test builds from a clean copy; release builds must use `python -m build` from a clean checkout.
- F4/F5 reproduced before the fix (`tests/test_binnames.py::test_pipeline_bin_names_end_to_end`): 2.0.0 created bins
  `SemiBin_12.emapper` and `a.b` with no quality values and no taxonomy.
- F3 reproduced before the fix (`tests/test_eggnog.py`): raw emapper file rejected with
  `missing columns: {'KEGG_Pathway', 'KEGG_ko'}`. Now `read_eggnog_annotations` ignores every `##` line.
- **Open for the owner (not changed, would alter DB content):** a KO whose `KEGG_Pathway` is `-` never reaches the
  `kegg` table, so it has no `bin_extra_kegg` link; the `<bin>_not_mapped` branch only fires on an empty
  `KEGG_Pathway`, which emapper never writes (it writes `-`).
- F2/F6 reproduced before the fix: `sourmash tax genome` file → `No recognizable classification files found.`;
  three-row lca file → only `S1.bin1` classified (others `'null'`); empty lca file → `StopIteration` (and a
  0-bin DB left on disk).
- Determinism reproduced before the fix: same inputs, `PYTHONHASHSEED=1` vs `2` → 210 differing dump lines.
- **Open for the owner (pre-existing in 2.0.0, app out of scope, not changed):** `pankegg_app` runs `app.run(host='0.0.0.0', debug=True)`, which exposes the Werkzeug debugger on all interfaces; `/bin_query` returns 500 (`Row is not JSON serializable`); `/get_heatmap_data_for_taxonomy` 500 with fewer than 2 taxa; `/compar_full` taxonomy PCA 500 when every bin is unclassified.
- F6 note: the committed F6 tests fail on the pre-fix code, but on the missing new columns/option rather than on F6 itself; F6 itself was reproduced by hand (recorded above) and again by the reviewer.
- Python 3.9.25 (via uv): full dependency set resolves (numpy 2.0.2, scipy 1.13.1, flask 3.1.3); tests pass.

- Baseline (step 1): `tests/regression/osf_{sourmash,gtdbtk}_2.0.0.json`, built with the unchanged 2.0.0 code
  (`git diff 2.0.0 HEAD -- pankegg_make_db.py lib data` is empty). Summaries of the rebuilt DBs are byte-identical
  to summaries of the DBs shipped in the OSF archive. Sample3 has 4,738 bin↔map↔KO links, as in the brief.
- Small 2.0.0 DB for app/back-compat tests: `tests/fixtures/db_2.0.0/s1_lca_2.0.0.db` (S1.bin2 has the old text
  `'null'` taxonomic_id). Its eggNOG inputs in `tests/fixtures/s1/` are the first 30 rows of OSF Sample1 bins
  189, 347, 385 in legacy (one `##` line) format.

- `README.md` is rendered from `docs/README.qmd` by `publish_and_render.yml` (master only): edit both.
- No `static/` directory exists in the repo; only `data/` and `templates/` move into the package.
- Baseline test run before any change (Python 3.13.18, pytest 9.1.1): 10 passed with network; 4 passed + 6 skipped without network (OSF download).
