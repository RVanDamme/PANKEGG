# PANKEGG update — progress

Specification: [`PANKEGG_update_brief.md`](PANKEGG_update_brief.md) (the kickoff prompt calls it `UPDATE_BRIEF.md`; same document).
Branch: `Update_Sourmash` (based on master `c09bf8a` + brief + fixtures).

## Now

- **Step:** 3 — Bin names
- **Next action:** write failing tests for `S3.439`, `SemiBin_12`, `a.b.c`, `.fa`, `.fa.gz`, `.fna.gz`, then add one normalisation function.

## Steps

- [x] 0. Progress file, CI runs on this branch
- [x] 1. Baseline from OSF example CSVs (regression reference)
- [x] 2. Packaging: `pankegg` (full) + `pankegg-makedb` (light), single version, console scripts, `--version`, clean-install test
- [ ] 3. Bin-name normalisation (brief 3.4)
- [ ] 4. eggNOG reader: raw and legacy files (brief 3.5)
- [ ] 5. Classification modes, tax genome reader, lca all rows, unclassified everywhere, schema additions
- [ ] 6. CLI behaviour: stderr/exit codes, `--quiet`/`--verbose`, deterministic output, English help
- [ ] 7. App check against new and 2.0.0 databases
- [ ] 8. Offline tests, optional OSF test, CI without `|| true`, clean-install job, no committed `__pycache__`
- [ ] 9. Docs, tax genome helper script, CHANGELOG
- [ ] 10. Independent review against brief §7, fixes, acceptance report, release instructions

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
