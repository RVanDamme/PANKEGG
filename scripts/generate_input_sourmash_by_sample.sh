echo "Sample name,Annotation_dir,classification_dir,Checkm2_dir" > samples.csv
for sample in Dir/*; do
    name=$(basename "$sample");
    ann_path="$sample/bin_annotation/*.annotations.tsv";
    class_path="$sample/sourmash/*";
    checkm2_path="$sample/checkm2_dir/quality_report.tsv";
    echo "$name,$ann_path,$class_path,$checkm2_path" >> samples.csv;
done
