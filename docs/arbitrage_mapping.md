# Arbitrage : défauts de mapping détectés

**Ce qu'on vous demande** : trancher la case « décision » de chaque cas. Le
code suit ensuite, un commit par cas, avec le harnais pour montrer exactement
ce qui change.

**Ce que ce document n'est pas** : la liste des vocabulaires non résolus
(voir `arbitrage_vocabulaires.md`). Ici il s'agit du **pipeline lui-même** —
une règle qui lit le mauvais champ, ou un champ que personne ne lit.

## Comment ces cas ont été trouvés

Par `tests/couverture_source.py`, qui part de la fiche source et demande, pour
chaque champ rempli, si une règle de la table le lit. C'est la classe de défaut
qui revient dans l'historique du dépôt (`fix OtherDocumentation bug`, `fix id
bug`…) : une règle qui pointe vers un chemin faux mais existant passe pour
vivante, pendant que le vrai champ, lui, n'est lu par personne.

**Tout ce qui suit est mesuré sur les 21 fiches de `tests/fixtures/`.** Les
proportions sont donc indicatives. La commande qui donne les chiffres du
catalogue complet :

```
python tests/couverture_source.py --data-dir data/input --exemples 3 > couverture.txt
```

Chaque cas a été vérifié par trois voies : aucune règle ne le cible, aucune
sortie produite ne le contient, et le contenu source a été lu à la main.

---

## Cas 1 — Les noms de personnes sont lus dans le mauvais champ

**Constat.** Quatre règles lisent `./name`, qui vaut `Prénom;NOM` :

| ligne | cible | branche source |
|---|---|---|
| 67 | `PIName` | `study_desc/authoring_entity/item` |
| 82 | `TeamMemberName` | `study_desc/oth_id/item[type='contributor']` |
| 94 | `ContactName` | `study_desc/distribution_statement/contact/item` |
| 259 | `DIContactName` | `study_desc/data_access/dataset_use/contact/item` |

Or **les quatre branches fournissent aussi le prénom et le nom séparés** :

```xml
<name>Gianluca;SEVERI</name>          ← ce que la règle lit
<firstname>Gianluca</firstname>       ← ignoré
<lastname>SEVERI</lastname>           ← ignoré
```

Résultat : 100 % des noms de personnes sortent en `Gianluca;SEVERI`, alors que
le XSD documente explicitement le format attendu — *« Prénom NOM du contact »*.
Le champ est typé `xsd:string`, donc la validation passe : c'est un défaut
qu'aucun schéma ne peut attraper.

`ContributorName` n'est pas concerné : il vient de `doc_desc/producers/producer/name`,
déjà au bon format.

**Correction proposée.** Lire `firstname` et `lastname` et les joindre par une
espace. Pas de remplacement du point-virgule dans la chaîne collée : on
utiliserait une donnée dégradée alors que la source fournit la donnée propre.

Effet de bord favorable : le « membre d'équipe fantôme » (`<name>;</name>`,
prénom et nom vides), aujourd'hui détecté par une expression régulière à
l'étape 0 du builder, deviendrait naturellement un nom vide.

**Coût.** Plus qu'une ligne de table : le moteur de mapping associe **une**
source à **une** cible, et il faut ici en combiner deux. Petite modification de
code, pas un simple changement de CSV.

**Ce qui change en sortie.** Tous les noms de personnes, sur pratiquement toutes
les fiches. `Gianluca;SEVERI` → `Gianluca SEVERI`.

**Confiance.** Élevée. La structure est identique dans les quatre branches, et
aucune des 87 valeurs observées ne contient autre chose qu'un point-virgule
unique entre prénom et nom.

> **Décision** : ☐ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 2 — `Provenance` n'est jamais rempli

**Constat.** Tout est en place, sauf le branchement :

- l'élément `Provenance` existe dans le XSD (`TechnicalInfo`, optionnel) ;
- **un vocabulaire lui est dédié**, `mappings/vocabularies/Provenance.csv`,
  avec trois termes : PEF, Clinical Trials, FReSH ;
- le builder connaît sa place (il figure dans `schema_hierarchy`) ;
- la source porte l'information dans `additional/prodPlace/values`.

**Aucune règle ne relie la source à la cible.** `Provenance` est vide dans
21 fiches sur 21. Le champ étant optionnel, le XSD n'a jamais rien signalé.

| source (`additional/prodPlace`) | fiches |
|---|---|
| Epidemiology France Portal (PEF) | 11 |
| Portail Epidémiologie France (PEF) | 8 |
| France Recherche en Santé Humaine (FReSH) | 2 |

**Correction proposée.** Une règle, plus trois alias : les libellés source et
référentiel sont **inversés** — « Portail Epidémiologie France (PEF) » d'un
côté, « PEF (Portail Epidémiologie France) » de l'autre. Sans les alias, la
valeur sortirait sans identifiant.

**Ce qui change en sortie.** Un élément `Provenance` apparaît dans toutes les
fiches.

**Intérêt au-delà du bug.** Chaque fiche porterait son origine. C'est ce qui
permettrait de répondre à la question laissée ouverte dans
`pistes_ouvertes.md` : le passif de vocabulaire est-il propre aux fiches
importées de PEF ?

**Point d'attention pour l'implémentation.** L'étape 11 du builder re-trie
`TechnicalInfo` avec sa propre liste (`ti_order`), qui **ne contient pas
`Provenance`** — alors que `schema_hierarchy` le contient. Ajouter la règle seule
rangerait l'élément en fin de bloc, là où le XSD le refuse. Il faudra aligner les
deux listes (et au passage, `ti_order` contient `DatasetPersistentID`, absent de
`schema_hierarchy` : deux listes d'ordre pour le même élément finissent toujours
par diverger).

**Confiance.** Élevée sur le constat. **Une question de sens à confirmer** : en
DDI, `prodPlace` désigne le lieu de production de l'étude. Ici ses valeurs sont
manifestement le catalogue d'origine de la fiche — mais c'est une lecture des
données, pas une définition.

> **Décision** : ☐ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 3 — `CollectionModeDetails` n'est jamais rempli — ✅ APPLIQUÉ

*Décision : appliqué le 23 septembre. Voir `journal_des_changements.md`. Sur les
21 fiches de test : 15 gagnent l'élément, aucune ne change de conformité.*

**Constat.** Le XSD prévoit dans `CollectionProcess` un élément
`CollectionModeDetails` — *« Mode de collecte, précisions »*. La source a un
champ **du même nom**, `additional/collectionProcess/collectionModeDetails`,
rempli dans **15 fiches sur 21** avec du texte substantiel :

> « Chaque investigateur devra inclure, durant toute la période épidémique… »
>
> « Data collection makes use of the information systems in place in the… »

Aucune règle ne les relie. La description de la façon dont l'étude recueille
ses données n'arrive jamais dans FReSH.

*(Correction d'une affirmation antérieure : j'avais écrit que `CollectionProcess`
n'était mappé nulle part. C'est faux — le conteneur est bien alimenté par les
lignes 216 et 217, pour les modes de collecte et d'échantillonnage. C'est
uniquement ce champ de précisions qui manque.)*

**Correction proposée.** Une règle vers
`…/DataCollection/CollectionProcess/CollectionModeDetails`.

**Point d'attention.** Le builder n'a pas d'entrée `CollectionProcess` dans son
dictionnaire d'ordre : il range les enfants de ce conteneur par des traitements
spécifiques. L'ordre du nouvel élément devra être vérifié — le XSD le placerait
après `CollectionMode`/`CollectionModeOther` et avant `SamplingMode`. Le harnais,
avec validation, dira immédiatement si c'est faux.

**Ce qui change en sortie.** Un élément de texte libre apparaît dans environ
trois fiches sur quatre (proportion à confirmer sur le corpus).

**Confiance.** Élevée. Même nom de part et d'autre, contenu qui correspond
exactement à la documentation du XSD.

> **Décision** : ☒ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 4 — `RecruitmentSourceOther` n'est jamais rempli — ✅ APPLIQUÉ

*Décision : appliqué le 23 septembre. Voir `journal_des_changements.md`. Sur les
21 fiches de test : 2 gagnent l'élément, aucune ne change de conformité.*

**Constat.** Même motif que le cas 3. L'élément existe dans le XSD, le builder
connaît sa place, la source a un champ du même nom
(`additional/dataCollection/recruitmentSourceOther`), aucune règle.

Rempli dans **2 fiches sur 21** — l'étude familiale E3N-Générations
(FRESH-PEF3101), en français et en anglais :

> « Pour constituer cette cohorte familiale, recueil des coordonnées des
> membres… »

**Correction proposée.** Une règle vers
`…/DataCollection/RecruitmentSourceOther`.

**Ce qui change en sortie.** Rare — un élément de plus sur peu de fiches.

**Confiance.** Élevée sur le constat, faible sur l'enjeu. Le volume réel se
lira sur le corpus.

> **Décision** : ☒ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 5 — `CreationDate` porte la date d'import, pas celle du premier enregistrement

**Constat (corpus complet).** La règle ligne 7 lit `/xml/dataset/created`, qui est
l'horodatage d'entrée de la fiche dans NADA. Pour les fiches importées de PEF,
c'est la date de l'**import en masse** — le 18 février 2026 :

| fiche | lu aujourd'hui (`created`) | `additional/creationDate` (non lu) |
|---|---|---|
| FRESH-PEF152 | 2026-02-18T18:21:38 | 14-12-2010 |
| FRESH-PEF200 | 2026-02-18T18:21:52 | 20-12-2010 |
| FRESH-PEF1192 | 2026-02-18T18:21:23 | 15-02-2011 |

Or le XSD documente `CreationDate` comme **« Date du 1er enregistrement / First
record date »**. Une étude enregistrée sur PEF en 2010 affiche aujourd'hui une
création en 2026.

**Ampleur.** `additional/creationDate` est rempli dans **2132 fiches sur 2154**.
Il est absent des 22 fiches nativement créées dans FReSH, pour lesquelles
`created` est bien la vraie date.

**Correction proposée.** Lire `additional/creationDate` quand il existe, et
retomber sur `created` sinon. Deux précautions : le format source est `JJ-MM-AAAA`
(à convertir en `AAAA-MM-JJ`), et **70 occurrences valent `----`** (à traiter
comme absentes, donc repli sur `created`).

**Ce qui change en sortie.** La date de création de ~2130 fiches recule de 2026
à leur vraie date, entre 2010 et 2013 pour l'essentiel.

**Question de sens à trancher.** Est-ce que FReSH veut la date de création de la
fiche d'origine (PEF), ou la date à laquelle la fiche est entrée dans FReSH ? La
documentation du XSD dit la première. Mais c'est une décision d'équipe : elle
change ce que « récent » veut dire dans le catalogue.

> **Décision** : ☐ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 6 — `CommitteeDetail` n'est jamais rempli — ✅ APPLIQUÉ

*Décision : appliqué le 25 septembre. 6 fiches de test gagnent l'élément, conformité inchangée.*

**Constat (corpus).** Même motif que les cas 3 et 4. L'élément existe
(*« Comité, précisions »*), la source `study_desc/study_info/quality_statement/standards/standard/committee`
est remplie dans **10 fiches**, aucune règle :

> « Steering Committee », « Comité de pilotage », « The Institutional Committee
> brings together the founding partners… »

**Déjà sécurisé.** C'est précisément le champ que le test booléen par
sous-chaîne aurait écrasé en `0`/`1` (« CommitteeDetail » contient
« Committee »). Le piège a été désamorcé au commit `fbf88c4`, la règle peut
être ajoutée sans risque.

> **Décision** : ☒ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Cas 7 — Trois champs « Autre, précisions » jamais remplis — ✅ APPLIQUÉ

*Décision : appliqué le 25 septembre. Aucune fiche de test ne les contient : vérifié sur une fiche injectée ; les vraies fiches restent à ajouter aux tests.*

**Constat (corpus).** Même motif, trois champs rares :

| source (`additional/…`) | cible XSD | fiches |
|---|---|---|
| `dataCollection/samplingModeOther` | `SamplingModeOther` | 4 |
| `collectionProcess/collectionModeOther` | `CollectionModeOther` | 2 |
| `fundingAgent/otherFundingAgentType/otherfundingagenttype` | `OtherFundingAgentType` | 2 (4 occurrences) |

Exemples : « Invitation totalité population éligible », « Données
administratives, SNDS », « Organisme protection sociale ».

**Point d'attention.** `OtherFundingAgentType` appartient à un financeur précis :
la source range les financeurs et leurs types dans des listes parallèles,
appariées par position (étape 2.5 du builder). La précision devra suivre le même
appariement, sinon elle serait rattachée au mauvais financeur. Les deux autres
sont de simples règles, et `CollectionProcess` est déjà re-trié depuis le cas 3.

> **Décision** : ☒ appliquer ☐ ne pas appliquer ☐ à revoir

---

## Ce que le corpus complet a appris

**Le catalogue est presque entièrement issu de l'import PEF.**
`additional/prodPlace` vaut « Portail Epidémiologie France (PEF) » dans 2150
fiches sur 2154, soit **1075 études sur 1077**. La question « le passif de
vocabulaire est-il propre aux fiches importées ? » (`pistes_ouvertes.md`) perd
donc beaucoup de son sens : à ce stade, le catalogue *est* l'import PEF.

**Le cas 1 touche ~2070 fiches** : `authoring_entity` (investigateurs) est rempli
dans 2068 fiches, `distribution_statement/contact` dans 1890.

**Restent à examiner, sans conclusion pour l'instant :**
- `study_info/universe` (2154 fiches) : un bloc JSON des critères de sexe et d'âge,
  avec leurs URI MeSH. Probablement un doublon, sous une autre forme, de `Sex` et
  `Age` — à vérifier, notamment si les URI MeSH y sont les seules disponibles ;
- `additional/avlStatus` (2154 fiches) : « Accès réservé », « To be defined »… un
  statut de disponibilité des données dont le rapport avec `IndividualDataAccess`
  reste à établir ;
- `additional/contributorName` : identique au contributeur lu dans 452 fiches sur
  556, **différent dans 104**. À regarder de près.

---

## Écartés après vérification

Pour que personne ne les redécouvre et ne perde de temps dessus. Chacun avait été
signalé par une première version du détecteur.

**La famille `additional/*/values`** (`dataKind`, `trialPhase`, `geogCoverage`,
`populationType`, `sourceOrigine`…). Ce sont des résumés d'affichage de champs
structurés déjà mappés ailleurs : `dataKind` vaut « Clinical data » là où
`DataType` lit `['Clinical data', 'Biological data']`. Même information, autre
écriture. Le détecteur compare désormais des valeurs normalisées et les classe
correctement.

**Le drapeau `<export>` de cette famille.** Il vaut 0 dans 483 cas sur 483, fiches
natives comprises. Un drapeau qui a toujours la même valeur ne discrimine rien :
il ne permet pas de conclure que ces champs sont « à ne pas exporter ».

**`piLabo`** (branche `additional`). Doublon de `PILabo` (branche
`authoring_entity`), valeurs identiques quand les deux existent.

**`rareDiseases`**. La source dit « Non », FReSH sort `0`. Même information en
booléen.

**`topicsHealthTheme`** — écarté du mapping, **mais signalé à la curation**. Le
pipeline lit le bon champ (le champ structuré, plus précis). En revanche la
fiche se contredit elle-même : sur FRESH-PEF2582 et FReSH-43597, le résumé dit
« No specific medical speciality » alors que le champ structuré liste deux
spécialités. Ce n'est pas un défaut de conversion, c'est une incohérence de
saisie.

---

## Ce que le détecteur ne voit pas

Il dit si un champ source est lu, pas s'il est **rangé au bon endroit**. Une
règle qui lit le bon champ et l'écrit dans le mauvais élément FReSH passe au
travers. C'est un troisième outil, à construire une fois ces cas traités.
