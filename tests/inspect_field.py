"""Lists the distinct values a source field actually takes across the corpus,
with their counts -- so a question about the data is settled by looking rather
than by guessing what the source system probably puts there.

    python tests/inspect_field.py --data-dir data\\input --xpath "/xml/dataset/metadata/additional/researchType/values"

Without --xpath it runs a preset sweep over the fields that decide which branch
of StudyMethodology the pipeline takes, which is the question that prompted it:
researchType reported only 2 interventional studies out of 2154 files, and that
is implausible for a health research catalogue.
"""
import argparse
import collections
import glob
import os

from lxml import etree  # type: ignore

# Chaque entrée est un signal indépendant du caractère interventionnel d'une
# étude. Si researchType dit "observationnelle" alors que trialPhase ou arms
# sont remplis, c'est la source qui se contredit -- et le pipeline suit
# aveuglément researchType (builder.py étape 10.7 élague l'autre branche).
PRESET = {
    "researchType": "/xml/dataset/metadata/additional/researchType/values",
    "isClinicalTrial": "/xml/dataset/metadata/additional/interventionalStudy/isClinicalTrial",
    "trialPhase": "/xml/dataset/metadata/additional/interventionalStudy/trialPhase/trialphase",
    "researchPurpose": "/xml/dataset/metadata/additional/interventionalStudy/researchPurpose/researchpurpose",
    "interventionalStudyModel": "/xml/dataset/metadata/additional/interventionalStudy/interventionalStudyModel",
    "arms": "/xml/dataset/metadata/additional/arms/arm/title",
    "armType": "/xml/dataset/metadata/additional/arms/arm/type",
    "studyClass": "/xml/dataset/metadata/study_desc/method/study_class",
}


def values_at(tree, xpath):
    out = []
    for node in tree.xpath(xpath):
        text = node if isinstance(node, str) else (node.text or "")
        text = " ".join(text.split())
        if text:
            out.append(text)
    return out


def report(sources, label, xpath, top):
    counter = collections.Counter()
    files_with_value = 0
    for tree in sources:
        found = values_at(tree, xpath)
        if found:
            files_with_value += 1
        for value in found:
            counter[value] += 1

    total = len(sources)
    print(f"\n=== {label} ===")
    print(f"    {xpath}")
    print(f"    rempli dans {files_with_value} / {total} fichiers")
    if not counter:
        print("    (aucune valeur)")
        return
    for value, count in counter.most_common(top):
        shown = value if len(value) <= 90 else value[:87] + "..."
        print(f"    {count:6}  {shown}")
    if len(counter) > top:
        print(f"    ... et {len(counter) - top} autre(s) valeur(s) distincte(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--xpath", help="un chemin précis ; sinon la batterie prédéfinie")
    parser.add_argument("--top", type=int, default=15, help="nombre de valeurs distinctes affichées")
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(args.data_dir, "*.xml")))
    if not paths:
        raise SystemExit(f"Aucun .xml dans {args.data_dir}")

    print(f"Lecture de {len(paths)} fichiers...")
    sources = []
    for path in paths:
        try:
            sources.append(etree.parse(path))
        except Exception:
            pass
    print(f"{len(sources)} fichiers lisibles.")

    if args.xpath:
        report(sources, "champ demandé", args.xpath, args.top)
    else:
        for label, xpath in PRESET.items():
            report(sources, label, xpath, args.top)


if __name__ == "__main__":
    main()
