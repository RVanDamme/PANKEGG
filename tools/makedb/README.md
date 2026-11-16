# pankegg-makedb

The database builder of [PANKEGG](https://github.com/RVanDamme/PANKEGG), without the web app.

`pankegg-makedb` installs the `pankegg_make_db` command, which builds a PANKEGG SQLite
database from eggNOG-mapper annotations, CheckM2 quality reports and a bin classification
(`sourmash tax genome`, `sourmash lca classify` or GTDB-Tk). It needs only the Python
standard library, which makes it suitable for pipelines and containers.

```bash
pip install pankegg-makedb
pankegg_make_db --help
```

To explore the database in the browser, install the full package instead:

```bash
pip install pankegg       # pankegg_make_db + pankegg_app
```

Install **either** `pankegg` **or** `pankegg-makedb` in one environment, not both: they
provide the same `pankegg` Python package.

Documentation, input formats and examples: <https://github.com/RVanDamme/PANKEGG>.
