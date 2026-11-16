# Web app review — visualisation and summaries (2026-11-16)

Analysis of `pankegg_app` at `f2f6cda`, tested on the OSF example database, and the owner's
decisions. Implementation is tracked in [`PROGRESS.md`](PROGRESS.md) (phase 2).

## What existed

| Page | Shows |
|---|---|
| Home | Static link cards, no data |
| Bin | Bins per sample, taxonomy, completeness/contamination scatter, quality filter |
| Map | Pathways with completion % and KO list; filters by sample, bin, taxon, KO |
| Kegg | KO list with bins, GO terms, eggNOG description |
| Taxonomy | Taxa at one rank with bin counts |
| Sample vs Sample | Per-sample heatmaps (bin × pathway completion), quality scatter, bin PCA, "common pathways" table and bars |
| Bin vs Bin | "Common pathways" table and bars |
| Taxonomy comparison | Stacked bars per sample, pathway × taxon heatmap |
| PCA | Samples by maps, KOs or taxonomy |
| Pathway Stats | Completeness per sample and per bin, KO lists |

## Problems found (verified)

1. **"Both" is a sum, not an overlap.** In the common-pathways tables "Both" = sample 1 + sample 2
   (all 262 rows of the OSF example).
2. **Bin vs Bin mixes samples.** Bins are matched by name only; `metabat_bins.78` exists in two OSF
   samples and is counted twice. SemiBin2 names repeat in every sample.
3. **Sample PCA is uninformative with few samples** (3 samples: two axes always explain 100%). The
   bin PCA uses a fixed 3 clusters and fails with fewer than 3 bins.
4. **Pathway "completeness" is measured against every KO on a KEGG map**, so values are low by
   construction (map00010: 45.8% for the whole database).
5. **Taxonomy bars are % of bins, not abundance**, and the chart does not say so.
6. **The Map page renders everything at once** (4.1 MB of HTML for 3 samples).
7. **Charts need internet**: Plotly from a CDN URL frozen at v1.58.5 (2021).
8. **Unused data**: GO terms, eggNOG descriptions, classification status.
9. Pathway Stats: loose `LIKE` lookup, map ID only, no chart, KO IDs without names, bins without a
   taxonomy row dropped (2.0.0 databases).

## Decisions (owner, 2026-11-16) — all in 2.1.0

| # | Item | Decision |
|---|---|---|
| A1 | Correct "Both", Bin vs Bin by sample, PCA guards, bundle Plotly locally | Yes |
| A2 | Pathway Stats: search by name; KO × bin matrix; completeness distribution per sample; who carries it (by taxon); missing KOs; unclassified bins included **as a toggle**; CSV export | Yes |
| A3 | Overview page replacing the static home | Yes |
| A4 | Bin detail page | Yes |
| A5 | Pathway × taxon matrix (with functional redundancy) | Yes |
| A6 | Core vs accessory pathways and KOs | Yes |
| A7 | Sample similarity heatmap | Yes |
| A8 | Two-group comparison with statistics (Fisher's exact test, multiple-testing correction) | Yes |
| A9 | KEGG module completeness. Keep the existing measure, named **"pathway per-ID completeness"**, and explain the difference wherever either is shown | Yes |
| A10 | Sample metadata: simple TSV `sample<TAB>condition`, free-text conditions, any number of them; colour and group by condition | Yes |
| A11 | Bin abundance | No, not now |
| A12 | Keep KOs that have no pathway | Yes (changes database content: additions only) |

Order: A1 → A2 → A3, A4 → A5–A8 → A9, A10, A12 (`pankegg_make_db`, additive schema).

## The two completeness measures

- **Pathway per-ID completeness** = distinct KOs of a KEGG map found in a bin (or sample) ÷ all KOs
  drawn on that map. A map collects every alternative route and every organism group, so no genome
  reaches 100%; use it to compare bins, not to decide that a pathway is "complete".
- **Module completeness** = mean score of the steps of a KEGG module. A module is a small functional
  unit defined as steps with alternatives (KO *or* KO), complexes (KO *and* KO) and optional parts. A
  step scores its best alternative, and a partly present complex or route counts partly; 100% means
  every required step has one alternative in full.
