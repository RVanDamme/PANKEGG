# Input CSV for pankegg_make_db with `sourmash tax genome` classifications,
# results grouped by tool, then sample:  Dir/{eggnog,sourmash,checkm2}/<sample>/
# Edit the directory names and patterns to match your data. Then run:
#   pankegg_make_db -i samples.csv -o my_db --classification sourmash_tax
ANN_GLOB="*.emapper.annotations"        # raw eggNOG-mapper output (or *.annotations.tsv)
CLASS_GLOB="*.classifications.csv"      # sourmash tax genome --output-format csv_summary
CHECKM2_FILE="quality_report.tsv"       # CheckM2 report (a glob such as *_checkm2_report.tsv works too)

echo "Sample name,Annotation_dir,classification_dir,Checkm2_dir" > samples.csv
for sample in Dir/eggnog/*; do
    name=$(basename "$sample");
    ann_path="Dir/eggnog/$name/$ANN_GLOB";
    class_path="Dir/sourmash/$name/$CLASS_GLOB";
    checkm2_path="Dir/checkm2/$name/$CHECKM2_FILE";
    echo "$name,$ann_path,$class_path,$checkm2_path" >> samples.csv;
done
