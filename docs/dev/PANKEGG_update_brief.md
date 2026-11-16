# PANKEGG update brief — standalone tool and MUFFIN pipeline component

Prepared 2026-11-16 from PANKEGG `master` at `3c6e652` (tag `2.0.0` = `0ef3aee`), sourmash 4.9.4, and the MUFFIN nf-core rebuild plan (`RVanDamme/MUFFIN`, branch `Upgrade`, `docs/migration/REPORT_ADDENDUM.md` §4 and §4a).

Scope: `pankegg_make_db` (database generation). The web app only needs to keep working with whatever the database becomes.

Each finding says how it was established: **run** = executed here, **read** = read from source only.

---

## 1. What must be true at the end

1. `pip install pankegg` (or the conda package) gives a working `pankegg_make_db` from any directory, with no repository checkout.
2. `pankegg_make_db` accepts three bin-classification inputs: `sourmash tax genome` (new), `sourmash lca classify` (existing), GTDB-Tk summaries (existing).
3. It accepts eggNOG-mapper output exactly as emapper writes it, and bin names as the MUFFIN modules produce them.
4. Existing users' commands, input CSVs and files keep working, and `pankegg_app` opens databases built by the new version.
5. A tagged release exists that the pipeline can pin in a container.

## 2. Findings on PANKEGG 2.0.0

### Blocking for the pipeline

| # | Finding | Evidence |
|---|---|---|
| F1 | **A normal `pip install .` produces a broken CLI.** `data/` (ko.txt, kegg_map_orthologs.tsv, pankegg.db …), `templates/` and `static/` are not installed; site-packages receives only `lib/`, `pankegg_app.py`, `pankegg_make_db.py`. `default_ko_file` resolves to `site-packages/data/ko.txt`, which does not exist. It works today only from a checkout or `pip install -e .` (which is what CI uses). Cause: `data/` is not inside a Python package, so `include_package_data` and `MANIFEST.in` do not apply to it. | run |
| F2 | **`sourmash tax genome` output is rejected**: `No recognizable classification files found.` `detect_file_type` knows only `ID,status` (lca) and `user_genome,classification` (GTDB-Tk). | run |
| F3 | **Raw eggNOG-mapper output is rejected**: `missing columns: {'KEGG_Pathway', 'KEGG_ko'}`. emapper writes several `##` lines before the `#query` header and three `##` lines after the data; PANKEGG skips only one leading `##` line. The example data works because legacy MUFFIN stripped the files first. | run |
| F4 | **Bin name = first two dot-separated parts of the annotation file name**, then a trailing `.fa` is removed (`sample_preliminary_process`, `process_annotation_file`, `process_gtdbtk_taxonomy_files`). `S3.439.emapper.annotations` → `S3.439` works (run). `SemiBin_12.emapper.annotations` → `SemiBin_12.emapper`, and any bin name with zero or two-plus dots, breaks (read). | run / read |
| F5 | Only `.fa` is stripped from classification IDs. nf-core binners emit `.fa.gz`; `.fna`, `.fasta` and their `.gz` forms are not handled. | read |
| F6 | Sourmash mode reads **exactly one data line per file** (`next(file)` twice). A file with several bins loses all but the first; an empty or header-only file raises `StopIteration`. | read |

### Packaging and hygiene

| # | Finding | Evidence |
|---|---|---|
| F7 | The installed top-level package is called `lib`, which collides with anything else named `lib`. | run |
| F8 | `install_requires` includes `pytest` and the whole web stack (flask, pandas, numpy, scikit-learn, scipy). `pankegg_make_db` itself imports only the standard library. | read |
| F9 | Version disagreement: `setup.py` 2.0.0, `conda.recipe/meta.yaml` 1.0. `pyproject.toml` has only a build-system table. No `--version` flag. | read |
| F10 | Not on PyPI or Bioconda as far as the README shows, so there is no ready container. *(confirm)* | read |
| F11 | Tests download the OSF archive at run time (`tests/conftest.py`), so they need network. `__pycache__/*.pyc` files are committed. CI runs the CLI help with `\|\| true`, which hides failures. Help epilog is in French. | read |
| F12 | Output is noisy (`[DEBUG]` and `Skipping row` lines on stdout), with no quiet/verbose switch. | run |

### What already works

- lca mode with pipeline-style names (`S3.439.emapper.annotations`, CheckM2 `Name` = `S3.439`, lca `ID` = `S3.439`) builds a correct DB: three bins with completeness, genus and 4,738 KEGG links. **run**
- CheckM2: needs `Name`, `Completeness`, `Contamination`; the nf-core `<prefix>_checkm2_report.tsv` is a plain copy of `quality_report.tsv`. **read**
- `sourmash lca classify` still exists and works in sourmash 4.9.4. **run**
- No network access during DB creation. **read**

## 3. Formats to support (real files are in `pankegg_fixtures.zip`)

### 3.1 `sourmash tax genome --output-format csv_summary` (new, pipeline default)

File `<base>.classifications.csv`, comma-separated, produced with sourmash 4.9.4:

```
query_name,status,rank,fraction,lineage,query_md5,query_filename,f_weighted_at_rank,bp_match_at_rank,query_ani_at_rank
S1.bin1,match,species,1.0,d__Bacteria;p__Pseudomonadota;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli,4830a32a,S1.bin1.fa.gz,1.0,180000,1.0
S1.bin3,below_threshold,superkingdom,0.0534,d__Bacteria,4e3fcfcd,S1.bin3.fa,0.0534,23000,0.9098
```

Rules to implement:
- Detect by header containing `query_name`, `status`, `lineage`.
- Bin name = `query_name` (normalised as in §3.4). Do not use `query_filename`.
- `lineage` is `;`-separated with GTDB prefixes and **may stop early** (the second row has only the domain). Pad missing ranks with NULL, as the GTDB-Tk reader already does.
- `status` values: `match`, `below_threshold`, `nomatch`. Decide how `below_threshold` is stored (§6, P3).
- A file may contain **one or many** rows (one per bin). Read all rows.
- **A bin with no gather match has no row and possibly no file at all**: `sourmash gather` writes no CSV when nothing matches (run), so `tax genome` never sees that bin. Every bin known from the annotations but absent from the classification files must end up as unclassified, as GTDB-Tk mode already does.

### 3.2 `sourmash lca classify` (existing, legacy option)

```
ID,status,superkingdom,phylum,class,order,family,genus,species,strain
S1.bin1,found,d__Bacteria,p__Pseudomonadota,…,s__Escherichia coli,
S1.bin2,nomatch,,,,,,,,
```

Keep working; read all rows; tolerate empty files.

### 3.3 GTDB-Tk (existing, high-accuracy option)

`gtdbtk.bac120.summary.tsv` and `gtdbtk.ar53.summary.tsv`, columns `user_genome`, `classification`. From the nf-core module the files are `<prefix>/classify/<prefix>.bac120.summary.tsv`. `user_genome` is the bin file name without the extension given to GTDB-Tk.

### 3.4 Bin names

The same bin must resolve to the same name in all three inputs (annotation file name, CheckM2 `Name`, classification ID). Replace the "first two dot parts" rule with suffix stripping:

- from annotation file names: `.emapper.annotations`, `.annotations.tsv`, `.annotations`
- from any bin identifier: `.fa`, `.fna`, `.fasta`, each optionally followed by `.gz`

Names the pipeline will produce: MetaBAT2 `<sample>.<n>`, COMEBin `<sample>.<bin>`, SemiBin2 `SemiBin_<n>` (exact strings to be confirmed in the pipeline's Stage 2; the stripping rule covers them all). Bin names are only unique within a sample, which the schema already handles via `sample_id`.

### 3.5 eggNOG-mapper annotations

Accept both the raw file (several leading `##` lines, header line starting `#query`, trailing `##` lines) and the legacy stripped file (one `##` line, then the header). Rule: ignore every line starting with `##`; the header is the line starting with `#query`.

## 4. Proposed command-line interface

```
pankegg_make_db -i samples.csv -o NAME --output_dir DIR
                [--classification auto|sourmash_tax|sourmash_lca|gtdbtk]
                [--gtdbtk]            # kept as an alias of --classification gtdbtk
                [--quiet | --verbose] [--version]
```

- Default `auto`: detect per file from the header; mixed types within one sample are an error.
- An explicit value that contradicts the files is an error naming the file.
- Input CSV unchanged: `Sample name,Annotation_dir,classification_dir,Checkm2_dir` with glob patterns. Relative paths must work (the pipeline writes this CSV inside the task directory).
- Non-zero exit code on every error; errors on stderr.
- Same inputs → same database content, independent of glob order (sort the file lists), so the pipeline can snapshot-test it.

How MUFFIN will call it (one task for all samples):

| Pipeline `--bin_taxonomy` | Files handed over per sample | Call |
|---|---|---|
| `sourmash` (default) | one `*.classifications.csv` per classified bin | `--classification sourmash_tax` |
| `sourmash_lca` | one lca CSV per bin | `--classification sourmash_lca` |
| `gtdbtk` | `*.summary.tsv` | `--classification gtdbtk` |

plus raw `*.emapper.annotations` (one per bin) and one CheckM2 report per sample.

## 5. Packaging target

- A real package directory (for example `pankegg/` containing `make_db.py`, `app.py`, `db_utils.py`, `sql_commands.py`, `data/`, `templates/`, `static/`), resources loaded with `importlib.resources`. Thin top-level `pankegg_make_db.py` / `pankegg_app.py` shims may stay so `python pankegg_make_db.py …` from a checkout keeps working.
- All metadata in `pyproject.toml`; one version source; console scripts `pankegg_make_db` and `pankegg_app`.
- Dependencies split: base install needs only what `make_db` needs (standard library); web stack under an extra such as `pankegg[app]`; pytest under `[dev]`. Decide whether the plain install should still pull the app (§6, P2).
- Test that would have caught F1: build the wheel, install it into a clean environment, change to an empty directory, run `pankegg_make_db` on fixtures.
- Release: tag (2.1.0 or 3.0.0, §6 P1) → PyPI → Bioconda recipe. A Bioconda package gives a BioContainers image automatically, so the pipeline module can pin it like any nf-core module instead of maintaining a custom image.
- Offline tests with small fixtures committed to the repo; keep the OSF download as an optional, marked test.

## 6. Decisions for you

| # | Question | Suggested default |
|---|---|---|
| P1 | Version number. The CLI stays compatible, but the import path changes if `lib` is renamed. | 2.1.0 if old top-level scripts keep working; 3.0.0 otherwise |
| P2 | Should a plain `pip install pankegg` include the web app dependencies? | No: base = `make_db`, `pankegg[app]` = web app. Simplest for the pipeline container; needs a line in the README |
| P3 | `below_threshold` rows from `tax genome`: store the (partial) lineage, or treat as unclassified? | Store the lineage and record the status, so the app can show low-confidence calls differently later |
| P4 | Record the classification method and status in the DB (new column or small metadata table)? This changes the schema, so the app must tolerate old and new DBs. | Yes, additive only (new nullable columns / new table), with a test that the app opens a 2.0.0 database |
| P5 | Publish to PyPI and Bioconda now, or only tag on GitHub? | Both; Bioconda removes the custom container from the pipeline |
| P6 | Keep the `generate_input_*_by_*.sh` helper scripts in sync with a `tax genome` variant? | Yes, one extra script or an option |

## 7. Acceptance criteria

1. Clean-environment install test passes (wheel → install → run from an empty directory).
2. `pankegg_make_db` builds a DB from each of: tax genome fixtures, lca fixtures, GTDB-Tk example data; `auto` picks the right reader for each.
3. Tax genome cases covered by tests: `match`, `below_threshold` with truncated lineage, a bin with no row/file, several bins in one file.
4. Raw eggNOG file and legacy stripped file give identical DB content.
5. Bin-name tests: `S3.439`, `SemiBin_12`, `a.b.c`, inputs with `.fa`, `.fa.gz`, `.fna.gz`.
6. Regression: the published OSF example CSVs (`sourmash_example.csv`, `gtdbtk_example.csv`) still build, and the result matches 2.0.0 for bins, taxonomy and KEGG links.
7. `pankegg_app` starts and serves the main pages against a DB from the new version and against a 2.0.0 DB.
8. Tests run offline; CI no longer masks CLI failures.
9. README/docs updated: three classification inputs, the new option, install extras, bin-naming rule.
10. Release tagged; the tag, the exact CLI call for each method and the package/container reference are written down for the MUFFIN pipeline (its open decision N12).

## 8. Fixtures (`pankegg_fixtures.zip`)

| Path | What it is |
|---|---|
| `sourmash_tax_genome/S1.bin1.classifications.csv` | real sourmash 4.9.4 output, `match` at species |
| `sourmash_tax_genome/S1.bin3.classifications.csv` | real output, `below_threshold`, lineage truncated at domain |
| `sourmash_tax_genome/S1.all.classifications.csv` | real output, two bins in one file |
| `sourmash_tax_genome/S1.bin1.gather.csv`, `lineages.csv` | the gather result and lineage table they came from |
| `sourmash_lca/S1.bin{1,2,3}.lca.csv` | real `lca classify` output: `found`, `nomatch`, `found` |
| `raw_eggnog_header/S3.439.emapper.annotations` | first rows of the OSF example annotation wrapped in an emapper-style `##` header and footer |

The genomes behind the sourmash files are random synthetic sequences with made-up accessions and real-looking GTDB lineages; they are valid for parser tests, not for biology. The eggNOG header/footer lines were written by hand to mimic emapper 2.1.13; replace this fixture with a real raw file from the pipeline when one exists. There is deliberately no file for `S1.bin2` under `sourmash_tax_genome/`: it had no gather match, which is the "missing bin" case.

---

## 9. Kickoff prompt (paste into Claude Code at the root of the PANKEGG repository)

Put this brief in the repo first (suggested: `docs/dev/UPDATE_BRIEF.md`) and unzip the fixtures to `tests/fixtures/`.

```
You are updating PANKEGG so that pankegg_make_db works both as an installed
standalone tool and as a step of the MUFFIN nf-core pipeline.
docs/dev/UPDATE_BRIEF.md is the specification: read it completely first.
The web app (pankegg_app) is out of scope except that it must keep working.

Rules
- Work on a new branch named pipeline-ready. Small conventional commits; push
  after every completed step so an interrupted session loses nothing.
- Keep docs/dev/PROGRESS.md up to date: a "Now" block (step, next action),
  a checklist of the steps below, and decisions with dates. Update and commit
  it at every step. On "resume": read it, check git status and git log, say
  where things stand in three lines, continue from the first open step.
- Reproduce each finding F1-F6 with a failing test before fixing it. Never
  claim something passes without showing the command and its output.
- Backward compatibility is a requirement: the existing CLI, the existing
  input CSV and the published OSF example data must keep working. Any change
  to the database schema must be additive, and the app must open old DBs.
- No new runtime dependency for pankegg_make_db beyond the standard library.
- Stop and ask instead of guessing when a decision in section 6 of the brief
  is needed, or when a fix would change existing database content.

Before changing anything
1. Read the brief, pankegg_make_db.py, lib/db_utils.py, lib/sql_commands.py,
   setup.py, pyproject.toml, MANIFEST.in, tests/, .github/workflows/.
2. Print python and pytest versions and run the current test suite; report
   what passes and whether it needed network.
3. Ask me decisions P1-P6 in one message, each with your recommendation.
4. Print the plan with the files each step will touch. Wait for my "go".

Steps (one at a time, tests first, commit and push after each)
1. Baseline: build databases from the OSF example CSVs with the current code
   and save a summary (bins, taxonomy, KEGG link counts per sample) as the
   regression reference.
2. Packaging: real package with data, templates and static inside it;
   pyproject metadata; single version; console scripts; dependency extras per
   P2; --version. Add the clean-install test (build wheel, install in a fresh
   venv, run from an empty directory).
3. Bin names: one normalisation function used everywhere (brief 3.4).
4. eggNOG reader: raw and legacy files (brief 3.5).
5. Classification: --classification auto|sourmash_tax|sourmash_lca|gtdbtk,
   --gtdbtk kept as alias; new tax genome reader (brief 3.1); lca reader reads
   all rows and tolerates empty files; bins without a classification become
   unclassified in every mode; schema additions per P3/P4.
6. CLI behaviour: errors to stderr with non-zero exit, --quiet/--verbose,
   deterministic output, English help text.
7. App check: start pankegg_app against a new DB and a 2.0.0 DB and request
   the main pages; fix only what the schema change broke.
8. Tests offline with the fixtures in tests/fixtures; OSF download test
   marked optional. CI: remove "|| true", add the clean-install job. Remove
   committed __pycache__ and ignore it.
9. Docs: README and docs for the three inputs, install extras, bin naming;
   helper script for tax genome input per P6; CHANGELOG.
10. Review your own diff against section 7 of the brief with a fresh
    subagent if available (otherwise as a separate pass), fix what it finds,
    then report against every acceptance criterion with evidence. Do not tag
    or publish; give me the exact release, PyPI and Bioconda steps and the
    three pankegg_make_db command lines the MUFFIN pipeline should use.
```
