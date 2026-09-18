# Pistes ouvertes — état au 18 septembre 2026

Ce document existe pour qu'on reprenne sur des faits et non sur des souvenirs.
Chaque piste dit ce qui est **mesuré**, ce qui est **supposé**, et la commande
qui tranche.

Toutes les mesures ci-dessous portent sur les **21 fiches de `tests/fixtures/`**,
sauf mention contraire. C'est assez pour repérer un motif, pas pour le chiffrer :
la commande de vérification sur les 2 154 fiches est donnée à chaque fois.

---

## 1. Les noms de personnes sortent avec un point-virgule

**Statut : mesuré, non corrigé. Décision attendue.**

Quatre champs publient `Prénom;NOM` au lieu de `Prénom NOM` :

| champ | occurrences | avec point-virgule |
|---|---|---|
| ContactName | 42 | **100 %** |
| PIName | 23 | **100 %** |
| TeamMemberName | 12 | **100 %** |
| DIContactName | 10 | **100 %** |
| ContributorName | 21 | 0 % |

Exemple réel : `Elodie;SPEYER`, `Christel;LECLERC-ZWIRN`.

**Pourquoi c'est un défaut et pas une convention.** Le XSD documente
explicitement le format attendu :

> `ContactName` — *Prénom NOM du contact* / *First name LAST NAME of the contact*

Une espace, pas un point-virgule. Le champ est typé `xsd:string`, donc la
validation passe : c'est exactement le genre de défaut qu'un schéma ne peut pas
attraper.

**D'où ça vient.** L'API source joint prénom et nom avec un `;`. Le pipeline
connaît déjà cet artefact — l'étape 0 de `_enforce_mandatory_dummy_nodes()`
détecte le cas dégénéré `<name>;</name>` (les deux parties vides) pour supprimer
le membre d'équipe fantôme. Mais quand les deux parties sont remplies, la chaîne
passe telle quelle. `ContributorName` y échappe parce qu'il vient d'un autre
chemin source (`doc_desc/producers/producer/name`), déjà correctement formaté.

**Ce qui a été vérifié.** Sur 87 valeurs, **toutes** contiennent exactement un
point-virgule, toujours entre prénom et nom. Aucune ne sépare deux personnes.

**Ce qui reste à vérifier avant de corriger.** Le corpus complet contient-il des
valeurs à 0 ou à 2 points-virgules ? S'il existe des valeurs où le `;` sépare
deux personnes, la correction devrait les traiter autrement.

```
python tests/inspect_field.py --data-dir data/input \
  --xpath "/xml/dataset/metadata/additional/contactPoint/contact/name"
```

**Correction envisagée.** Dans `builder.py`, à l'endroit où l'étape 0 traite
déjà le cas vide : remplacer le `;` par une espace **uniquement** quand il y en
a exactement un et que les deux côtés sont non vides. Laisser tout le reste
intact et le signaler au rapport qualité.

**Portée.** Cela modifierait la sortie de pratiquement toutes les fiches du
catalogue. C'est pour ça que ce n'est pas fait : le harnais montrera exactement
l'ampleur avant qu'on décide.

---

## 2. Des champs texte portent en réalité une liste fermée

**Statut : mesuré sur 21 fiches, à confirmer sur le corpus.**

Un champ contrôlé sort avec son identifiant de vocabulaire ; un champ texte sort
sans rien. Pour HealthDCAT-AP, où une notion s'identifie par une URI, un champ
texte n'est pas alignable — **même quand son contenu est en fait un terme choisi
dans une liste déroulante**.

L'outil `tests/detecter_listes_aplaties.py` repère ces cas par la répétition :
un vrai texte libre produit des valeurs longues et presque toutes différentes,
une liste aplatie produit des valeurs courtes qui reviennent à l'identique.

### 2a. Listes fermées sans référentiel

| champ | valeurs distinctes | exemples |
|---|---|---|
| `AnalysisUnit` | 2 | `Individus` / `Individuals` |
| `SponsorType` | 5 | `Public (France)`, `Industry` / `Industrie`, `Private non-profit` / `Privé à but non lucratif` |
| `AggregatedDataAccess` | 5 | `Accès libre` / `Free access`, `Accès restreint sur projet spécifique` |
| `PrimaryOutcomes` | 13 (≈ 4 notions × 2 langues + variantes) | `Evénements de santé/morbidité`, `Consommation de soins/services de santé` |

Chacun a la signature d'une liste déroulante : les mêmes valeurs, dans les deux
langues, d'une fiche à l'autre. Un vocabulaire contrôlé leur donnerait un
identifiant.

`AggregatedDataAccess` est un cas mixte : quatre valeurs de liste **plus** une
saisie libre (`The data will be hosted on the France Cohortes information
system.`). Le champ cumule donc liste et texte, ce qui est le pire des deux.

### 2b. Entités nommées récurrentes — un autre problème

| champ | occurrences | distinctes |
|---|---|---|
| `OrganisationName` | 77 | 15 |
| `FundingAgentName` | 48 | 20 |
| `SponsorName` | 35 | 14 |

`INSTITUT NATIONAL DE LA SANTE ET DE LA RECHERCHE MEDICALE (INSERM)` revient
21 fois en `OrganisationName`, 10 en `SponsorName`, 6 en `FundingAgentName`.

Ce ne sont pas des listes aplaties : ce sont des **organisations qui ont un
identifiant ROR**. Le pipeline sait déjà transporter ces identifiants quand la
source les fournit (`<FundingAgentPID><PIDSchema><value>ROR</value>…`), mais rien
ne relie le nom à l'identifiant quand la source ne le donne pas. C'est un
chantier d'alignement d'entités, distinct des vocabulaires, et il pèsera lourd
dans le mapping HealthDCAT-AP.

### 2c. Un champ d'identifiant non contrôlé

`IDSchema` prend 4 valeurs pour 2 concepts :

```
40  FReSH
15  PEF
 2  PORTAIL EPIDEMIOLOGIE FRANCE (PEF)
 2  Portail Épidémiologie France (PEF)
```

Trois écritures de la même chose. Un champ qui nomme un schéma d'identifiant
devrait être contrôlé.

### Vérification sur le corpus

```
python tests/detecter_listes_aplaties.py --data-dir data/input
```

---

## 3. Deux questions qui décident du traitement des vocabulaires

**Statut : non tranchées. Elles priment sur l'arbitrage lui-même.**

Voir `docs/arbitrage_vocabulaires.md` pour le détail des 1 922 valeurs non
résolues. Deux questions conditionnent la suite :

### 3a. La liste déroulante du formulaire est-elle à jour ?

Les valeurs non résolues viennent de listes déroulantes, pas de saisie libre —
c'est établi : 542 occurrences **strictement identiques**, ponctuation
typographique comprise, avec des effectifs français et anglais qui se répondent
(542/542, 151/151, 28/28).

Donc personne n'a mal tapé : **le libellé de la liste a été réécrit depuis**.
Reste à savoir si le formulaire propose aujourd'hui l'ancien ou le nouveau
libellé :

- s'il propose encore l'ancien, toute fiche créée aujourd'hui reproduit le
  problème, et les alias sont un pansement permanent ;
- s'il a été mis à jour, le passif est fermé et les alias ne concernent que
  l'existant.

**Question pour qui maintient le formulaire du portail.** À poser avant de
valider les alias.

### 3b. Le passif est-il propre aux fiches importées de PEF ?

Sur les 21 fiches de test, **toutes** les valeurs non résolues sont dans des
fiches `FRESH-PEF` (importées du Portail Épidémiologie France), et les deux
fiches nativement FReSH n'en ont aucune. **Deux fiches natives, c'est trop peu
pour conclure** — mais si ça se confirme, l'origine du problème est l'import et
non une dérive de vocabulaire interne, et le traitement diffère.

Vérification : découper le comptage des valeurs non résolues selon l'origine de
la fiche (nom de fichier `FRESH-PEF*` contre `FReSH-<numérique>`). Une dizaine
de minutes à ajouter à `audit_corpus.py`.

Un indice contraire, déjà mesuré : `Via les professionnels d'exercice libéral`
(93 occurrences) ne se résout pas alors que son équivalent anglais `Through
independent healthcare practitioners` (94) se résout. Le libellé **français** du
référentiel FReSH a été réécrit sans que l'anglais le soit. Ça, l'import PEF ne
peut pas en être responsable — donc il y a au moins une part de dérive interne.

---

## 4. Le découpage des valeurs collées

**Statut : mesuré, faisable, non décidé.**

La source livre parfois deux termes du référentiel collés dans une seule chaîne,
séparateur perdu en amont. Vérifié sur `FRESH-PEF152-fr` :

```xml
<unit_type>['Base médico-administrative (de patients, Assurance Maladie/Mutuelle) Registre de maladies, de décès']</unit_type>
```

Ce sont deux termes distincts de `RecruitmentSource` (FRS3712 et FRS3562) dans
un seul élément de liste. **Le pipeline ne colle rien** : il reçoit la chaîne
déjà collée.

Volume estimé : **~190 occurrences**, soit 10 % du passif de vocabulaire.
(Estimation revue à la hausse : 88 dans une première lecture, puis recomptée à
partir de la distribution complète de `unit_type` — 44+44, 16+16, 9, plus une
partie des 34 valeurs distinctes restantes.)

**Correction envisagée.** Quand une chaîne est exactement la concaténation de
deux termes connus du référentiel, le découpage est certain et ne peut pas se
tromper. Ça récupérerait ces ~190 occurrences **sans rien demander à la
curation**. Mais ça change le comportement du pipeline, donc c'est une décision,
pas une évidence.

---

## 5. Ce qui est clos

Pour mémoire, afin de ne pas y revenir :

- **Les 6 règles `Other*Determinant` soupçonnées mortes ne le sont pas.** Le
  catalogue ne contient que 4 valeurs de `vocab` : `health determinant`,
  `health theme`, `cim-11`, `other environmental determinant`. Cette dernière
  fonctionne de bout en bout (vérifié sur `FRESH-PEF3101`). Les 6 autres règles
  ne se déclenchent jamais parce que le cas ne se présente pas — elles ne sont
  pas cassées.
- **L'écart `etc.` contre `…` n'existe pas.** Les 542+542 occurrences de
  `Through organizations (…)` / `Via des structures (…)` correspondent
  exactement au référentiel, ponctuation comprise.
- **Il n'y a jamais d'identifiant d'organisation vide, ni de source tierce sans
  type**, dans aucune des 2 154 fiches. Le code prévoit ces cas ; les données ne
  les produisent pas.
- **La sortie du pipeline est reproductible d'une machine à l'autre.** Vérifié :
  référence gelée sous Windows/Python 3.14, rejouée à l'identique sous
  Linux/Python 3.11.
