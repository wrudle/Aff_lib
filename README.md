# Panneaux d'affichage libre — Isère

Outil de cartographie des panneaux d'affichage libre (« affichage libre » / AL)
des 512 communes de l'Isère, avec sélection par canton, intercommunalité,
arrondissement ou circonscription législative, et préparation de tournées.

Trois briques qui lisent **la même source de données** (dossier `data/`) :

1. **uMap** : la carte partagée, mise à jour automatiquement via « données
   distantes ».
2. **L'application web** (`index.html`) : filtres, sélection de communes,
   tournées, exports GPX / CSV / GeoJSON.
3. **Le glanage** (classeur Excel) : la saisie terrain des panneaux.

## Structure du dépôt

```
data/                          DONNÉES GÉNÉRÉES (ne pas modifier à la main)
  communes.json                 512 communes : zones, population, BAL, centre
  communes_contours.geojson     polygones des communes (500*, pas 512 : voir notes)
  circonscriptions_contours.geojson
  zones.json                    zones avec listes de communes et totaux
  panneaux.geojson              TOUS les panneaux glanés (source pour uMap + app)
  by_zone/                      panneaux découpés par zone (arro/cant/interco/circ)
glanage/
  gabarit_glanage.xlsx          modèle de saisie (une ligne = un panneau)
scripts/
  construire.py                 referentiel → data/ ; panneaux → data/
  faire_gabarit.py              (re)génère le gabarit depuis data/communes.json
*.xlsx (racine)                 LE fichier Excel d'origine des communes
```

Les sources officielles (centres de communes via geo.api.gouv.fr, contours des
circonscriptions via data.gouv.fr) sont **téléchargées automatiquement** par
`construire.py` la première fois (caches non commités, voir `.gitignore`).

## Première mise en place

1. Déposer le fichier Excel des communes **à la racine du dépôt**
   (glisser-déposer sur la page GitHub fonctionne ; n'importe quel nom).
2. Pousser un changement quelconque dans `glanage/`, `scripts/` ou la racine :
   l'action GitHub (`.github/workflows/construire.yml`) reconstruit TOUT
   (référentiel → panneaux → gabarit) et committe les fichiers `data/`.
   Aucun secret à créer : elle utilise le GITHUB_TOKEN intégré.

## Workflow du glanage

1. Récupérer `glanage/gabarit_glanage.xlsx` (télécharger depuis GitHub),
   feuille **Waypoints**.
2. Une ligne = un panneau : code INSEE (liste déroulante), nom, description,
   **Longitude**, **Latitude** (format décimal WGS84, ex. `5.731`, `45.1876` —
   sur OpenStreetMap, clic droit sur le panneau puis « Afficher l'adresse »
   donne les coordonnées).
3. Enregistrer, puis committer/pousser le classeur (remplacer le fichier dans
   `glanage/`) : l'action GitHub intégre le glanage automatiquement.
   En local, la même opération :
   ```bash
   python scripts/construire.py panneaux --excel glanage/gabarit_glanage.xlsx
   ```
   Le script **refuse** tout code INSEE inconnu ou point hors de l'Isère.
4. uMap et l'application affichent les nouveaux panneaux au rechargement.

## Déploiement sur Vercel

1. Sur vercel.com : « Add New » → « Project » → choisir le dépôt → **Deploy**
   (framework : Other, aucune commande de build).
2. URL finale : `https://<projet>.vercel.app`. `vercel.json` ajoute
   `X-Robots-Tag: noindex` (le site reste accessible **par lien seulement**,
   mais sort des moteurs de recherche) et autorise le CORS (nécessaire à uMap).
3. Chaque push redéploie automatiquement.

## Configuration uMap

Créer la carte principale sur umap.openstreetmap.fr :

1. Créer une carte → « Qui peut voir » : toute personne avec le lien ;
   « Qui peut modifier » : propriétaire seul (garder le lien d'édition secret).
2. Ajouter un calque « Panneaux » → propriétés du calque → **Données distantes** :
   - URL : `https://<projet>.vercel.app/data/panneaux.geojson`
   - Format : geojson · **Utiliser un proxy** : oui · Type « toujours utiliser les
     données distantes »
3. (Optionnel) calque « Communes » avec `data/communes_contours.geojson`
   en données distantes, style discret.
4. Chaque push du glanage met à jour la carte au rechargement, sans action manuelle.

Depuis l'application, les boutons **« Ouvrir uMap »** créent aussi une carte neuve
pré-remplie avec les panneaux d'une zone (fichiers `data/by_zone/...`).

## Le référentiel

```bash
python scripts/construire.py referentiel --excel "votre_fichier_communes.xlsx"
```

Régénère `communes.json`, `zones.json` et les contours. La colonne **Bal** du
fichier source (nombre de **boîtes aux lettres**) est conservée dans
`boites_aux_lettres`.

### Notes de qualité des données

- **Circonscriptions législatives** : rattachement calculé à partir des
  contours officiels (data.gouv.fr), vérifié sur les communes emblématiques.
- **Communes à cheval sur plusieurs circonscriptions** (5 connues) : elles
  apparaissent dans chaque circonscription touchée dans `zones.json`, avec la
  plus grande partie comme valeur principale dans `communes.json`
  (badge ⇄ dans l'application) :
  Grenoble (1/3), Bourgoin-Jallieu (6/10), Chamrousse (2/5),
  Villages du Lac de Paladru (5/7), Saint-Pierre-de-Chartreuse (1/5).
- **12 communes nouvelles n'ont pas de polygone** dans le fichier source
  (Grenoble, Le Haut-Bréda, communes fusionnées récentes...) : elles
  fonctionnent pour les panneaux et les listes, mais ne se dessinent pas sur
  la carte. Le fichier géographique d'origine devra être complété un jour.
- La population des communes éclatées est comptée dans chaque circonscription
  qu'elles touchent (les totaux des circonscriptions se chevauchent donc
  légèrement) ; la population totale du département reste exacte (1 134 991).

## Confidentialité

Les panneaux d'affichage libre sont des supports d'affichage publics ; les
données ne contiennent rien de personnel. Conformément au choix « par lien
seulement » : site dépublié des moteurs de recherche, carte uMap non référencée,
lien d'édition gardé secret.
