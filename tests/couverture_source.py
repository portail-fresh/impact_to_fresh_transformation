"""Part de la fiche source et demande, pour chaque champ rempli : est-ce que
quelqu'un le lit ?

    python tests/couverture_source.py --data-dir tests/fixtures
    python tests/couverture_source.py --data-dir data/input --exemples 5

Pourquoi ce sens-la
-------------------
L'audit existant (audit_corpus.py, section 4) part de la table de mapping et
demande : est-ce que cette regle trouve quelque chose ? C'est utile, mais ca
rate le defaut le plus couteux -- celui qu'on a vu passer plusieurs fois dans
l'historique du depot (« fix OtherDocumentation bug », « fix id bug »...) :

    une regle qui pointe vers un chemin FAUX mais EXISTANT passe pour vivante,
    pendant que le vrai champ source, lui, n'est lu par personne.

En partant de la source, ce cas devient visible : le champ est rempli dans des
centaines de fiches, et aucune regle ne le touche.

Comment « lu » est determine
----------------------------
Pas en comparant des chaines de caracteres : les regles portent des predicats
(topic[vocab='health determinant'], item[activity_type='...']) et quatre modes
dont trois sont relatifs au contexte de la ligne precedente. Comparer des
chemins textuellement donnerait n'importe quoi.

On rejoue donc les quatre branches de HierarchicalExtractor.process() -- les
memes appels xpath, dans le meme ordre, avec le meme etat -- et on collecte les
NOEUDS renvoyes. Un champ est lu si son noeud figure dans cette collecte. Les
predicats sont donc pris en compte gratuitement, puisque c'est lxml qui les
evalue, exactement comme pour l'extracteur.

Ce que l'outil ne fait pas
--------------------------
Il ne dit pas si un champ lu est range au bon endroit dans FReSH. Une regle qui
lit le bon champ source et l'ecrit dans le mauvais element cible passe au
travers. C'est un troisieme detecteur, a construire apres avoir vu ce que
celui-ci donne.

Il produit des CANDIDATS, pas des verdicts : beaucoup de champs source sont
legitimement non lus (metadonnees techniques de NADA, champs DDI que FReSH n'a
pas, doublons). D'ou l'echantillon de valeurs affiche a chaque ligne -- c'est
lui qui permet de trancher d'un coup d'oeil.
"""
import argparse
import collections
import csv
import io
import os
import re
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MAPPING_CSV = os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv")

# /xml/dataset/metadata/.../topic[3] -> /xml/dataset/metadata/.../topic
_INDICE = re.compile(r"\[\d+\]")

# Branches du document source qui ne decrivent pas l'etude mais le depot NADA
# lui-meme (identifiants internes, dates d'export, droits du catalogue). Elles
# ne sont pas censees etre mappees ; les signaler noierait le reste.
BRANCHES_TECHNIQUES = (
    "/xml/dataset/metadata/doc_desc/",
)


def charger_regles():
    """Renvoie la table telle que l'extracteur la lit : une liste ordonnee de
    (numero de ligne, source, cible). L'ordre est porteur de sens -- une ligne
    './' se rattache au dernier ROOT: ou ARRAY: rencontre."""
    regles = []
    with io.open(MAPPING_CSV, encoding="utf-8-sig") as f:
        lecteur = csv.DictReader(f)
        for row in lecteur:
            # line_num compte les lignes PHYSIQUES du fichier : c'est le numero
            # que l'on voit en ouvrant la table dans un editeur. Enumerer les
            # enregistrements donnait un numero decale des qu'une ligne vide
            # separe deux blocs -- inutilisable pour aller corriger.
            source = (row.get("source_xpath") or "").strip()
            cible = (row.get("target_xpath") or "").strip()
            if source and cible and source.lower() != "nan":
                regles.append((lecteur.line_num, source, cible))
    return regles


def noeuds_lus(tree, regles):
    """Rejoue les quatre branches de HierarchicalExtractor.process() et renvoie
    ({id(noeud) lus}, {numero de regle: [noeuds renvoyes]}).

    On ne reproduit que la SELECTION des noeuds, pas la construction du
    dictionnaire : c'est la seule partie qui nous interesse, et c'est aussi la
    seule ou une divergence avec l'extracteur serait possible. Les quatre
    branches ci-dessous sont copiees une a une sur les siennes."""
    lus = set()
    par_regle = collections.defaultdict(list)

    racines = []
    tableaux = []          # liste (par racine) de listes de sous-noeuds
    mode = "ABSOLUTE"

    for numero, source, _cible in regles:
        try:
            if source.startswith("/xml/"):
                mode = "ABSOLUTE"
                elements = _en_elements(tree.xpath(source))
                par_regle[numero].extend(elements)
                lus.update(id(e) for e in elements)

            elif source.startswith("ROOT:"):
                mode = "ROOT"
                racines = _en_elements(tree.xpath(source.split("ROOT:", 1)[1]))
                tableaux = []
                par_regle[numero].extend(racines)
                lus.update(id(e) for e in racines)

            elif source.startswith("ARRAY:"):
                mode = "ARRAY"
                relatif = source.split("ARRAY:", 1)[1]
                tableaux = []
                for racine in racines:
                    sous = _en_elements(racine.xpath(relatif))
                    tableaux.append(sous)
                    par_regle[numero].extend(sous)
                    lus.update(id(e) for e in sous)

            elif source.startswith("./"):
                if mode == "ROOT":
                    for racine in racines:
                        elements = _en_elements(racine.xpath(source))
                        par_regle[numero].extend(elements)
                        lus.update(id(e) for e in elements)
                elif mode == "ARRAY":
                    for sous in tableaux:
                        for noeud in sous:
                            elements = _en_elements(noeud.xpath(source))
                            par_regle[numero].extend(elements)
                            lus.update(id(e) for e in elements)
        except Exception:
            # Un XPath invalide dans la table ne doit pas arreter l'analyse :
            # c'est justement une anomalie a signaler.
            par_regle[numero] = None

    return lus, par_regle


def _en_elements(resultats):
    """Huit regles de la table lisent './text()' : lxml renvoie alors des chaines,
    pas des elements. Le noeud reellement lu est leur parent -- c'est lui qu'il
    faut marquer, sinon ces champs passeraient pour non lus."""
    sortie = []
    for r in resultats:
        if hasattr(r, "tag"):
            sortie.append(r)
        else:
            parent = getattr(r, "getparent", lambda: None)()
            if parent is not None:
                sortie.append(parent)
    return sortie


# Un noeud peut etre "non lu" tout en etant utilise : les regles filtrent avec
# des predicats (topic[vocab='health determinant'], item[type='contributor']).
# lxml renvoie alors le topic, pas le vocab -- mais la valeur du vocab a bel et
# bien servi, elle a decide du rangement. Ces champs ne sont pas perdus.
_CHAMP_DE_PREDICAT = re.compile(r"\[\s*([A-Za-z_][\w.-]*)\s*=")


def champs_filtres(regles):
    noms = set()
    for _numero, source, _cible in regles:
        noms.update(_CHAMP_DE_PREDICAT.findall(source))
    return noms


# La meme information s'ecrit souvent de deux facons dans une meme fiche : un
# resume d'affichage ("Clinical data") et un champ structure sous forme de fausse
# liste Python ("['Clinical data', 'Biological data']"), parfois avec une
# ponctuation differente ("determinants: Addiction" / "determinants : Addiction").
# Comparer les chaines a l'identique classait ces doublons comme donnee perdue.
# On compare donc des ATOMES normalises, avec la normalisation que le pipeline
# applique deja pour resoudre les vocabulaires -- ainsi le detecteur juge
# l'equivalence exactement comme le pipeline.
_FAUSSE_LISTE = re.compile(r"^\s*\[(.*)\]\s*$", re.S)

# Valeurs de remplissage : le formulaire les ecrit quand le champ n'a pas ete
# renseigne. Elles ne portent aucune information, donc un champ non lu qui ne
# contient qu'elles ne fait rien perdre.
_REMPLISSAGE_BRUT = (
    "Non renseigné", "Not specified", "Non applicable", "Not applicable",
    "NA", "N/A", "Non précisé", "Unknown", "Inconnu",
)


def _atomes(texte):
    m = _FAUSSE_LISTE.match(texte)
    if m:
        morceaux = re.split(r"'\s*,\s*'|\"\s*,\s*\"", m.group(1))
        morceaux = [x.strip().strip("'\"") for x in morceaux]
    else:
        morceaux = re.split(r"[\r\n]+", texte)
    return [x.strip() for x in morceaux if x.strip()]


# Les champs booleens sortent en 0/1 cote FReSH alors que les resumes d'affichage
# de la source ecrivent Oui/Non, Yes/No. Meme information : sans cette
# equivalence, additional/rareDiseases ("Non") passait pour perdu alors que
# <RareDiseases> vaut bien 0.
_BOOLEENS = {"oui": "1", "yes": "1", "true": "1", "non": "0", "no": "0", "false": "0"}


def _cle(atome):
    from src.vocabularies import _normalize
    k = _normalize(atome)
    return _BOOLEENS.get(k, k)


_REMPLISSAGE = None


def _est_remplissage(cle):
    global _REMPLISSAGE
    if _REMPLISSAGE is None:
        _REMPLISSAGE = {_cle(v) for v in _REMPLISSAGE_BRUT}
    return cle in _REMPLISSAGE


def _generalise(chemin):
    return _INDICE.sub("", chemin)


def _est_technique(chemin):
    return any(chemin.startswith(b) for b in BRANCHES_TECHNIQUES)


def analyser(data_dir, limite=None, garder_technique=False):
    from lxml import etree

    regles = charger_regles()
    fichiers = sorted(f for f in os.listdir(data_dir) if f.lower().endswith(".xml"))
    if limite:
        fichiers = fichiers[:limite]
    if not fichiers:
        sys.exit("Aucun fichier XML dans %s" % data_dir)

    # par chemin generalise : occurrences lues / non lues, fiches, valeurs vues,
    # et "doublons" = occurrences non lues dont la valeur exacte se retrouve dans
    # un champ qui, lui, est lu. Sans ce discriminant la liste est inexploitable :
    # le document source repete la meme information dans le resume de catalogue
    # (/xml/dataset/*) et dans le bloc DDI detaille, et seul le second est mappe.
    # Un champ non lu dont la valeur existe ailleurs ne perd rien ; un champ non
    # lu dont la valeur n'existe nulle part ailleurs, si.
    stats = collections.defaultdict(
        lambda: {"lues": 0, "non_lues": 0, "fiches": set(),
                 "valeurs": collections.Counter(), "doublons": 0, "remplissage": 0})
    # par regle : a-t-elle ramene au moins un contenu ?
    regle_a_du_contenu = collections.defaultdict(bool)
    regle_invalide = set()
    echecs = []

    for nom in fichiers:
        base = os.path.splitext(nom)[0]
        try:
            tree = etree.parse(os.path.join(data_dir, nom))
        except Exception:
            echecs.append((base, traceback.format_exc().strip().splitlines()[-1]))
            continue

        lus, par_regle = noeuds_lus(tree, regles)

        for numero, elements in par_regle.items():
            if elements is None:
                regle_invalide.add(numero)
                continue
            for e in elements:
                if (e.text or "").strip():
                    regle_a_du_contenu[numero] = True

        # Atomes effectivement recuperes par le mapping dans CETTE fiche, sous
        # leur forme normalisee.
        cles_lues = set()
        for e in tree.iter():
            if id(e) in lus and (e.text or "").strip():
                cles_lues.update(_cle(a) for a in _atomes(e.text.strip()))

        for el in tree.iter():
            texte = (el.text or "").strip()
            if not texte:
                continue
            chemin = _generalise(tree.getpath(el))
            if not garder_technique and _est_technique(chemin):
                continue
            s = stats[chemin]
            s["fiches"].add(base)
            s["valeurs"][texte] += 1
            if id(el) in lus:
                s["lues"] += 1
            else:
                s["non_lues"] += 1
                cles = [_cle(a) for a in _atomes(texte)]
                if cles and all(_est_remplissage(k) for k in cles):
                    s["remplissage"] += 1
                elif cles and all(k in cles_lues or _est_remplissage(k) for k in cles):
                    s["doublons"] += 1

    return stats, regles, regle_a_du_contenu, regle_invalide, len(fichiers), echecs


def afficher(stats, regles, regle_a_du_contenu, regle_invalide, nb_lus, echecs, exemples):
    filtres = champs_filtres(regles)
    perdus, doublons, sert_de_filtre, partiels = [], [], [], []
    for chemin, s in stats.items():
        if s["lues"] == 0:
            feuille = chemin.rsplit("/", 1)[-1]
            # Un chemin dont TOUTES les occurrences non lues sont des doublons ne
            # fait rien perdre : l'information part par un autre chemin.
            if s["doublons"] + s["remplissage"] >= s["non_lues"]:
                doublons.append((chemin, s))
            elif feuille in filtres:
                sert_de_filtre.append((chemin, s))
            else:
                perdus.append((chemin, s))
        elif s["non_lues"] > 0:
            partiels.append((chemin, s))

    perdus.sort(key=lambda c: -len(c[1]["fiches"]))
    doublons.sort(key=lambda c: -len(c[1]["fiches"]))
    partiels.sort(key=lambda c: -c[1]["non_lues"])
    jamais_lus = perdus

    print("=" * 76)
    print("COUVERTURE DE LA SOURCE -- qui lit quoi")
    print("=" * 76)
    print()
    print("  %d fiches lues" % nb_lus)
    print("  %d chemins source porteurs de contenu" % len(stats))
    print("  %d jamais lus dont la valeur ne part nulle part ailleurs" % len(perdus))
    print("  %d jamais lus mais dupliques dans un champ lu" % len(doublons))
    print("  %d jamais lus mais utilises comme filtre par une regle" % len(sert_de_filtre))
    print("  %d lus partiellement" % len(partiels))
    if echecs:
        print("  %d fiches illisibles" % len(echecs))
    print()

    # ---------------------------------------------------------------- 1
    print("-" * 76)
    print("1. DONNEE QUI N'ARRIVE JAMAIS DANS FReSH  --  %d" % len(perdus))
    print("-" * 76)
    print("  Champs remplis, lus par aucune regle, et dont la valeur ne se retrouve")
    print("  dans aucun champ lu : cette information est perdue a la conversion.")
    print("  Chaque ligne est un candidat -- oubli de mapping, ou concept que FReSH")
    print("  n'a pas. L'echantillon de valeurs permet de trancher.")
    print()
    if not jamais_lus:
        print("  Aucun.")
    for chemin, s in jamais_lus:
        print("  %s" % chemin)
        print("      %d fiche(s), %d occurrence(s), %d valeur(s) distincte(s)"
              % (len(s["fiches"]), s["non_lues"], len(s["valeurs"])))
        # Un champ presque toujours duplique est un quasi-doublon : ce n'est pas
        # lui qui est interessant, c'est l'occurrence ou les deux sources
        # divergent. Le ratio le dit d'un coup d'oeil.
        sans_perte = s["doublons"] + s["remplissage"]
        if sans_perte:
            print("      dont %d/%d sans perte (%d doublon(s), %d valeur(s) de"
                  " remplissage) -- %d occurrence(s) a examiner"
                  % (sans_perte, s["non_lues"], s["doublons"], s["remplissage"],
                     s["non_lues"] - sans_perte))
        for valeur, n in s["valeurs"].most_common(exemples):
            print("          %4d  %s" % (n, valeur[:62].replace("\n", " ")))
        if len(s["valeurs"]) > exemples:
            print("          ...   et %d autre(s)" % (len(s["valeurs"]) - exemples))
        print()

    # ---------------------------------------------------------------- 1bis
    print("-" * 76)
    print("1 bis. NON LUS, MAIS L'INFORMATION PART AILLEURS  --  %d" % len(doublons))
    print("-" * 76)
    print("  Le document source repete la meme information a deux endroits : le")
    print("  resume de catalogue et le bloc DDI detaille. Seul l'un des deux est")
    print("  mappe, ce qui est normal. Rien n'est perdu ici -- liste donnee pour")
    print("  memoire, a ne pas confondre avec la section 1.")
    print()
    for chemin, s in doublons:
        print("  %-64s %d fiche(s)" % (chemin[-64:], len(s["fiches"])))
    print()

    print("-" * 76)
    print("1 ter. NON LUS, MAIS UTILISES COMME FILTRE  --  %d" % len(sert_de_filtre))
    print("-" * 76)
    print("  Ces champs servent de critere dans un predicat (topic[vocab='...']).")
    print("  lxml renvoie le noeud filtre et non le critere, d'ou leur absence de la")
    print("  collecte -- mais leur valeur a bien decide du rangement.")
    print()
    for chemin, s in sert_de_filtre:
        print("  %-64s %d fiche(s)" % (chemin[-64:], len(s["fiches"])))
    print()

    # ---------------------------------------------------------------- 2
    print("-" * 76)
    print("2. CHAMPS LUS SEULEMENT EN PARTIE  --  %d" % len(partiels))
    print("-" * 76)
    print("  Un filtre laisse passer certaines occurrences et pas d'autres. C'est")
    print("  normal quand un predicat trie (topic[vocab='...']) -- suspect quand la")
    print("  part non lue est grosse.")
    print()
    if not partiels:
        print("  Aucun.")
    for chemin, s in partiels:
        total = s["lues"] + s["non_lues"]
        print("  %-62s %d/%d non lus" % (chemin[-62:], s["non_lues"], total))
    print()

    # ---------------------------------------------------------------- 3
    print("-" * 76)
    print("3. REGLES QUI NE RAMENENT JAMAIS DE CONTENU")
    print("-" * 76)
    print("  L'audit existant teste si le noeud EXISTE. Ici on teste s'il a du")
    print("  TEXTE : une regle qui vise un noeud toujours vide est soit inutile,")
    print("  soit mal ciblee. Les lignes ROOT: et ARRAY: sont exclues, ce sont des")
    print("  points d'ancrage de boucle et non des porteuses de valeur.")
    print()
    muettes = [(n, s, c) for n, s, c in regles
               if not s.startswith(("ROOT:", "ARRAY:")) and not regle_a_du_contenu[n]]
    if not muettes:
        print("  Aucune.")
    for numero, source, cible in muettes:
        print("  ligne %-4d %s" % (numero, cible))
        print("             lit : %s" % source)
    print()

    if regle_invalide:
        print("-" * 76)
        print("4. REGLES DONT LE XPATH EST INVALIDE  --  %d" % len(regle_invalide))
        print("-" * 76)
        for numero, source, cible in regles:
            if numero in regle_invalide:
                print("  ligne %-4d %s\n             %s" % (numero, cible, source))
        print()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--exemples", type=int, default=4,
                        help="valeurs affichees par champ non lu")
    parser.add_argument("--avec-technique", action="store_true",
                        help="inclure les metadonnees du depot NADA (doc_desc)")
    args = parser.parse_args()

    stats, regles, contenu, invalides, nb, echecs = analyser(
        args.data_dir, args.limit, args.avec_technique)
    afficher(stats, regles, contenu, invalides, nb, echecs, args.exemples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
