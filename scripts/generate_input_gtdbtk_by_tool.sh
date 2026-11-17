echo "Sample name,Annotation_dir,classification_dir,Checkm2_dir" > samples.csv
for sample in Dir/bin_annotation/*; do
    name=$(basename "$sample");
    ann_path="Dir/bin_annotation/$name/*.annotations.tsv";
    class_path="Dir/gtdb_results/$name/*.summary.tsv";
    checkm2_path="Dir/checkm2_dir/$name/quality_report.tsv";
    echo "$name,$ann_path,$class_path,$checkm2_path" >> samples.csv;
done
