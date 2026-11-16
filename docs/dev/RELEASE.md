# Releasing PANKEGG

Two distributions are released from one tag:

| Distribution | Contents | Runtime dependencies | Built with |
|---|---|---|---|
| `pankegg` | `pankegg_make_db` + `pankegg_app` | Flask, pandas, NumPy, scikit-learn, SciPy, Jinja2, click, python-dotenv | `python -m build` |
| `pankegg-makedb` | `pankegg_make_db` only | none (standard library) | `python tools/build_makedb.py` |

The version is set only in `pankegg/__init__.py` (`__version__`). `codemeta.json` must agree
(`tests/test_version.py` checks it). Tags have no `v` prefix (`2.0.0`, `2.1.0`).

## 1. Prepare

```bash
git checkout master && git pull                # after merging Update_Sourmash
grep __version__ pankegg/__init__.py           # 2.1.0
# CHANGELOG.md: replace "unreleased" with the release date
pip install -e ".[dev]" build twine
pytest && pytest --run-osf                     # offline + OSF regression
```

The CI workflow must be green on master (jobs `test` 3.9/3.13, `osf-regression`, `clean-install`, `test-conda`).

## 2. Build from a clean checkout

A stale in-tree `build/` directory can leak old files into a wheel, so build from a fresh clone:

```bash
git clone https://github.com/RVanDamme/PANKEGG.git /tmp/pankegg-release && cd /tmp/pankegg-release
python -m build --outdir dist .                # pankegg-2.1.0.tar.gz, pankegg-2.1.0-py3-none-any.whl
python tools/build_makedb.py --outdir dist     # pankegg_makedb-2.1.0.tar.gz, pankegg_makedb-2.1.0-py3-none-any.whl
twine check dist/*
python -m zipfile -l dist/pankegg_makedb-2.1.0-py3-none-any.whl   # no app.py, no templates, no pankegg.db
```

Optional rehearsal on TestPyPI:

```bash
twine upload --repository testpypi dist/*
python -m venv /tmp/t && /tmp/t/bin/pip install -i https://test.pypi.org/simple/ pankegg-makedb==2.1.0
/tmp/t/bin/pankegg_make_db --version
```

## 3. Tag and GitHub release

```bash
git tag -a 2.1.0 -m "PANKEGG 2.1.0"
git push origin 2.1.0
gh release create 2.1.0 dist/* --title "PANKEGG 2.1.0" --notes-file <(sed -n '/## \[2.1.0\]/,/## \[2.0.0\]/p' CHANGELOG.md | sed '$d')
```

## 4. PyPI

Both project names are free on PyPI (checked 2026-11-16). The first upload creates them; add the
co-maintainer afterwards, or configure a Trusted Publisher for each project.

```bash
twine upload dist/pankegg-2.1.0* dist/pankegg_makedb-2.1.0*
pip install pankegg-makedb==2.1.0 && pankegg_make_db --version    # in a fresh venv
```

## 5. Bioconda

Fork <https://github.com/bioconda/bioconda-recipes>, add the two recipes below as
`recipes/pankegg-makedb/meta.yaml` and `recipes/pankegg/meta.yaml`, fill in the sha256 of each PyPI
sdist, lint, and open one PR.

```bash
curl -sL https://pypi.org/packages/source/p/pankegg-makedb/pankegg_makedb-2.1.0.tar.gz | sha256sum
curl -sL https://pypi.org/packages/source/p/pankegg/pankegg-2.1.0.tar.gz | sha256sum
bioconda-utils lint recipes config.yml --packages pankegg-makedb pankegg
```

`recipes/pankegg-makedb/meta.yaml`:

```yaml
{% set name = "pankegg-makedb" %}
{% set version = "2.1.0" %}

package:
  name: {{ name }}
  version: {{ version }}

source:
  url: https://pypi.org/packages/source/p/{{ name }}/pankegg_makedb-{{ version }}.tar.gz
  sha256: <sha256 of the sdist>

build:
  number: 0
  noarch: python
  script: {{ PYTHON }} -m pip install . --no-deps --no-build-isolation -vv
  entry_points:
    - pankegg_make_db = pankegg.make_db:main
  run_exports:
    - {{ pin_subpackage(name, max_pin="x") }}

requirements:
  host:
    - python >=3.9
    - pip
    - setuptools >=77
    - wheel
  run:
    - python >=3.9

test:
  imports:
    - pankegg.make_db
  commands:
    - pankegg_make_db --version
    - pankegg_make_db --help

about:
  home: https://github.com/RVanDamme/PANKEGG
  dev_url: https://github.com/RVanDamme/PANKEGG
  license: MIT
  license_family: MIT
  license_file: LICENSE
  summary: "PANKEGG database builder: KEGG pathways, taxonomy and quality of MAGs into SQLite (no web app)"

extra:
  recipe-maintainers:
    - RVanDamme
```

`recipes/pankegg/meta.yaml`:

```yaml
{% set name = "pankegg" %}
{% set version = "2.1.0" %}

package:
  name: {{ name }}
  version: {{ version }}

source:
  url: https://pypi.org/packages/source/p/{{ name }}/pankegg-{{ version }}.tar.gz
  sha256: <sha256 of the sdist>

build:
  number: 0
  noarch: python
  script: {{ PYTHON }} -m pip install . --no-deps --no-build-isolation -vv
  entry_points:
    - pankegg_make_db = pankegg.make_db:main
    - pankegg_app = pankegg.app:start_server
  run_exports:
    - {{ pin_subpackage(name, max_pin="x") }}

requirements:
  host:
    - python >=3.9
    - pip
    - setuptools >=77
    - wheel
  run:
    - python >=3.9
    - flask >=2.2
    - jinja2 >=3.0
    - click >=8.0
    - python-dotenv >=0.21
    - pandas >=1.5
    - numpy >=1.23
    - scikit-learn >=1.1
    - scipy >=1.9
  run_constrained:
    - pankegg-makedb <0a0    # same files; never install both in one environment

test:
  imports:
    - pankegg.make_db
    - pankegg.app
  commands:
    - pip check
    - pankegg_make_db --version
    - pankegg_app --help

about:
  home: https://github.com/RVanDamme/PANKEGG
  dev_url: https://github.com/RVanDamme/PANKEGG
  license: MIT
  license_family: MIT
  license_file: LICENSE
  summary: "Build, explore and compare KEGG pathway, taxonomy and quality data of metagenome-assembled genomes"

extra:
  recipe-maintainers:
    - RVanDamme
```

`run_constrained: pankegg-makedb <0a0` makes conda refuse to install both packages in one environment.
Drop it if the Bioconda reviewers prefer otherwise. Bioconda requires `run_exports`; `max_pin="x"`
follows semantic versioning.

Once the PR is merged, BioContainers publishes images automatically (noarch Python builds usually get the
build string `pyhdfd78af_0`; check the actual tag on quay.io):

- Docker: `quay.io/biocontainers/pankegg-makedb:2.1.0--pyhdfd78af_0`
- Singularity: `https://depot.galaxyproject.org/singularity/pankegg-makedb:2.1.0--pyhdfd78af_0`

## 6. For the MUFFIN pipeline (its open decision N12)

- Package: `bioconda::pankegg-makedb=2.1.0` (container as above). The web app is not needed in the pipeline.
- One task for all samples; the task writes `samples.csv` (header
  `Sample name,Annotation_dir,classification_dir,Checkm2_dir`, one row per sample, glob patterns relative
  to the task directory) and runs one of the commands below.
- Stage each sample's files in their own subdirectory (e.g. `stageAs: "${meta.id}/annotations/*"`):
  bin names are only unique within a sample (SemiBin2 writes `SemiBin_<n>` in every sample, so
  `SemiBin_1.emapper.annotations` from two samples would collide in one directory). The CSV row of a sample
  then points to `<sample>/annotations/*.emapper.annotations`, `<sample>/taxonomy/*` and `<sample>/checkm2/*`.

```bash
# --bin_taxonomy sourmash (default): sourmash tax genome --output-format csv_summary, *.classifications.csv
pankegg_make_db -i samples.csv -o pankegg --output_dir . --classification sourmash_tax --quiet

# --bin_taxonomy sourmash_lca: sourmash lca classify CSVs
pankegg_make_db -i samples.csv -o pankegg --output_dir . --classification sourmash_lca --quiet

# --bin_taxonomy gtdbtk: <prefix>.bac120.summary.tsv / <prefix>.ar53.summary.tsv
pankegg_make_db -i samples.csv -o pankegg --output_dir . --classification gtdbtk --quiet
```

- Annotations: raw `*.emapper.annotations`, one per bin. CheckM2: the nf-core `<prefix>_checkm2_report.tsv`
  (a glob is fine).
- Bins without a gather match need no file; they are stored as unclassified (`classification_status = 'absent'`).
- Output: `pankegg.db`. Same inputs give a byte-identical file with the same SQLite library (pinned
  container), so it can be snapshot-tested with nf-test. The SQLite file header records the library version,
  so a different SQLite gives different bytes with identical content; snapshot a content summary (e.g.
  `sqlite3 pankegg.db .dump | md5sum`) if the container is not pinned.
- Exit status 1 on any input problem (message on stderr naming the file); no partial `pankegg.db` is left.
- Version for `versions.yml`: `pankegg_make_db --version` prints `pankegg_make_db 2.1.0`.
