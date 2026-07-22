"""Normalizes free-text enum values against the ground-truth controlled-vocabulary
CSVs in mappings/vocabularies/, so source-system drift (accents, case, typos)
resolves to the exact term the FReSH schema/vocabulary expects."""
import csv
import glob
import os
import re
import unicodedata

VOCAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mappings", "vocabularies")

# Manual overrides for values that don't normalize-match any ground-truth term.
# Keyed by field name (the FReSH tag), each maps a normalized raw value to the
# term that should be emitted. After syncing fresh-schema_v3.xsd to the
# ground-truth CSVs (see sync_xsd_vocabularies.py), most of the old hardcoded
# translations resolve through the CSV lookup directly (source values already
# match the CSV's own wording once accents/case/hyphens are normalized). These
# two are genuine wording gaps the CSVs don't cover on their own:
VOCAB_ALIASES = {
    # Source sends the short label; the ground-truth term is the long one.
    "MaskingType": {"insu": "Avec insu (en aveugle)"},
    # Source sends ISO language codes; the ground-truth term is the full word.
    "OriginLang": {"fr": "Français", "en": "Anglais"},
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
    # "convenance") still match a source value that omits the quotes.
    s = re.sub(r'[\s\-/\'’"“”]+', "", s)
    return s


def load_vocabularies():
    vocabularies = {}
    for csv_path in glob.glob(os.path.join(VOCAB_DIR, "*.csv")):
        field_name = os.path.splitext(os.path.basename(csv_path))[0]
        terms = {}
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                term = (row.get("Terme français") or "").strip()
                if term:
                    terms[_normalize(term)] = term
        vocabularies[field_name] = terms
    return vocabularies


_VOCABULARIES = load_vocabularies()


def resolve_vocab_term(field_name, raw_value, report=None):
    """Returns the canonical ground-truth term for raw_value under field_name.

    If field_name has no vocab table, raw_value is returned unchanged.
    If no match is found (normalized or alias), raw_value is returned
    unchanged and (field_name, raw_value) is appended to report if given.
    """
    if not raw_value:
        return raw_value

    terms = _VOCABULARIES.get(field_name)
    if terms is None:
        return raw_value

    normalized = _normalize(raw_value)

    canonical = terms.get(normalized)
    if canonical is not None:
        return canonical

    alias = VOCAB_ALIASES.get(field_name, {}).get(normalized)
    if alias is not None:
        return alias

    if report is not None:
        report.append((field_name, raw_value))
    return raw_value
