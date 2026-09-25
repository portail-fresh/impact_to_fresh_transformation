# Journal des changements de sortie

**Pour qui** : quiconque consomme ce que produit le pipeline — en premier lieu le
mapping FReSH → HealthDCAT-AP, construit sur la sortie de la branche `main`.

**Ce qu'on y trouve** : pour chaque commit qui modifie ce que le pipeline
**produit**, ce qui change, sur combien de fiches, et ce qu'un consommateur doit
vérifier de son côté. Les commits qui ne touchent que les outils d'analyse
(`tests/`) ou la documentation n'y figurent pas : ils ne changent rien à la
sortie.

**Pourquoi ce document existe** : sans lui, la discussion de fusion se résume à
« la sortie a changé, à toi de voir ». Avec lui, chaque impact se vérifie en
quelques minutes.

Point de départ de la comparaison : `main` au commit `f7e61c7` (« run 10/09/26 »).

---

## `40defd2` — deux défauts qui rendaient 12 fiches non conformes

| | |
|---|---|
| **XML produit** | modifié, sur 12 fiches |
| **fiches conformes au XSD** | 2141 → 2153 sur 2154 |

**Ce qui change.**

1. *Ordre dans `ThirdPartySource`* — 4 fiches (FRESH-PEF3101 et FRESH-PEF3162,
   fr et en). `SourceType` passe **après** `SourceName`. Contenu identique, seul
   l'ordre des éléments change.

2. *Nœuds réduits à une URI nue* — 8 fiches (FRESH-PEF152, PEF3988, PEF5440,
   PEF8142, fr et en). Un nœud comme
   `<Pathology><URI>100000000000000005366162204393472</URI></Pathology>` est
   **supprimé**. Il n'avait pas de libellé, et son identifiant n'était pas un
   code CIM-11 valide.

**À vérifier côté consommateur.** Si le mapping HealthDCAT lit les URI des
pathologies, ces 8 URI orphelines disparaissent. Elles ne désignaient rien : leur
disparition ne devrait rien casser, mais il faut le savoir.

---

## `ea816e4` — sortie indépendante du système d'exploitation

| | |
|---|---|
| **XML produit** | modifié octet par octet sur **toutes** les fiches, identique au sens XML |

**Ce qui change.** Les fichiers sont écrits avec des fins de ligne Unix (`\n`)
quel que soit le système, au lieu de fins de ligne Windows (`\r\n`) sous
Windows. Les retours chariot présents dans les champs de texte libre de la source
ne sont plus doublés.

**Pourquoi.** Le même corpus donnait deux sorties différentes selon la machine
qui lançait le pipeline.

**À vérifier côté consommateur.**
- Tout lecteur XML (lxml, ElementTree, un moteur RDF) **ne voit aucune
  différence** : la norme XML normalise les fins de ligne à la lecture.
- En revanche **tout outil qui compare des fichiers, calcule des empreintes ou
  fait des diff textuels verra toutes les fiches changer d'un coup.** Ce n'est
  pas une régression.
- Dans les textes libres (résumés, critères), un saut de ligne vide
  intermédiaire disparaît là où la source portait un retour chariot encodé.

---

## `afeadfe` — rapport qualité par fiche

| | |
|---|---|
| **XML produit** | **inchangé** |
| **journaux** | un fichier de plus par fiche |

**Ce qui change.** Dans le dossier des journaux, chaque fiche produit désormais
`<nom>_quality_report.csv` (colonnes `code, element, detail`), qui liste ce que
le pipeline a dû réparer faute de mieux : contributeur inventé, membre d'équipe
vide supprimé, terme sans libellé abandonné.

**À vérifier côté consommateur.** Rien, sauf si un script parcourt le dossier des
journaux en s'attendant à exactement deux fichiers par fiche.

---

## `c74f990` — lanceur par lot utilisable sans l'éditer

| | |
|---|---|
| **XML produit** | **inchangé** |
| **façon de lancer** | modifiée |

**Ce qui change.** `run_pipeline_batch.py` avait ses chemins écrits en dur vers
un poste particulier. Il prend maintenant des options :

```
python run_pipeline_batch.py                                   # dossiers du dépôt
python run_pipeline_batch.py --data-dir ... --output-dir ... --logs-dir ...
python run_pipeline_batch.py --study-ids 43597 PEF3476
```

**À vérifier côté consommateur.** Quiconque lançait le lot avec ses propres
chemins doit désormais les passer en option plutôt que d'éditer le fichier.

---

## Cas 3 de l'arbitrage — `CollectionModeDetails` enfin rempli

| | |
|---|---|
| **XML produit** | modifié : un élément **ajouté**, rien de retiré |
| **fiches concernées** | 15 sur les 21 fiches de test (proportion du corpus à mesurer) |
| **conformité XSD** | inchangée |

**Ce qui change.** Dans `DataCollection/CollectionProcess`, un élément
`<CollectionModeDetails>` apparaît entre `CollectionMode` et `SamplingMode`,
avec le texte libre de la source `additional/collectionProcess/collectionModeDetails`
— souvent un paragraphe entier décrivant la procédure de collecte de l'étude.

**Pourquoi.** Le champ source et l'élément du XSD portent le même nom ; aucune
règle ne les reliait. Trouvé par `tests/couverture_source.py`.

**Changement associé dans le builder.** `CollectionProcess` est désormais re-trié
explicitement à l'étape 11. Jusqu'ici l'ordre de ses enfants dépendait de l'ordre
des lignes dans la table de mapping : ajouter une règle au mauvais endroit du CSV
aurait suffi à rendre des fiches invalides.

**À vérifier côté consommateur.** Un nouvel élément de texte libre. Rien ne
disparaît ni ne change de place.

---

## Cas 4 de l'arbitrage — `RecruitmentSourceOther` enfin rempli

| | |
|---|---|
| **XML produit** | modifié : un élément **ajouté**, rien de retiré |
| **fiches concernées** | 2 sur les 21 fiches de test (FRESH-PEF3101, fr et en) |
| **conformité XSD** | inchangée |

**Ce qui change.** Dans `DataCollection`, un élément `<RecruitmentSourceOther>`
apparaît juste après `RecruitmentSource`, avec le texte libre de la source
`additional/dataCollection/recruitmentSourceOther`.

**Pourquoi.** Même motif que le cas 3 : champ du même nom dans la source et le
XSD, aucune règle entre les deux.

**À vérifier côté consommateur.** Un nouvel élément de texte libre, rare. Rien ne
disparaît ni ne change de place.

---

## Cas 6 de l'arbitrage — `CommitteeDetail` enfin rempli

| | |
|---|---|
| **XML produit** | modifié : un élément **ajouté**, rien de retiré |
| **fiches concernées** | 6 sur 21 fiches de test ; 10 sur le corpus complet |
| **conformité XSD** | inchangée |

**Ce qui change.** Dans `OrganisationGovernance/Governance`, un élément
`<CommitteeDetail>` apparaît juste après `<Committee>` : « Comité de pilotage »,
« Steering Committee », « Le comité institutionnel réunit les partenaires
fondateurs… ».

**Pourquoi.** La règle voisine lisait `standards/standard/governance` ; son jumeau
`standards/standard/committee` n'était relié à rien. Dans toutes les fiches de
test concernées, le booléen `Committee` vaut 1 et un seul comité est décrit —
cohérent avec le schéma, qui n'en accepte qu'un.

**Prérequis.** Ce champ n'était reliable qu'après `fbf88c4` : l'ancien test
booléen par sous-chaîne aurait remplacé ce texte par 0 ou 1.

---

## Cas 7 de l'arbitrage — trois champs « Autre, précisions » enfin remplis

| | |
|---|---|
| **XML produit** | modifié : éléments **ajoutés**, rien de retiré |
| **fiches concernées** | aucune des 21 fiches de test ; 2 à 4 fiches par champ sur le corpus |
| **conformité XSD** | inchangée sur les fiches de test, vérifiée conforme sur une fiche injectée |

**Ce qui change.**
- `CollectionProcess/CollectionModeOther` ← `additional/collectionProcess/collectionModeOther` (2 fiches)
- `CollectionProcess/SamplingModeOther` ← `additional/dataCollection/samplingModeOther` (4 fiches)
- `FundingAgent/OtherFundingAgentType` ← `additional/fundingAgent/otherFundingAgentType` (2 fiches),
  rattaché **au financeur de même rang** et placé après son `FundingAgentType`.

**Changement associé dans le code — sans effet sur la sortie existante.** La liste
des champs appariés par position existait en **deux copies**, l'une dans
`run_pipeline.py` (extraction), l'autre écrite en dur dans `builder.py`
(construction). En ajoutant le nouveau champ à une seule des deux, la précision
se retrouvait rattachée au **premier** financeur au lieu du bon. Il n'y a plus
qu'une liste, dans `src/builder.py`, que `run_pipeline.py` importe.

**Comment c'est vérifié.** Aucune fiche de test ne contient ces champs. La
vérification a été faite sur une copie de FRESH-PEF3101 où la précision a été
placée dans la case du 4ᵉ financeur sur 7 : elle arrive bien sur le 4ᵉ. **Les
vraies fiches concernées doivent encore être ajoutées aux tests** pour que le
harnais couvre ces champs durablement.

**À vérifier côté consommateur.** Trois éléments de texte libre, rares.

---

## À venir

Les corrections de mapping en attente de décision sont décrites dans
`arbitrage_mapping.md`. Chacune, une fois appliquée, fera l'objet d'une entrée
ici. Les deux qui modifieront le plus la sortie :

- **les noms de personnes** — `Gianluca;SEVERI` deviendrait `Gianluca SEVERI`,
  sur pratiquement toutes les fiches ;
- **`Provenance`** — un élément nouveau apparaîtrait dans toutes les fiches.
