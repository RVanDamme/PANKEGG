# Helper scripts

Shell loops that write the input CSV of `pankegg_make_db` from a directory of results.
Copy one, edit the directory names and file patterns at the top to match your data, and run it
from the directory that contains `Dir/`:

| Script | Classification input | Layout |
|---|---|---|
| `generate_input_sourmash_tax_by_sample.sh` | `sourmash tax genome` (`*.classifications.csv`) | `Dir/<sample>/{eggnog,sourmash,checkm2}/` |
| `generate_input_sourmash_tax_by_tool.sh` | `sourmash tax genome` | `Dir/{eggnog,sourmash,checkm2}/<sample>/` |
| `generate_input_sourmash_by_sample.sh` | `sourmash lca classify` | `Dir/<sample>/{bin_annotation,sourmash,checkm2_dir}/` |
| `generate_input_sourmash_by_tool.sh` | `sourmash lca classify` | `Dir/{bin_annotation,sourmash,checkm2_dir}/<sample>/` |
| `generate_input_gtdbtk_by_sample.sh` | GTDB-Tk (`*.summary.tsv`) | `Dir/<sample>/{bin_annotation,gtdb_results,checkm2_dir}/` |
| `generate_input_gtdbtk_by_tool.sh` | GTDB-Tk | `Dir/{bin_annotation,gtdb_results,checkm2_dir}/<sample>/` |

Each writes `samples.csv` in the current directory. See the `pankegg_make_db` documentation for
the CSV format and the bin naming rule.
