"""Compares what the pipeline produces today against a frozen reference, so a
change to the code shows up as an explicit list of differences instead of a
guess.

    python tests/run_regression.py --update   # (re)gèle la référence
    python tests/run_regression.py            # compare, montre les différences
    python tests/run_regression.py --quick    # idem sans la validation XSD (rapide)

The reference is not "the correct output" -- it is "the output as of the moment
you froze it". That is what makes the harness usable on a pipeline that still
has defects: you do not need the output to be right, only to know what moved.

Four files per fixture are compared, because all four are pipeline outputs a
change can silently alter:
  <name>_clean.xml               le XML produit
  <name>_validation_report.txt   conforme au XSD, ou la première erreur
  <name>_unmatched_vocab.csv     les valeurs sans correspondance de vocabulaire
  <name>_quality_report.csv      les réparations faites faute de mieux

A fixture that makes the pipeline crash is recorded as such and compared like
any other: freezing a known failure is what tells you the day it changes.
"""
import argparse
import difflib
import io
import os
import re
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stdout

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

FIXTURES_DIR = os.path.join(BASE_DIR, "tests", "fixtures")
EXPECTED_DIR = os.path.join(BASE_DIR, "tests", "expected")
MAPPING_CSV = os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv")
XSD_SCHEMA = os.path.join(BASE_DIR, "mappings", "fresh-schema_v6.xsd")

CRASH_MARKER = "_CRASH.txt"

# xmlschema reports the offending node as a Python repr -- "<Element 'StudyId'
# at 0x0000018B1AA3AFC0>" -- whose address differs on every run. Left alone, any
# fixture that fails validation would be flagged as changed forever, and the
# harness would cry wolf until nobody reads it any more.
_MEMORY_ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")

# Les fiches source contiennent des retours chariot encodes (&#13;) au milieu du
# texte libre. Selon le systeme, ils ressortent comme une ligne vide ou comme un
# simple saut de ligne : une reference gelee sous Windows affichait 5 ecarts
# fantomes rejouee sous Linux. On ramene toutes les fins de ligne a "\n" avant de
# comparer, pour que le harnais dise la meme chose partout -- sinon il crie au
# loup chez le premier collegue qui le lance.
_FINS_DE_LIGNE = re.compile(r"\r\n?")


def normalise(content):
    content = _FINS_DE_LIGNE.sub("\n", content)
    return _MEMORY_ADDRESS.sub(" at 0xADDR", content)


def produce(fixture_path, out_dir, quick):
    """Runs the pipeline on one fixture into out_dir. Returns the crash text, or
    None when it completed. The pipeline's own stdout is swallowed -- the
    harness reports differences, not progress."""
    from run_pipeline import run_transformation

    name = os.path.splitext(os.path.basename(fixture_path))[0]
    output_xml = os.path.join(out_dir, f"{name}_clean.xml")

    schema_path = XSD_SCHEMA
    if quick:
        # Sans validation : on garde la comparaison du XML, qui est l'essentiel,
        # et on évite de recompiler le XSD 1.1 une fois par fixture.
        schema_path = None

    try:
        with redirect_stdout(io.StringIO()):
            if schema_path is None:
                _produce_without_validation(fixture_path, output_xml, out_dir)
            else:
                run_transformation(
                    input_xml_path=fixture_path,
                    mapping_csv_path=MAPPING_CSV,
                    xsd_schema_path=schema_path,
                    output_xml_path=output_xml,
                    logs_path=out_dir,
                )
        return None
    except Exception:
        return traceback.format_exc()


def _produce_without_validation(fixture_path, output_xml, logs_dir):
    """Le chemin --quick : extraction + construction, sans l'étape XSD."""
    import csv as _csv

    from run_pipeline import HierarchicalExtractor
    from src.builder import FReSHXMLBuilder

    extractor = HierarchicalExtractor(fixture_path, MAPPING_CSV)
    nested = extractor.process()
    builder = FReSHXMLBuilder(lang=extractor.lang)
    root = builder.build_tree(nested)
    os.makedirs(os.path.dirname(output_xml), exist_ok=True)
    builder.save_xml(root, output_xml)

    name = os.path.splitext(os.path.basename(fixture_path))[0]
    with open(os.path.join(logs_dir, f"{name}_unmatched_vocab.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(["field", "raw_value"])
        writer.writerows(extractor.unmatched_vocab + builder.unmatched_vocab)

    with open(os.path.join(logs_dir, f"{name}_quality_report.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(["code", "element", "detail"])
        writer.writerows(builder.corrections)


def run_all(quick):
    """Produces every fixture's output into a temporary folder and returns
    {nom de fichier: contenu}."""
    fixtures = sorted(
        p for p in (os.path.join(FIXTURES_DIR, f) for f in os.listdir(FIXTURES_DIR))
        if p.lower().endswith(".xml")
    )
    if not fixtures:
        sys.exit(f"Aucune fixture dans {FIXTURES_DIR} -- lancez d'abord select_fixtures.py")

    produced = {}
    tmp = tempfile.mkdtemp(prefix="regression_")
    try:
        for fixture in fixtures:
            name = os.path.splitext(os.path.basename(fixture))[0]
            crash = produce(fixture, tmp, quick)
            if crash:
                produced[name + CRASH_MARKER] = normalise(crash)
        for fname in sorted(os.listdir(tmp)):
            with open(os.path.join(tmp, fname), encoding="utf-8-sig") as f:
                produced[fname] = normalise(f.read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return produced, len(fixtures)


def load_expected():
    if not os.path.isdir(EXPECTED_DIR):
        return None
    expected = {}
    for fname in sorted(os.listdir(EXPECTED_DIR)):
        with open(os.path.join(EXPECTED_DIR, fname), encoding="utf-8-sig") as f:
            expected[fname] = f.read()
    return expected


def freeze(produced):
    if os.path.isdir(EXPECTED_DIR):
        shutil.rmtree(EXPECTED_DIR)
    os.makedirs(EXPECTED_DIR)
    for fname, content in produced.items():
        with open(os.path.join(EXPECTED_DIR, fname), "w", encoding="utf-8") as f:
            f.write(content)
    print(f"Référence gelée : {len(produced)} fichiers dans tests/expected/")
    print("Relisez-les une fois -- c'est cette sortie-là qui fait foi désormais.")


def compare(produced, expected):
    added = sorted(set(produced) - set(expected))
    removed = sorted(set(expected) - set(produced))
    changed = sorted(
        name for name in set(produced) & set(expected)
        if produced[name] != expected[name]
    )

    for name in removed:
        print(f"\n  DISPARU  {name}")
        print("      le pipeline ne produit plus ce fichier")
    for name in added:
        print(f"\n  NOUVEAU  {name}")
        if name.endswith(CRASH_MARKER):
            print("      " + produced[name].strip().splitlines()[-1])

    for name in changed:
        print(f"\n  MODIFIÉ  {name}")
        diff = difflib.unified_diff(
            expected[name].splitlines(), produced[name].splitlines(),
            fromfile="référence", tofile="maintenant", lineterm="", n=1,
        )
        lines = list(diff)[2:]
        for line in lines[:30]:
            print(f"      {line}")
        if len(lines) > 30:
            print(f"      ... et {len(lines) - 30} lignes de différence en plus")

    return added, removed, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true", help="(re)gèle la référence sur la sortie actuelle")
    parser.add_argument("--quick", action="store_true", help="saute la validation XSD (beaucoup plus rapide)")
    args = parser.parse_args()

    mode = " (mode rapide, sans validation XSD)" if args.quick else ""
    print(f"Exécution du pipeline sur les fixtures{mode}...")
    produced, n_fixtures = run_all(args.quick)
    print(f"{n_fixtures} fixtures traitées, {len(produced)} fichiers produits.")

    if args.update:
        freeze(produced)
        return 0

    expected = load_expected()
    if expected is None:
        print("\nAucune référence n'existe encore.")
        print("Lancez : python tests/run_regression.py --update")
        return 1

    added, removed, changed = compare(produced, expected)
    total = len(added) + len(removed) + len(changed)

    if total == 0:
        print(f"\nIdentique à la référence ({len(expected)} fichiers). Rien n'a bougé.")
        return 0

    print(f"\n{total} différence(s) : {len(changed)} modifié(s), {len(added)} nouveau(x), {len(removed)} disparu(s).")
    print("Relisez-les une par une. Si elles sont toutes voulues :")
    print("    python tests/run_regression.py --update")
    return 1


if __name__ == "__main__":
    sys.exit(main())
