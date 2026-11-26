🇫🇷 Version française | [🇬🇧 English version](product-context.md)

---

# Contexte produit - geo_data

## Concept

Les projets qui travaillent avec des territoires (pays, régions, départements) ont tous besoin des mêmes découpages administratifs, et les sources publiques les publient sous des formes, des codes et des langues différents. geo_data est un outil transverse qui centralise ces sources géographiques et les normalise une seule fois dans un schéma générique. Chaque projet consommateur, public ou privé, récupère ensuite ses données par une petite étape d'export adaptée à son propre format, au lieu de maintenir ses propres scripts de téléchargement et de nettoyage. GeoChallenge-Tracker, qui suit des challenges géocaching par zone administrative, est l'un de ces consommateurs.

## Utilisateur cible

Un développeur qui a besoin de zones administratives propres dans un projet, et qui lance le pipeline en local quand un pays est ajouté ou qu'une source change. Pas d'utilisateurs finaux, pas de service hébergé.

## Vocabulaire

| Terme | Sens |
|---|---|
| `ADM level` | Profondeur administrative : 0 pays, 1 équivalent région, 2 équivalent département |
| `feature_code` | Code brut de l'unité administrative dans la source, sans préfixe pays (ex. `84`) |
| `normalized output` | Fichiers génériques, indépendants de tout projet, `data/normalized/{cc}/adm{level}.geojson` (`feature_code`, `name`, `parent_feature_code`) |
| `export` | Étape propre à un consommateur, qui remet la sortie normalisée au format d'un projet |
| `contract` | Le schéma de sortie convenu avec un consommateur, par exemple `scripts/docs/CONTRACT.md` pour GeoChallenge-Tracker |
| `country config` | Description par pays de la source et du handler qui alimentent chaque niveau (`normalize/common/countries/`) |

## Fonctionnalités

- **Téléchargement** - archives geoBoundaries ADM0-5 par pays, tables de codes administratifs GeoNames
- **Normalisation** - un framework de jointure générique (sources, handlers, rapprochement des noms) construit la sortie normalisée ; la France joint les fichiers de codes INSEE conservés dans `data/insee/`, l'Italie promeut ses unités admin2 en régions
- **Export** - une étape par consommateur ; l'export GeoChallenge-Tracker ajoute la `bbox`, préfixe les codes (`FR-84`) et renomme les propriétés selon son contrat
- **Attribution** - suivi des sources par pays et par niveau dans `SOURCES.md` et `CREDITS.md`

## Hors périmètre

- Pas d'API, pas d'interface, pas d'exécution planifiée : un pipeline CLI local
- Pas d'écriture directe dans la base d'un consommateur : les fichiers d'export sont la seule interface
- Pas de changement de contrat sans accord du consommateur concerné
