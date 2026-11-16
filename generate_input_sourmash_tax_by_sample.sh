# Input CSV for pankegg_make_db with `sourmash tax genome` classifications,
# results grouped by sample:  Dir/<sample>/{eggnog,sourmash,checkm2}/
# Edit the directory names and patterns to match your data. Then run:
#   pankegg_make_db -i samples.csv -o my_db --classification sourmash_tax
ANN_GLOB="*.emapper.annotations"        # raw eggNOG-mapper output (or *.annotations.tsv)
CLASS_GLOB="*.classifications.csv"      # sourmash tax genome --output-format csv_summary
CHECKM2_FILE="quality_report.tsv"       # CheckM2 report (a glob such as *_checkm2_report.tsv works too)

echo "Sample name,Annotation_dir,classification_dir,Checkm2_dir" > samples.csv
for sample in Dir/*; do
    name=$(basename "$sample");
    ann_path="$sample/eggnog/$ANN_GLOB";
    class_path="$sample/sourmash/$CLASS_GLOB";
    checkm2_path="$sample/checkm2/$CHECKM2_FILE";
    echo "$name,$ann_path,$class_path,$checkm2_path" >> samples.csv;
done
