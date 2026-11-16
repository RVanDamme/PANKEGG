# PANKEGG update — progress

Specification: [`PANKEGG_update_brief.md`](PANKEGG_update_brief.md) (the kickoff prompt calls it `UPDATE_BRIEF.md`; same document).
Branch: `Update_Sourmash` (based on master `c09bf8a` + brief + fixtures).

## Now

- **Step:** 1 — Baseline
- **Next action:** build both OSF example databases with the 2.0.0 code and write the regression summary.

## Steps

- [x] 0. Progress file, CI runs on this branch
- [ ] 1. Baseline from OSF example CSVs (regression reference)
- [ ] 2. Packaging: `pankegg` (full) + `pankegg-makedb` (light), single version, console scripts, `--version`, clean-install test
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

- `README.md` is rendered from `docs/README.qmd` by `publish_and_render.yml` (master only): edit both.
- No `static/` directory exists in the repo; only `data/` and `templates/` move into the package.
- Baseline test run before any change (Python 3.13.18, pytest 9.1.1): 10 passed with network; 4 passed + 6 skipped without network (OSF download).
