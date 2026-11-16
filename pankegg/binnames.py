"""Bin names: one rule for every input (brief §3.4).

A bin is identified by the same name in the eggNOG annotation file name, the
CheckM2 ``Name`` column and the classification ID (sourmash ``ID`` /
``query_name``, GTDB-Tk ``user_genome``). Names are stripped of known
suffixes; dots inside a name are kept (``S3.439``, ``a.b.c``).
"""

import logging
import os

log = logging.getLogger("pankegg")
_warned = set()  # warn once per file name, not once per pass over the file

# Longest first, so ".emapper.annotations" wins over ".annotations".
ANNOTATION_SUFFIXES = (".emapper.annotations", ".annotations.tsv", ".annotations")
FASTA_SUFFIXES = (".fasta", ".fna", ".fa")
COMPRESSION_SUFFIXES = (".gz",)


def _strip_suffix(text, suffixes):
    lower = text.lower()
    for suffix in suffixes:
        if lower.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)], True
    return text, False


def normalise_bin_name(name):
    """Bin identifier without a FASTA extension: ``S1.bin1.fa.gz`` -> ``S1.bin1``.

    Strips one of ``.fa``, ``.fna``, ``.fasta``, each optionally followed by
    ``.gz`` (case-insensitive), and surrounding whitespace.
    """
    name = name.strip()
    stem, compressed = _strip_suffix(name, COMPRESSION_SUFFIXES)
    stem, had_fasta = _strip_suffix(stem, FASTA_SUFFIXES)
    if had_fasta:
        return stem
    return name  # a lone ".gz" without a FASTA extension is not ours to remove


def bin_name_from_annotation_file(path):
    """Bin name from an eggNOG-mapper annotation file name.

    ``S3.439.emapper.annotations`` -> ``S3.439``;
    ``metabat_bins.189.annotations.tsv`` -> ``metabat_bins.189``;
    ``SemiBin_12.fa.emapper.annotations`` -> ``SemiBin_12``.

    File names without a known annotation suffix keep the PANKEGG 2.0.0 rule
    (first two dot-separated parts) so existing databases do not change, with
    a warning.
    """
    base = os.path.basename(path)
    stem, matched = _strip_suffix(base, ANNOTATION_SUFFIXES)
    if matched:
        return normalise_bin_name(stem)
    parts = base.split(".")
    legacy = ".".join(parts[:2]) if len(parts) >= 2 else base
    if base not in _warned:
        _warned.add(base)
        log.warning(
            f"Annotation file {base!r} has no known suffix ({', '.join(ANNOTATION_SUFFIXES)}); "
            f"using the PANKEGG 2.0.0 naming rule: bin name {normalise_bin_name(legacy)!r}")
    return normalise_bin_name(legacy)
