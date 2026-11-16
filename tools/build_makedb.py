#!/usr/bin/env python
"""Build the light "pankegg-makedb" distribution (sdist and wheel).

pankegg-makedb is the pankegg package without the web app: same version, same
pankegg_make_db code and KEGG reference files, no dependencies. It is built
from the sources in this repository so the two distributions never drift.

    python tools/build_makedb.py                 # dist/pankegg_makedb-X.tar.gz + .whl
    python tools/build_makedb.py --wheel-only --outdir /tmp/dist

Uses the setuptools already installed in the running interpreter (no build
isolation, no network).
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "pankegg"
TEMPLATE = Path(__file__).resolve().parent / "makedb"

# Web-app parts of the package that the light distribution leaves out.
APP_ONLY_MODULES = {"app.py", "pages.py", "insights.py"}
APP_ONLY_DATA = {"pankegg.db", "pathway_groups.txt"}


def stage(dest):
    pkg = dest / "pankegg"
    (pkg / "data").mkdir(parents=True)
    for src in sorted(PKG.glob("*.py")):
        if src.name not in APP_ONLY_MODULES:
            shutil.copy2(src, pkg / src.name)
    for src in sorted((PKG / "data").iterdir()):
        if src.is_file() and src.name not in APP_ONLY_DATA:
            shutil.copy2(src, pkg / "data" / src.name)
    shutil.copy2(TEMPLATE / "pyproject.toml", dest / "pyproject.toml")
    shutil.copy2(TEMPLATE / "README.md", dest / "README.md")
    shutil.copy2(REPO / "LICENSE", dest / "LICENSE")


def build(src_dir, outdir, wheel_only):
    targets = ["build_wheel"] if wheel_only else ["build_sdist", "build_wheel"]
    code = (
        # Read the output directory once: setuptools' build_sdist rewrites sys.argv.
        "import sys; from setuptools import build_meta as b\n"
        "out = sys.argv[1]\n"
        f"for t in {targets!r}: print(getattr(b, t)(out))\n"
    )
    subprocess.run([sys.executable, "-c", code, str(outdir)], cwd=src_dir, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--outdir", default=str(REPO / "dist"), help="output directory (default: dist/)")
    parser.add_argument("--wheel-only", action="store_true", help="build only the wheel")
    args = parser.parse_args(argv)
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pankegg-makedb-") as tmp:
        stage(Path(tmp))
        build(Path(tmp), outdir, args.wheel_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
