"""Repère les champs FReSH déclarés en texte libre qui portent en réalité une
liste fermée -- c'est-à-dire une liste déroulante côté source, aplatie en texte
à l'arrivée.

    python tests/detecter_listes_aplaties.py --data-dir tests/fixtures
    python tests/detecter_listes_aplaties.py --data-dir data/input

Pourquoi ça compte
------------------
Un champ contrôlé sort avec son identifiant de vocabulaire ; un champ texte
sort sans rien. Pour HealthDCAT-AP, où une notion s'identifie par une URI et
non par son libellé, un champ texte n'est pas alignable -- même quand son
contenu est, dans les faits, un terme choisi dans une liste.

Exemple constaté : PrimaryOutcomes est un champ texte côté FReSH, mais sur les
fiches de test il ne prend que quatre valeurs, répétées d'une fiche à l'autre.
C'était une liste déroulante côté source, et la structure a été perdue en
route.

Comment on distingue un vrai champ libre d'une liste aplatie
------------------------------------------------------------
Un vrai texte libre (résumé, critères d'inclusion) produit des valeurs longues
et presque toutes différentes. Une liste aplatie produit des valeurs courtes
qui reviennent à l'identique d'une fiche à l'autre. Le critère retenu est donc
la REPETITION rapportee au nombre de valeurs distinctes, plus une borne de
longueur.

Ce n'est pas une preuve, c'est un faisceau d'indices : le script sort des
candidats à vérifier, pas un verdict. Sur un petit échantillon il produira des
faux positifs (un champ rempli par deux fiches d'une même équipe se répète sans
être une liste) -- d'où l'exigence d'un minimum d'occurrences.

Les booléens, dates, adresses et identifiants sont écartés d'office : ils se
répètent aussi, mais ce ne sont pas des vocabulaires.
"""
import argparse
import collections
import os
import re
import statistics
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MAPPING_CSV = os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv")
VOCAB_DIR = os.path.join(BASE_DIR, "mappings", "vocabularies")

# Les valeurs contrôlées sont rangées dans un enfant <value> ; le nom du champ
# est donc celui du parent. <URI> porte l'identifiant, pas le libellé.
FEUILLES_PORTEUSES = {"value"}
FEUILLES_IGNOREES = {"URI"}

_BOOLEEN = {"0", "1", "true", "false", "oui", "non", "yes", "no"}
_DATE = re.compile(r"^\d{4}([-/]\d{1,2}){0,2}$")
_COURRIEL = re.compile(r"^[^@\s]+@[^@\s]+$")
_LIEN = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
_IDENTIFIANT = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")

# Un nombre d'occurrences trop bas rend la repetition non significative.
MIN_OCCURRENCES = 6
# En dessous de 2 valeurs distinctes il n'y a pas de "liste" a proprement parler.
MIN_DISTINCTES = 2
# Un terme de vocabulaire est court ; un resume ne l'est pas.
LONGUEUR_MAX_MEDIANE = 90


def champs_avec_referentiel():
    if not os.path.isdir(VOCAB_DIR):
        return set()
    return {f[:-4] for f in os.listdir(VOCAB_DIR) if f.endswith(".csv")}


def _valeurs_du_texte(texte):
    """Une fiche peut empiler plusieurs choix dans un seul champ, separes par un
    retour chariot venu du formulaire (voir PrimaryOutcomes). On les separe,
    sinon chaque combinaison compterait comme une valeur distincte et la
    repetition serait invisible."""
    for morceau in re.split(r"[\r\n]+", texte):
        morceau = morceau.strip()
        if morceau:
            yield morceau


def collecter(data_dir, limite=None):
    """Renvoie ({champ: Counter(valeurs)}, {champ: nb de fiches}, nb_lus, echecs)."""
    from run_pipeline import HierarchicalExtractor
    from src.builder import FReSHXMLBuilder

    fichiers = sorted(f for f in os.listdir(data_dir) if f.lower().endswith(".xml"))
    if limite:
        fichiers = fichiers[:limite]
    if not fichiers:
        sys.exit("Aucun fichier XML dans %s" % data_dir)

    valeurs = collections.defaultdict(collections.Counter)
    fiches = collections.Counter()
    echecs = []

    for nom in fichiers:
        try:
            ex = HierarchicalExtractor(os.path.join(data_dir, nom), MAPPING_CSV)
            racine = FReSHXMLBuilder(lang=ex.lang).build_tree(ex.process())
        except Exception:
            echecs.append((nom, traceback.format_exc().strip().splitlines()[-1]))
            continue

        vus = set()
        for parent in racine.iter():
            for el in parent:
                if len(el) or not (el.text or "").strip():
                    continue
                if el.tag in FEUILLES_IGNOREES:
                    continue
                champ = parent.tag if el.tag in FEUILLES_PORTEUSES else el.tag
                for v in _valeurs_du_texte(el.text):
                    valeurs[champ][v] += 1
                vus.add(champ)
        for champ in vus:
            fiches[champ] += 1

    return valeurs, fiches, len(fichiers), echecs


def _nature(compteur):
    """Ecarte ce qui se repete sans etre un vocabulaire."""
    echantillon = list(compteur)
    if all(v.lower() in _BOOLEEN for v in echantillon):
        return "booleen"
    if all(_DATE.match(v) for v in echantillon):
        return "date"
    if all(_COURRIEL.match(v) for v in echantillon):
        return "courriel"
    if all(_LIEN.match(v) for v in echantillon):
        return "lien"
    if all(_IDENTIFIANT.match(v) for v in echantillon):
        return "identifiant"
    return None


def analyser(valeurs, fiches, avec_referentiel):
    suspects, ecartes, libres = [], [], []
    for champ, compteur in valeurs.items():
        if champ in avec_referentiel:
            continue
        occurrences = sum(compteur.values())
        distinctes = len(compteur)
        mediane = statistics.median(len(v) for v in compteur)
        repetition = occurrences / distinctes

        nature = _nature(compteur)
        dossier = (champ, occurrences, distinctes, repetition, mediane,
                   fiches[champ], compteur)

        if nature:
            ecartes.append(dossier + (nature,))
        elif (occurrences >= MIN_OCCURRENCES and distinctes >= MIN_DISTINCTES
              and repetition >= 2 and mediane <= LONGUEUR_MAX_MEDIANE):
            suspects.append(dossier)
        else:
            libres.append(dossier)

    suspects.sort(key=lambda d: d[3], reverse=True)
    return suspects, ecartes, libres


def afficher(suspects, ecartes, libres, nb_lus, echecs, avec_referentiel, montrer_valeurs):
    print("=" * 74)
    print("CHAMPS TEXTE QUI PORTENT UNE LISTE FERMEE -- candidats")
    print("=" * 74)
    print()
    print("  %d fiches lues" % nb_lus)
    print("  %d champs ont un referentiel (non examines ici)" % len(avec_referentiel))
    print("  %d candidats, %d champs libres confirmes, %d ecartes (booleens, dates...)"
          % (len(suspects), len(libres), len(ecartes)))
    if echecs:
        print("  %d fiches n'ont pas pu etre lues" % len(echecs))
    print()
    if nb_lus < 100:
        print("  /!\\ Echantillon reduit : a 21 fiches ce script sort des pistes,")
        print("      pas des conclusions. Relancez-le sur data/input pour trancher.")
        print()

    if not suspects:
        print("Aucun candidat.")
        return

    print("-" * 74)
    print("%-30s %6s %6s %6s %6s" % ("champ", "occ.", "distinct", "repet.", "long."))
    print("-" * 74)
    for champ, occ, dist, rep, med, nfiches, _c in suspects:
        print("%-30s %6d %6d %6.1f %6d" % (champ, occ, dist, rep, med))
    print()
    print("  occ.     : valeurs rencontrees en tout")
    print("  distinct : valeurs differentes")
    print("  repet.   : occ./distinct -- plus c'est haut, plus la liste est fermee")
    print("  long.    : longueur mediane d'une valeur, en caracteres")
    print()

    if montrer_valeurs:
        for champ, occ, dist, rep, med, nfiches, compteur in suspects:
            print("-" * 74)
            print("%s  --  %d valeurs distinctes sur %d occurrences, dans %d fiches"
                  % (champ, dist, occ, nfiches))
            print("-" * 74)
            for v, n in compteur.most_common(montrer_valeurs):
                print("   %4d  %s" % (n, v[:66]))
            if dist > montrer_valeurs:
                print("   ... et %d autre(s) valeur(s)" % (dist - montrer_valeurs))
            print()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--valeurs", type=int, default=12,
                        help="valeurs listees par candidat (0 = aucune)")
    args = parser.parse_args()

    avec_referentiel = champs_avec_referentiel()
    valeurs, fiches, nb_lus, echecs = collecter(args.data_dir, args.limit)
    suspects, ecartes, libres = analyser(valeurs, fiches, avec_referentiel)
    afficher(suspects, ecartes, libres, nb_lus, echecs, avec_referentiel, args.valeurs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
