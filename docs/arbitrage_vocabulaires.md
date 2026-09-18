# Arbitrage : les valeurs qui ne trouvent pas leur terme de référentiel

**Pour qui** : la personne qui possède les vocabulaires contrôlés FReSH.
**Ce qu'on vous demande** : trancher les cases « décision » ci-dessous. Rien
d'autre — le code suit ensuite.

## Le problème en trois phrases

Quand le pipeline convertit une fiche, il remplace chaque valeur de champ
contrôlé par le terme exact du référentiel, ce qui lui donne son identifiant.
Quand la valeur écrite dans la fiche ne correspond à aucun terme, elle ressort
telle quelle, **sans identifiant**.

Sans identifiant, la valeur n'est pas alignable vers HealthDCAT-AP : dans un
graphe RDF une notion s'identifie par une URI, pas par son libellé. Ces valeurs
sont donc le vrai passif à résorber avant l'EHDS.

**1 922 valeurs sont dans ce cas sur les 2 154 fiches du catalogue.** Cinq
libellés en représentent 90 %.

## Comment lire ce document

Les écarts ne sont pas tous de même nature, et c'est tout l'enjeu : certains
sont mécaniques, d'autres changent le sens. Ils sont donc classés par **ce que
décider coûte**, pas par volume.

| catégorie | ce que ça veut dire | occurrences |
|---|---|---|
| A. Équivalence mécanique | singulier/pluriel, rien d'autre | 497 (26 %) |
| B. Reformulation du référentiel | le terme a été réécrit depuis la saisie | 1 093 (57 %) |
| C. Arbitrage de fond | deux cibles possibles, il faut choisir | 134 (7 %) |
| D. Défaut de la source | ce n'est pas une question de vocabulaire | 198 (10 %) |

---

## A. Équivalences mécaniques — 497 occurrences

Le référentiel est au singulier, la fiche au pluriel. Aucune autre différence,
y compris le préfixe de catégorie qui est identique des deux côtés.

| champ | écrit dans les fiches | terme du référentiel | occ. |
|---|---|---|---|
| HealthDeterminant | Déterminants biologiques : Prédisposition**s** génétique**s** | Déterminants biologiques : Prédisposition génétique | 220 |
| HealthDeterminant | Déterminants comportementaux : Addiction**s** | Déterminants comportementaux : Addiction | 144 |
| HealthDeterminant | Déterminants environnementaux : Autre**s** | Déterminants environnementaux : Autre | 133 |

**Mon avis** : à appliquer sans discussion. Le sens est identique, la catégorie
est la même, il n'existe aucun autre terme candidat dans le référentiel.

> **Décision** : ☐ appliquer ☐ ne pas appliquer ☐ à revoir

---

## B. Reformulations du référentiel — 1 093 occurrences

Ici le référentiel a été réécrit après que les fiches ont été saisies. La
notion visée paraît la même, mais **c'est vous qui savez si la réécriture a
changé le périmètre**, et c'est exactement ce qu'on ne peut pas deviner depuis
le code.

### B1. Données rapportées par les participants — 706 occurrences

| | |
|---|---|
| écrit dans les fiches | Données rapportées par le participant de l'étude |
| terme du référentiel | Données **de santé** rapportées par **les participants** de l'étude |
| identifiant | FDA6533 |
| libellé anglais | Participant-reported health data |

Deux différences : le pluriel, et l'ajout de « de santé ».

**Mon avis** : le pluriel est neutre. « De santé » restreint en théorie, mais le
référentiel ne propose aucun autre terme pour des données rapportées par le
participant qui ne seraient pas de santé. À confirmer plutôt qu'à arbitrer.

> **Décision** : ☐ équivalent ☐ non équivalent ☐ à revoir

### B2. Données paracliniques — 294 occurrences

| | |
|---|---|
| écrit dans les fiches | Données paracliniques |
| terme du référentiel | Données paracliniques **(hors biologiques)** |
| identifiant | FDA6856 |

**C'est celui sur lequel je ne veux pas trancher seul.** La parenthèse *exclut*
quelque chose. Si, au moment de la saisie, « Données paracliniques » englobait
le biologique, alors les rattacher au terme actuel fait sortir 294 valeurs du
périmètre qu'elles désignaient.

Deux éléments à verser au débat :

- le référentiel comporte une entrée distincte **Données biologiques**
  (FDA1123), donc la taxinomie actuelle sépare bien les deux ;
- il comporte aussi quatre sous-termes `Données paracliniques (hors
  biologiques) : Imagerie / Anthropométrie / Exploration fonctionnelle /
  Autre`, ce qui suggère que la parenthèse est une **précision** ajoutée à une
  notion inchangée, et non une restriction nouvelle.

**Mon avis** : probablement équivalent, mais c'est une lecture, pas une preuve.

> **Décision** : ☐ équivalent ☐ non équivalent ☐ à revoir

### B3. Via les professionnels d'exercice libéral — 93 occurrences

| | |
|---|---|
| écrit dans les fiches | Via les professionnels d'exercice libéral |
| terme du référentiel | Via les professionnels **de santé** d'exercice libéral |
| identifiant | FRS8098 |

**Mon avis** : équivalent. Dans un catalogue de recherche en santé, « les
professionnels d'exercice libéral » ne peut désigner que des professionnels de
santé. L'ajout précise, il ne restreint pas.

> **Décision** : ☐ équivalent ☐ non équivalent ☐ à revoir

---

## C. Arbitrage de fond — 134 occurrences

### Systèmes de soins et accès aux soins

Cette valeur ne ressemble à aucun terme actuel : c'est un libellé d'une version
antérieure du référentiel, qui **mélangeait une catégorie et un de ses
sous-termes**. Le référentiel actuel les sépare :

| candidat | ce que ça implique |
|---|---|
| `Déterminants liés au système de santé` | on garde la catégorie, on perd la précision « accès aux soins » |
| `Déterminants liés au système de santé : Accès aux soins` | on garde la précision, on affirme que c'est bien ce que la fiche voulait dire |
| les deux | une valeur source devient deux valeurs cibles |

Le référentiel propose aussi, sous la même catégorie, `Qualité des soins` et
`Consommation des soins` — ce qui montre qu'« accès aux soins » est un choix
parmi d'autres et non un synonyme de la catégorie.

**Mon avis** : je n'en ai pas de solide. Les trois options se défendent et le
choix engage 134 valeurs. Si l'une doit être privilégiée sans relire les
fiches, la première est la plus prudente : elle n'invente rien.

> **Décision** : ☐ catégorie seule ☐ sous-terme « Accès aux soins » ☐ les deux ☐ à revoir

---

## D. Défauts de la source — 198 occurrences

**Ceci n'est pas une question de vocabulaire**, et aucun alias ne le réglera.
C'est ici pour que le compte soit complet et parce que ça remonte à la saisie.

### D1. Deux termes accolés en un seul

La source livre parfois plusieurs termes du référentiel collés dans une même
chaîne, séparateur perdu. Exemple réel, dans la fiche FRESH-PEF152-fr :

```xml
<unit_type>['Base médico-administrative (de patients, Assurance Maladie/Mutuelle) Registre de maladies, de décès']</unit_type>
```

Ce sont deux termes distincts du référentiel `RecruitmentSource`
(FRS3712 et FRS3562) dans un seul élément de liste. Vérifié : le pipeline ne
colle rien, il reçoit la chaîne déjà collée.

Environ 88 occurrences identifiées sur `RecruitmentSource`.

**Piste technique, si la curation ne peut pas reprendre les fiches** : découper
la chaîne en cherchant les termes connus du référentiel. Quand une chaîne est
exactement la concaténation de deux termes existants, le découpage est certain.
À décider séparément — c'est un changement du comportement du pipeline.

### D2. Les deux langues collées

Sur `CollectionMode`, 2 occurrences où le libellé anglais et le libellé
français se suivent sans séparateur :

> `Recording (audio, video, electrophysiological, imaging)Enregistrement (audio, vidéo, électrophysiologique, imagerie)`

Volume négligeable, mais le mécanisme mérite d'être signalé à qui maintient
l'export : il peut toucher d'autres champs.

### D3. Le reste

`RecruitmentSource` compte une trentaine d'autres valeurs distinctes non
classées ici (≈ 70 occurrences), et `DocumentType` 6 occurrences dont l'écart
semble tenir à la ponctuation finale. Marginal, à traiter après les catégories
A à C.

Une vérification reste à faire, et elle peut basculer une soixantaine
d'occurrences en catégorie A : les termes du référentiel finissent par des
points de suspension typographiques (`entreprises…`) là où les fiches écrivent
peut-être `etc.`. Commande :

```
python tests/inspect_field.py --data-dir data/input \
  --xpath "/xml/dataset/metadata/study_desc/method/data_collection/sample_frame/frame_unit/unit_type"
```

---

## Ce qui se passe après votre décision

1. Les équivalences validées sont ajoutées à `VOCAB_ALIASES` dans
   `src/vocabularies.py` — quelques lignes, par langue et par champ.
2. Le harnais de régression affiche **exactement** quelles valeurs changent, sur
   les 21 fiches de test, avant toute conversion du catalogue.
3. L'audit est relancé sur les 2 154 fiches et donne le nouveau chiffre de
   valeurs non résolues.

Un alias fait correspondre une valeur écrite à un terme du référentiel au moment
de la conversion. **Il ne modifie pas les fiches du portail** : celles-ci
continueront de porter l'ancien libellé tant que la curation ne les reprend pas.
L'alias évite la perte d'identifiant, il ne remplace pas la correction à la
source.
