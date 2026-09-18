"""Agrège, sur tout un dossier de fiches source, ce que le pipeline a dû réparer
faute de mieux -- et le présente comme un document destiné à la curation.

    python tests/rapport_qualite.py --data-dir data/input > rapport_qualite.txt

Pourquoi ce rapport existe
--------------------------
Le pipeline produit un XML conforme au XSD même quand la fiche source est
lacunaire : il invente le contributeur manquant, jette le membre d'équipe sans
nom, abandonne la source tierce sans type. La sortie est alors *valide* et donc
indiscernable d'une fiche saine. Personne, côté curation, ne peut deviner quelle
fiche a été rafistolée ni sur quel champ.

Ce script rend visible exactement cela. Il ne juge pas la conversion -- pour ça
il y a le harnais de régression et l'audit de conformité -- il dit ce que la
SOURCE n'a pas fourni.

Ce qu'il ne rapporte pas, délibérément
--------------------------------------
Les insertions purement structurelles, comme l'élément vide <OtherClusion> que
le XSD exige même sans critères d'inclusion. Elles concernent presque toutes les
fiches et ne disent rien du contenu : les signaler noierait les vraies lacunes.
Si la curation veut suivre la complétude des critères d'inclusion, c'est une
mesure à part, pas une réparation.

La validation XSD est volontairement sautée : seul le constructeur est
nécessaire ici, et recompiler le schéma XSD 1.1 par fiche coûterait des heures
sur 2154 fiches pour une information qu'on n'utilise pas.
"""
import argparse
import collections
import os
import re
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MAPPING_CSV = os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv")

# Pour chaque code : ce que le pipeline a fait, et ce que la curation peut en
# faire. Sans cette seconde colonne le rapport n'est qu'une liste d'erreurs de
# plus ; c'est elle qui le rend actionnable.
EXPLICATIONS = {
    "CONTRIBUTEUR_INVENTE": (
        "La fiche ne nomme aucun contributeur de métadonnées, champ pourtant "
        "obligatoire. Le pipeline a écrit « Inconnu » pour que le fichier reste "
        "conforme.",
        "Renseigner le contributeur réel sur la fiche. Tant que ce n'est pas "
        "fait, la valeur « Inconnu » se retrouvera telle quelle dans le "
        "catalogue publié.",
    ),
    "MEMBRE_EQUIPE_VIDE": (
        "La source a émis un membre d'équipe sans nom ni affiliation : l'API "
        "joint prénom et nom même quand les deux sont vides, ce qui donne un "
        "nom réduit à un point-virgule. Le pipeline a supprimé ce membre.",
        "Vérifier si un membre d'équipe a été saisi puis vidé. Si la ligne est "
        "un résidu de saisie, la supprimer sur la fiche ; sinon, compléter le "
        "nom.",
    ),
    "LIBELLE_ABSENT": (
        "Un terme de vocabulaire porte un identifiant mais aucun libellé. Le "
        "schéma exige le libellé avant l'identifiant, donc le nœud entier a été "
        "abandonné -- l'identifiant est perdu avec lui.",
        "Rouvrir le terme concerné sur la fiche et le resélectionner dans le "
        "vocabulaire, pour qu'il reparte avec son libellé. L'identifiant "
        "conservé ci-dessous permet de retrouver de quel terme il s'agit.",
    ),
    "IDENTIFIANT_ORGANISATION_VIDE": (
        "Un emplacement d'identifiant d'organisation (ROR, RNSR...) existe mais "
        "ne contient rien. Le pipeline l'a supprimé.",
        "Renseigner l'identifiant de l'organisation. C'est la donnée qui "
        "manquera le plus au futur alignement HealthDCAT-AP, où une organisation "
        "s'identifie par une URI et non par son nom.",
    ),
    "SOURCE_TIERCE_SANS_TYPE": (
        "Une source de données tierce est déclarée sans type, alors que le "
        "schéma l'impose. Le pipeline a abandonné la source entière -- nom et "
        "finalité compris.",
        "Renseigner le type de la source sur la fiche. En l'état, la "
        "réutilisation de données déclarée par l'étude n'apparaît pas du tout "
        "dans le catalogue.",
    ),
}

# FRESH-PEF3101-fr.xml -> ("FRESH-PEF3101", "fr")
_NOM = re.compile(r"^(?P<etude>.+)-(?P<langue>fr|en)$", re.IGNORECASE)


def _decompose(nom_fichier):
    m = _NOM.match(nom_fichier)
    if m:
        return m.group("etude"), m.group("langue").lower()
    return nom_fichier, "?"


def collecter(data_dir, limite=None):
    """Passe chaque fiche dans l'extracteur et le constructeur, et récolte leurs
    registres. Renvoie (lignes, nb_lus, echecs).

    Une fiche qui fait planter le pipeline est comptée à part : la taire
    donnerait un rapport faussement rassurant."""
    from run_pipeline import HierarchicalExtractor
    from src.builder import FReSHXMLBuilder

    fichiers = sorted(f for f in os.listdir(data_dir) if f.lower().endswith(".xml"))
    if limite:
        fichiers = fichiers[:limite]
    if not fichiers:
        sys.exit("Aucun fichier XML dans %s" % data_dir)

    lignes = []
    echecs = []
    for nom in fichiers:
        base = os.path.splitext(nom)[0]
        etude, langue = _decompose(base)
        try:
            extracteur = HierarchicalExtractor(os.path.join(data_dir, nom), MAPPING_CSV)
            constructeur = FReSHXMLBuilder(lang=extracteur.lang)
            constructeur.build_tree(extracteur.process())
        except Exception:
            echecs.append((base, traceback.format_exc().strip().splitlines()[-1]))
            continue
        for code, element, detail in constructeur.corrections:
            lignes.append((etude, langue, base, code, element, detail))

    return lignes, len(fichiers), echecs


def afficher(lignes, nb_lus, echecs, detail_max):
    fiches_touchees = {l[2] for l in lignes}
    etudes_touchees = {l[0] for l in lignes}

    print("=" * 72)
    print("RAPPORT QUALITE -- ce que le pipeline a repare faute de mieux")
    print("=" * 72)
    print()
    print("  %s lue%s" % (_pluriel(nb_lus, "fiche"), "s" if nb_lus > 1 else ""))
    print("  %s concernee%s (%s distincte%s)"
          % (_pluriel(len(fiches_touchees), "fiche"),
             "s" if len(fiches_touchees) > 1 else "",
             _pluriel(len(etudes_touchees), "etude"),
             "s" if len(etudes_touchees) > 1 else ""))
    print("  %s au total" % _pluriel(len(lignes), "reparation"))
    if echecs:
        print("  %s n'%s pas pu etre traitee%s (voir la fin du rapport)"
              % (_pluriel(len(echecs), "fiche"),
                 "ont" if len(echecs) > 1 else "a",
                 "s" if len(echecs) > 1 else ""))
    print()

    if not lignes:
        print("Aucune reparation : toutes les fiches lues fournissent ce que le")
        print("schema exige. Rien a remonter a la curation.")
        return

    par_code = collections.Counter(l[3] for l in lignes)

    print("-" * 72)
    print("VUE D'ENSEMBLE")
    print("-" * 72)
    print("  %-32s %12s %10s" % ("motif", "occurrences", "etudes"))
    for code, n in par_code.most_common():
        etudes = {l[0] for l in lignes if l[3] == code}
        print("  %-32s %12d %10d" % (code, n, len(etudes)))
    print()

    for code, _ in par_code.most_common():
        concernees = [l for l in lignes if l[3] == code]
        etudes = sorted({l[0] for l in concernees})
        constat, action = EXPLICATIONS.get(
            code, ("(motif non documente)", "(a documenter)"))

        print("-" * 72)
        print("%s  --  %s, %s"
              % (code, _pluriel(len(concernees), "occurrence"), _pluriel(len(etudes), "etude")))
        print("-" * 72)
        print("  Ce qui s'est passe :")
        for ligne in _paragraphe(constat):
            print("    " + ligne)
        print("  Ce que la curation peut faire :")
        for ligne in _paragraphe(action):
            print("    " + ligne)
        print()

        # Une etude apparait en francais et en anglais ; on les rassemble pour
        # que la curation ouvre une fiche, pas deux.
        par_etude = collections.OrderedDict()
        for etude, langue, _base, _code, element, detail in concernees:
            par_etude.setdefault(etude, []).append((langue, element, detail))

        print("  Etude%s concernee%s :"
              % ("s" if len(etudes) > 1 else "", "s" if len(etudes) > 1 else ""))
        for i, (etude, occurrences) in enumerate(sorted(par_etude.items())):
            if detail_max and i >= detail_max:
                print("    ... et %d autres etudes" % (len(par_etude) - detail_max))
                break
            langues = sorted({o[0] for o in occurrences})
            print("    %-22s (%s)" % (etude, "+".join(langues)))
            vus = set()
            for _langue, element, detail in occurrences:
                cle = (element, detail)
                if cle in vus:
                    continue
                vus.add(cle)
                print("        <%s> %s" % (element, detail))
        print()

    if echecs:
        print("-" * 72)
        print("FICHES NON TRAITEES  --  %d" % len(echecs))  # entete fixe, volontairement
        print("-" * 72)
        print("  Le pipeline s'est arrete sur ces fiches. Elles ne sont comptees")
        print("  dans aucun motif ci-dessus : leur contenu n'a pas ete examine.")
        for base, message in echecs:
            print("    %-28s %s" % (base, message[:80]))
        print()


def _pluriel(n, singulier, pluriel=None):
    """Accorde un decompte. Un rapport destine a la curation se lit mieux sans
    les « 1 occurrences » qui trahissent la sortie de script."""
    return "%d %s" % (n, singulier if abs(n) <= 1 else (pluriel or singulier + "s"))


def _paragraphe(texte, largeur=66):
    """Coupe un texte en lignes lisibles dans un terminal."""
    mots = texte.split()
    ligne, lignes = "", []
    for mot in mots:
        if ligne and len(ligne) + 1 + len(mot) > largeur:
            lignes.append(ligne)
            ligne = mot
        else:
            ligne = (ligne + " " + mot).strip()
    if ligne:
        lignes.append(ligne)
    return lignes


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True,
                        help="dossier des fiches source (ex. data/input)")
    parser.add_argument("--limit", type=int, default=None,
                        help="n'examiner que les N premieres fiches (mise au point)")
    parser.add_argument("--detail-max", type=int, default=40,
                        help="nombre d'etudes listees par motif (0 = toutes)")
    args = parser.parse_args()

    lignes, nb_lus, echecs = collecter(args.data_dir, args.limit)
    afficher(lignes, nb_lus, echecs, args.detail_max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
