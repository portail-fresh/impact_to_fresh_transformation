"""Normalizes free-text enum values against the ground-truth controlled-vocabulary
CSVs in mappings/vocabularies/, so source-system drift (accents, case, typos)
resolves to the exact term the FReSH schema/vocabulary expects. Bilingual:
each field's CSV carries both a "Terme français" and a "Terme anglais" column,
and resolution is keyed by the record's own language (see fresh-schema_v4.xsd,
which validates each field against the matching language via XSD 1.1
Conditional Type Assignment)."""
import csv
import glob
import os
import re
import unicodedata

VOCAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mappings", "vocabularies")

# Manual overrides for values that don't normalize-match any ground-truth term.
# Keyed by [lang][field name], each maps a normalized raw value to the term
# that should be emitted. After syncing fresh-schema_v3.xsd/_v4.xsd to the
# ground-truth CSVs (see sync_xsd_vocabularies.py / _bilingual.py), most of
# the old hardcoded translations resolve through the CSV lookup directly
# (source values already match the CSV's own wording once accents/case/
# hyphens are normalized). These are genuine wording gaps the CSVs don't
# cover on their own:
VOCAB_ALIASES = {
    "fr": {
        # Source sends the short label; the ground-truth term is the long one.
        "MaskingType": {"insu": "Avec insu (en aveugle)"},
        # Source sends ISO language codes; the ground-truth term is the full word.
        "OriginLang": {"fr": "Français", "en": "Anglais"},
        # Source sends "Etude cas-témoins" (singular study, plural témoins); the
        # ground-truth/XSD term flips both ("Etudes cas-temoin", no accent).
        # Source also sends the short "Cohorte"; ground truth is the longer form.
        "ObservationalStudyDesign": {
            "etudecastemoins": "Etudes cas-temoin",
            "cohorte": "Longitudinale ou cohorte",
        },
    },
    "en": {
        "OriginLang": {"fr": "French", "en": "English"},
        # Source sends the short label "Cohort study"; ground truth is "Longitudinal or cohort".
        "ObservationalStudyDesign": {"cohortstudy": "Longitudinal or cohort"},
    },
}


def _normalize(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    # Drop separators/quote marks entirely (not just collapse) so "MR-001",
    # "MR 001" and "MR001" normalize identically regardless of separator
    # style, and so CSV terms that quote a word for emphasis (e.g. de
    # "convenance") still match a source value that omits the quotes. Colons
    # are included too: several vocab CSVs use "Category : Subcategory" style
    # terms (DataType, HealthDeterminant, SourceType...) and some source
    # records drop the colon in translation (e.g. "Clinical source Clinical
    # record" instead of "Clinical source: Clinical record"). Checked against
    # every vocab CSV for collisions before adding ':' here -- none found.
    s = re.sub(r'[\s\-/\'’"“”:]+', "", s)
    return s


def load_vocabularies():
    vocabularies = {}
    for csv_path in glob.glob(os.path.join(VOCAB_DIR, "*.csv")):
        field_name = os.path.splitext(os.path.basename(csv_path))[0]
        fr_terms, en_terms = {}, {}
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                fr = (row.get("Terme français") or "").strip()
                en = (row.get("Terme anglais") or "").strip()
                if fr:
                    fr_terms[_normalize(fr)] = fr
                if en:
                    en_terms[_normalize(en)] = en
        vocabularies[field_name] = {"fr": fr_terms, "en": en_terms}
    return vocabularies


_VOCABULARIES = load_vocabularies()


def resolve_vocab_term(field_name, raw_value, lang, report=None):
    """Returns the canonical ground-truth term for raw_value under field_name,
    in the given language ("fr" or "en").

    If field_name has no vocab table, raw_value is returned unchanged.
    If no match is found (normalized or alias), raw_value is returned
    unchanged and (field_name, raw_value) is appended to report if given.
    """
    if not raw_value:
        return raw_value

    field_terms = _VOCABULARIES.get(field_name)
    if field_terms is None:
        return raw_value

    normalized = _normalize(raw_value)

    canonical = field_terms.get(lang, {}).get(normalized)
    if canonical is not None:
        return canonical

    alias = VOCAB_ALIASES.get(lang, {}).get(field_name, {}).get(normalized)
    if alias is not None:
        return alias

    if report is not None:
        report.append((field_name, raw_value))
    return raw_value
