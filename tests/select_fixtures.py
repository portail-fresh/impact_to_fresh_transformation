"""Chooses the smallest set of real source files that exercises every tricky
code path in the pipeline, so the regression harness tests reality rather than
an idealised idea of what the source looks like.

Run it against the full corpus (the folder run_pipeline_batch.py reads):

    python tests/select_fixtures.py --data-dir /chemin/vers/xml_files_from_IH_API
    python tests/select_fixtures.py --data-dir ... --copy-to tests/fixtures

Each TRAIT below corresponds to a branch in HierarchicalExtractor or
FReSHXMLBuilder that nothing currently covers. Selection is a greedy set
cover: repeatedly take the file covering the most still-uncovered traits, so
20 files stand in for ~2000 without losing a code path.
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import sys

from lxml import etree  # type: ignore


def _texts(tree, xpath):
    out = []
    for node in tree.xpath(xpath):
        text = node if isinstance(node, str) else (node.text or "")
        out.append(text.strip())
    return out


def _looks_like_json(text):
    return text.startswith("{") or text.startswith("[{")


def detect_traits(path):
    """Returns (traits, note). Traits are the tricky-path markers this file
    carries; note carries anything worth printing next to it in the report."""
    try:
        tree = etree.parse(path)
    except Exception as exc:
        return {"unparseable_source"}, f"XML source illisible: {exc}"

    traits, notes = set(), []

    # --- Listes parallèles appariées par position (builder.py étapes 2.5 / 10) ---
    funders = tree.xpath("/xml/dataset/metadata/study_desc/production_statement/funding_agencies/funding_agency")
    funder_types = _texts(tree, "/xml/dataset/metadata/additional/fundingAgent/fundingAgentType/fundingagenttype")
    if len(funders) > 1:
        traits.add("multi_funder")
    if funders and len(funder_types) != len(funders):
        traits.add("funder_type_desync")
        notes.append(f"{len(funders)} financeurs / {len(funder_types)} types")

    sponsors = tree.xpath("/xml/dataset/metadata/study_desc/production_statement/producers/producer")
    if len(sponsors) > 1:
        traits.add("multi_sponsor")

    agencies = _texts(tree, "/xml/dataset/metadata/study_desc/study_authorization/agency/item/name")
    if len(agencies) > 1:
        traits.add("multi_agency")
    if any(a.strip().lower() in ("autre", "other") for a in agencies):
        traits.add("agency_other")

    # --- Fan-out ThirdPartySource : un <source> avec plusieurs <srcorig> ---
    for source in tree.xpath("/xml/dataset/metadata/study_desc/method/data_collection/sources/source"):
        if len(source.xpath("./srcOrig/srcorig")) > 1:
            traits.add("multi_srcorig")
            break

    # --- Blobs JSON encastrés dans du texte (builder.py étapes 8 / 10.5) ---
    for text in _texts(tree, "/xml/dataset/metadata/study_desc/method/data_collection/coll_mode/item"):
        if _looks_like_json(text):
            traits.add("json_collection_mode")
            try:
                json.loads(text.replace("\n", " ").replace("\r", ""))
            except Exception:
                # Ce cas est aujourd'hui avalé par un `except Exception: pass`
                # suivi d'un remove() : la donnée disparaît sans aucune trace.
                traits.add("json_collection_mode_invalid")
                notes.append("JSON collectionMode invalide (perte silencieuse)")

    for text in _texts(tree, "/xml/dataset/metadata/study_desc/method/data_collection/sampling_procedure"):
        if text.startswith("["):
            traits.add("json_sampling_mode")

    for text in _texts(tree, "/xml/dataset/metadata/study_desc/data_access/dataset_availability/status"):
        if _looks_like_json(text):
            traits.add("json_individual_access")

    # --- Faux tableaux "['a','b']" (builder.py étapes 10.8 / 10.9) ---
    bracket_sources = {
        "bracket_data_kind": "/xml/dataset/metadata/study_desc/study_info/data_kind",
        "bracket_used_standards": "/xml/dataset/metadata/study_desc/study_info/quality_statement/standards/standard/name",
        "bracket_recruitment": "/xml/dataset/metadata/study_desc/method/data_collection/sample_frame/frame_unit/unit_type",
    }
    for trait, xpath in bracket_sources.items():
        for text in _texts(tree, xpath):
            if text.startswith("[") and text.endswith("]"):
                traits.add(trait)
                # Une apostrophe dans un faux tableau est ce qui rendait
                # ast.literal_eval non déterministe -- cas à garder sous la main.
                if re.search(r"\w'\w", text):
                    traits.add("bracket_with_apostrophe")

    # --- Branche interventionnelle / observationnelle (builder.py étape 10.7) ---
    research_type = " ".join(_texts(tree, "/xml/dataset/metadata/additional/researchType/values")).lower()
    if "intervention" in research_type:
        traits.add("interventional")
    if "observation" in research_type:
        traits.add("observational")
    if not research_type:
        traits.add("no_research_type")
    if tree.xpath("/xml/dataset/metadata/additional/arms/arm"):
        traits.add("has_arms")
        if _texts(tree, "/xml/dataset/metadata/additional/arms/arm/type"):
            traits.add("has_arm_type")

    # --- Nœuds fantômes et valeurs par défaut (builder.py étapes 0 / 2) ---
    contributors = _texts(tree, "/xml/dataset/metadata/doc_desc/producers/producer/name")
    if not any(contributors):
        traits.add("empty_contributor")  # -> deviendra "Inconnu" en sortie
    for name in _texts(tree, "/xml/dataset/metadata/study_desc/oth_id/item[type='contributor']/name"):
        if re.fullmatch(r"[;,\s]*", name):
            traits.add("ghost_teammember")

    # --- Langue : le pipeline retombe sur "fr" quand la source est muette ---
    if not any(_texts(tree, "/xml/dataset/metadata/additional/originLang")):
        traits.add("no_origin_lang")

    return traits, "; ".join(notes)


def lang_of(path):
    name = os.path.basename(path).lower()
    if name.endswith("-fr.xml"):
        return "fr"
    if name.endswith("-en.xml"):
        return "en"
    return "?"


def sibling_in_other_lang(path):
    lang = lang_of(path)
    if lang == "?":
        return None
    other = "en" if lang == "fr" else "fr"
    candidate = re.sub(r"-%s\.xml$" % lang, "-%s.xml" % other, path, flags=re.I)
    return candidate if os.path.exists(candidate) else None


def failing_files(logs_dir):
    """Study names whose last validation report recorded a failure -- the most
    valuable fixtures of all, since freezing a known failure tells you the day
    it changes."""
    failing = set()
    for report in glob.glob(os.path.join(logs_dir, "*_validation_report.txt")):
        try:
            with open(report, encoding="utf-8") as f:
                if "Échec" in f.read():
                    failing.add(os.path.basename(report).replace("_validation_report.txt", ""))
        except Exception:
            continue
    return failing


def select(scanned, max_files, failing):
    """Greedy set cover over traits: repeatedly take the file covering the most
    still-uncovered traits. A file that currently fails validation wins ties --
    freezing a known failure is what tells you the day it changes."""
    remaining = dict(scanned)
    chosen, covered = [], set()

    while remaining and len(chosen) < max_files:
        def score(item):
            path, (traits, _note) = item
            gain = len(traits - covered)
            return (gain, os.path.basename(path) in failing, -len(traits))

        path, (traits, note) = max(remaining.items(), key=score)
        if not traits - covered:
            break  # plus rien de neuf à couvrir
        chosen.append((path, sorted(traits - covered), note))
        covered |= traits
        del remaining[path]

    return chosen, covered


def add_complements(chosen, scanned, max_files, banal_wanted=3):
    """The greedy cover stops as soon as no file adds a new trait, so on its own
    it never keeps an ordinary study -- yet the ordinary study is ~95% of the
    corpus and the one whose output you read most often. Same for the bilingual
    pair: both languages of one study must be in the set, since language drives
    vocabulary lookup, boolean/date handling, xml:lang and the XSD's own
    conditional typing."""
    picked = {p for p, _, _ in chosen}
    # Parcouru dans l'ordre glouton, jamais dans celui de l'ensemble : l'ordre
    # d'itération d'un set de chaînes varie d'une exécution à l'autre (hachage
    # randomisé), ce qui donnait une sélection de fixtures différente à chaque
    # lancement -- exactement ce qu'un harnais de non-régression ne peut pas se
    # permettre. En prime, l'ordre glouton prend le pendant de la fixture la
    # plus riche plutôt qu'un fichier au hasard.
    ordered = [p for p, _, _ in chosen]

    # 1. Une étude présente dans ses deux langues, de préférence déjà retenue.
    if not any(sibling_in_other_lang(p) in picked for p in ordered if sibling_in_other_lang(p)):
        sibling = next((sibling_in_other_lang(p) for p in ordered if sibling_in_other_lang(p)), None)
        if sibling:
            chosen.append((sibling, ["paire_bilingue"], f"pendant {lang_of(sibling)} d'une fixture retenue"))
            picked.add(sibling)
        else:
            for path in sorted(scanned):
                other = sibling_in_other_lang(path)
                if other and path not in picked and other not in picked:
                    chosen.append((path, ["paire_bilingue"], "paire fr/en complète"))
                    chosen.append((other, ["paire_bilingue"], "paire fr/en complète"))
                    picked |= {path, other}
                    break

    # 2. Quelques études ordinaires : le cas nominal doit être testé lui aussi.
    ordinary = sorted(
        (p for p in scanned if p not in picked),
        key=lambda p: (len(scanned[p][0]), os.path.basename(p)),
    )
    for path in ordinary[:banal_wanted]:
        if len(chosen) >= max_files + banal_wanted:
            break
        chosen.append((path, ["cas_ordinaire"], f"{len(scanned[path][0])} cas particulier(s)"))

    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True, help="dossier contenant les XML source du corpus complet")
    parser.add_argument("--logs-dir", help="dossier des logs du dernier batch (pour repérer les fichiers en échec)")
    parser.add_argument("--max", type=int, default=20, help="nombre maximum de fixtures (défaut 20)")
    parser.add_argument("--copy-to", help="si fourni, copie les fixtures retenues dans ce dossier")
    parser.add_argument("--report", default="tests/fixtures_selection.csv", help="où écrire le rapport CSV")
    args = parser.parse_args()

    sources = sorted(glob.glob(os.path.join(args.data_dir, "*.xml")))
    if not sources:
        sys.exit(f"Aucun .xml trouvé dans {args.data_dir}")

    failing = failing_files(args.logs_dir) if args.logs_dir else set()
    print(f"Analyse de {len(sources)} fichiers source...")
    if failing:
        print(f"  ({len(failing)} en échec de validation au dernier batch)")

    scanned = {path: detect_traits(path) for path in sources}

    all_traits = set()
    for traits, _ in scanned.values():
        all_traits |= traits

    chosen, covered = select(scanned, args.max, failing)

    chosen = add_complements(chosen, scanned, args.max)

    print(f"\n{len(chosen)} fixtures retenues, couvrant {len(covered)}/{len(all_traits)} cas :\n")
    for path, new_traits, note in chosen:
        flag = " [ÉCHEC VALIDATION]" if os.path.basename(path) in failing else ""
        print(f"  {os.path.basename(path)}{flag}")
        print(f"      apporte : {', '.join(new_traits)}")
        if note:
            print(f"      note    : {note}")

    missing = all_traits - covered
    if missing:
        print(f"\n  Non couvert (aucun fichier ne le porte seul) : {', '.join(sorted(missing))}")

    print("\nFréquence de chaque cas dans le corpus complet :")
    for trait in sorted(all_traits):
        count = sum(1 for traits, _ in scanned.values() if trait in traits)
        print(f"  {trait:32} {count:5} fichiers")

    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["fichier", "langue", "echec_validation", "cas_couverts", "note"])
        for path, new_traits, note in chosen:
            writer.writerow([
                os.path.basename(path), lang_of(path),
                "oui" if os.path.basename(path) in failing else "non",
                " ".join(new_traits), note,
            ])
    print(f"\nRapport écrit : {args.report}")

    if args.copy_to:
        os.makedirs(args.copy_to, exist_ok=True)
        for path, _, _ in chosen:
            shutil.copy2(path, os.path.join(args.copy_to, os.path.basename(path)))
        print(f"{len(chosen)} fichiers copiés dans {args.copy_to}")


if __name__ == "__main__":
    main()
