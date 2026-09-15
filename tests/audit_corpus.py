"""Audits the whole corpus in one pass and prints what nobody currently knows:
which source fields are really populated, where the source contradicts itself,
which controlled-vocabulary values never resolve, and which mapping rows never
match anything.

    python tests/audit_corpus.py --data-dir data\\input              # sections 1-5, rapide
    python tests/audit_corpus.py --data-dir data\\input --full       # + vocabulaires (lent)
    python tests/audit_corpus.py --data-dir data\\input --full --validate   # + conformite XSD

Written because a headline number from the fixture-selection script -- only 2
interventional files out of 2154 -- was implausible for a health research
catalogue, and guessing at the cause is worth less than measuring it.
"""
import argparse
import collections
import csv
import glob
import io
import os
import sys
import time
from contextlib import redirect_stdout

import xml.etree.ElementTree as stdET

from lxml import etree  # type: ignore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MAPPING_CSV = os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv")
XSD_SCHEMA = os.path.join(BASE_DIR, "mappings", "fresh-schema_v6.xsd")

# Signaux indépendants du caractère interventionnel d'une étude. researchType
# est celui sur lequel builder.py (étape 10.7) tranche pour SUPPRIMER l'autre
# branche de StudyMethodology ; les autres sont des données qui n'ont de sens
# que pour une étude interventionnelle. Si researchType dit "observationnelle"
# alors que ceux-ci sont remplis, la source se contredit et le pipeline jette
# silencieusement les secondes.
INTERVENTIONAL_SIGNALS = {
    "isClinicalTrial": "/xml/dataset/metadata/additional/interventionalStudy/isClinicalTrial",
    "trialPhase": "/xml/dataset/metadata/additional/interventionalStudy/trialPhase/trialphase",
    "researchPurpose": "/xml/dataset/metadata/additional/interventionalStudy/researchPurpose/researchpurpose",
    "studyModel": "/xml/dataset/metadata/additional/interventionalStudy/interventionalStudyModel",
    "arms": "/xml/dataset/metadata/additional/arms/arm",
    "allocation": "/xml/dataset/metadata/additional/allocation",
    "masking": "/xml/dataset/metadata/additional/masking",
}

RESEARCH_TYPE = "/xml/dataset/metadata/additional/researchType/values"


def texts(tree, xpath):
    out = []
    try:
        nodes = tree.xpath(xpath)
    except Exception:
        return out
    for node in nodes:
        text = node if isinstance(node, str) else (node.text or "")
        text = " ".join(text.split())
        if text:
            out.append(text)
    return out


def title(text):
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


# --------------------------------------------------------------------------
# 1. researchType : ce que la source dit vraiment
# --------------------------------------------------------------------------
def section_research_type(trees):
    title("1. researchType -- les valeurs reellement presentes")
    counter = collections.Counter()
    empty = 0
    for _, tree in trees:
        values = texts(tree, RESEARCH_TYPE)
        if not values:
            empty += 1
        for value in values:
            counter[value] += 1

    print(f"vide dans {empty} / {len(trees)} fichiers")
    for value, count in counter.most_common(20):
        print(f"  {count:6}  {value[:80]}")
    if len(counter) > 20:
        print(f"  ... {len(counter) - 20} autre(s) valeur(s) distincte(s)")


# --------------------------------------------------------------------------
# 2. La source se contredit-elle ?
# --------------------------------------------------------------------------
def section_contradiction(trees):
    title("2. Donnees interventionnelles presentes malgre un researchType observationnel")
    print("Ce que builder.py fait (etape 10.7) : si researchType dit observationnel,")
    print("la branche InterventionalStudy est SUPPRIMEE. Toute donnee ci-dessous")
    print("comptee comme 'jetee' disparait donc du XML produit.\n")

    per_signal = collections.Counter()
    contradicted = set()
    signal_totals = collections.Counter()

    for name, tree in trees:
        research = " ".join(texts(tree, RESEARCH_TYPE)).lower()
        says_observational = "observation" in research
        for label, xpath in INTERVENTIONAL_SIGNALS.items():
            present = bool(tree.xpath(xpath)) if label in ("arms",) else bool(texts(tree, xpath))
            if not present:
                continue
            signal_totals[label] += 1
            if says_observational:
                per_signal[label] += 1
                contradicted.add(name)

    print(f"{'signal':<22} {'rempli':>8} {'dont jete':>11}")
    for label in INTERVENTIONAL_SIGNALS:
        total = signal_totals[label]
        lost = per_signal[label]
        flag = "  <-- !!" if lost else ""
        print(f"{label:<22} {total:>8} {lost:>11}{flag}")

    print(f"\nFichiers concernes par au moins une contradiction : {len(contradicted)} / {len(trees)}")
    for name in sorted(contradicted)[:10]:
        print(f"    {name}")
    if len(contradicted) > 10:
        print(f"    ... et {len(contradicted) - 10} autres")


# --------------------------------------------------------------------------
# 3. Listes paralleles appariees par position
# --------------------------------------------------------------------------
PAIRED_LISTS = {
    "financeur / type": (
        "/xml/dataset/metadata/study_desc/production_statement/funding_agencies/funding_agency",
        "/xml/dataset/metadata/additional/fundingAgent/fundingAgentType/fundingagenttype",
    ),
    "sponsor / type": (
        "/xml/dataset/metadata/study_desc/production_statement/producers/producer",
        "/xml/dataset/metadata/additional/sponsor/sponsorType/sponsortype",
    ),
    "agence / precision": (
        "/xml/dataset/metadata/study_desc/study_authorization/agency/item/name",
        "/xml/dataset/metadata/additional/obtainedAuthorization/otherAuthorizingAgency/otherauthorizingagency",
    ),
}


def section_paired_lists(trees):
    title("3. Listes paralleles appariees PAR POSITION")
    print("builder.py attache type[i] a element[i]. Si les longueurs different,")
    print("le surplus est perdu -- et un decalage en amont decale tout le reste.\n")

    for label, (left_xpath, right_xpath) in PAIRED_LISTS.items():
        shapes = collections.Counter()
        for _, tree in trees:
            left = len(tree.xpath(left_xpath))
            # Compter les ÉLÉMENTS, pas les valeurs non vides : la source émet un
            # emplacement par élément de la liste sœur, vide compris, et c'est ce
            # vide qui tient la position. Compter les valeurs non vides faisait
            # passer un appariement correct pour un décalage (vérifié sur
            # FRESH-PEF2582 : 3 agences, 3 emplacements dont 2 vides, la
            # précision "Inserm" tombe bien en face de l'agence "Autre").
            right = len(tree.xpath(right_xpath))
            if left or right:
                shapes[(left, right)] += 1

        aligned = sum(c for (a, b), c in shapes.items() if a == b)
        missing = sum(c for (a, b), c in shapes.items() if b == 0 and a > 0)
        mismatch = sum(c for (a, b), c in shapes.items() if b > 0 and a != b)

        print(f"--- {label} ---")
        print(f"  alignes                        : {aligned}")
        print(f"  aucun type (benin, champ vide) : {missing}")
        print(f"  longueurs differentes, non nul : {mismatch}   <-- le cas a risque")
        for (a, b), count in shapes.most_common(8):
            mark = "  <-- risque" if b > 0 and a != b else ""
            print(f"      {count:6}  {a} element(s) / {b} type(s){mark}")
        print()


# --------------------------------------------------------------------------
# 4. Lignes de mapping qui ne matchent jamais rien
# --------------------------------------------------------------------------
def section_dead_mapping(trees):
    title("4. Lignes de la table de mapping qui ne ramenent JAMAIS rien")
    rows = list(csv.DictReader(open(MAPPING_CSV, encoding="utf-8")))

    checks = []  # (target, xpath_absolu)
    current_root = None
    for row in rows:
        source = (row.get("source_xpath") or "").strip()
        target = (row.get("target_xpath") or "").strip()
        if not source or not target:
            continue
        if source.startswith("ROOT:"):
            current_root = source.split("ROOT:", 1)[1]
            checks.append((target, current_root))
        elif source.startswith("ARRAY:"):
            relative = source.split("ARRAY:", 1)[1].lstrip("./")
            if current_root:
                checks.append((target, f"{current_root}/{relative}"))
        elif source.startswith("./"):
            if current_root:
                checks.append((target, f"{current_root}/{source[2:]}"))
        elif source.startswith("/xml/"):
            checks.append((target, source))

    never, rare = [], []
    for target, xpath in checks:
        hits = 0
        for _, tree in trees:
            try:
                if tree.xpath(xpath):
                    hits += 1
            except Exception:
                hits = -1
                break
        if hits == 0:
            never.append(target)
        elif 0 < hits <= max(1, len(trees) // 100):
            rare.append((target, hits))

    print(f"{len(checks)} regles evaluees sur {len(trees)} fichiers\n")
    print(f"--- JAMAIS remplies ({len(never)}) : mapping mort, ou chemin source faux ---")
    for target in never:
        print(f"    {target}")
    print(f"\n--- remplies dans moins de 1% des fichiers ({len(rare)}) ---")
    for target, hits in sorted(rare, key=lambda x: x[1]):
        print(f"    {hits:5}  {target}")


# --------------------------------------------------------------------------
# 5. Asymetrie fr / en
# --------------------------------------------------------------------------
def section_bilingual(trees):
    title("5. Asymetries entre les versions fr et en d'une meme etude")
    by_study = collections.defaultdict(dict)
    for name, tree in trees:
        lower = name.lower()
        if lower.endswith("-fr.xml"):
            by_study[name[:-7]]["fr"] = tree
        elif lower.endswith("-en.xml"):
            by_study[name[:-7]]["en"] = tree

    pairs = {k: v for k, v in by_study.items() if len(v) == 2}
    print(f"{len(pairs)} etudes presentes dans les deux langues\n")

    probes = {
        "nb financeurs": "/xml/dataset/metadata/study_desc/production_statement/funding_agencies/funding_agency",
        "nb agences": "/xml/dataset/metadata/study_desc/study_authorization/agency/item/name",
        "nb mots-cles": "/xml/dataset/metadata/study_desc/study_info/keywords/keyword/keyword",
        "nb sources tierces": "/xml/dataset/metadata/study_desc/method/data_collection/sources/source",
        "nb bras": "/xml/dataset/metadata/additional/arms/arm",
    }
    for label, xpath in probes.items():
        differing = [
            study for study, langs in pairs.items()
            if len(langs["fr"].xpath(xpath)) != len(langs["en"].xpath(xpath))
        ]
        print(f"  {label:<22} differe dans {len(differing):5} / {len(pairs)} etudes")
        for study in sorted(differing)[:3]:
            fr = len(pairs[study]["fr"].xpath(xpath))
            en = len(pairs[study]["en"].xpath(xpath))
            print(f"        {study}  fr={fr} en={en}")


# --------------------------------------------------------------------------
# 6. Vocabulaires non resolus (passe complete, lente)
# --------------------------------------------------------------------------
def section_vocabularies(paths, validate):
    title("6. Valeurs de vocabulaire controle NON resolues")
    print("Une valeur non resolue sort sans URI. Sans URI, elle n'est pas")
    print("mappable vers HealthDCAT-AP : c'est le backlog de curation.\n")

    from run_pipeline import HierarchicalExtractor
    from src.builder import FReSHXMLBuilder

    schema = None
    if validate:
        import xmlschema
        print("Compilation du XSD (une seule fois pour tout le corpus)...")
        started = time.time()
        schema = xmlschema.XMLSchema11(XSD_SCHEMA)
        print(f"  fait en {time.time() - started:.1f}s\n")

    per_field = collections.Counter()
    examples = collections.defaultdict(collections.Counter)
    crashed, valid, invalid = [], 0, 0
    validation_errors = []
    started = time.time()

    for index, path in enumerate(paths, 1):
        if index % 250 == 0:
            print(f"  {index} / {len(paths)}  ({time.time() - started:.0f}s)")
        try:
            with redirect_stdout(io.StringIO()):
                extractor = HierarchicalExtractor(path, MAPPING_CSV)
                data = extractor.process()
                builder = FReSHXMLBuilder(lang=extractor.lang)
                root = builder.build_tree(data)
            for field, raw in extractor.unmatched_vocab + builder.unmatched_vocab:
                per_field[field] += 1
                examples[field][raw] += 1
        except Exception as exc:
            crashed.append((os.path.basename(path), str(exc)[:120]))
            continue

        if schema is not None:
            # builder.py construit avec xml.etree (bibliothèque standard), pas
            # avec lxml : sérialiser via lxml lève "cannot be serialized".
            try:
                payload = stdET.tostring(root, encoding="unicode")
                if schema.is_valid(io.StringIO(payload)):
                    valid += 1
                else:
                    invalid += 1
            except Exception as exc:
                invalid += 1
                if len(validation_errors) < 5:
                    validation_errors.append((os.path.basename(path), str(exc)[:120]))

    print(f"\n{len(paths) - len(crashed)} fichiers traites, {len(crashed)} plantages")
    for name, message in crashed[:10]:
        print(f"    {name} : {message}")

    if schema is not None:
        total = valid + invalid
        rate = 100 * valid / total if total else 0
        print(f"\n--- CONFORMITE XSD : {valid} valides / {total}  ({rate:.1f}%) ---")
        for name, message in validation_errors:
            print(f"    erreur inattendue sur {name} : {message}")

    print(f"\n--- Champs avec des valeurs non resolues ({len(per_field)}) ---")
    for field, count in per_field.most_common():
        print(f"\n  {field}  ({count} occurrences)")
        for raw, n in examples[field].most_common(5):
            print(f"      {n:5}  {raw[:70]!r}")
        if len(examples[field]) > 5:
            print(f"      ... {len(examples[field]) - 5} autre(s) valeur(s) distincte(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--full", action="store_true", help="ajoute l'analyse des vocabulaires (plusieurs minutes)")
    parser.add_argument("--validate", action="store_true", help="ajoute la conformite XSD (implique --full)")
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.data_dir, "*.xml")))
    if not paths:
        raise SystemExit(f"Aucun .xml dans {args.data_dir}")

    print(f"Lecture de {len(paths)} fichiers...")
    trees, unreadable = [], []
    for path in paths:
        try:
            trees.append((os.path.basename(path), etree.parse(path)))
        except Exception as exc:
            unreadable.append((os.path.basename(path), str(exc)[:100]))
    print(f"{len(trees)} lisibles, {len(unreadable)} illisibles")
    for name, message in unreadable[:10]:
        print(f"    {name} : {message}")

    section_research_type(trees)
    section_contradiction(trees)
    section_paired_lists(trees)
    section_dead_mapping(trees)
    section_bilingual(trees)

    if args.full or args.validate:
        section_vocabularies(paths, args.validate)
    else:
        print("\n(section vocabulaires sautee -- relancez avec --full)")


if __name__ == "__main__":
    main()
