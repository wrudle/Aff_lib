#!/usr/bin/env python3
"""
Construit les données du projet "Panneaux d'affichage libre - Isère".

Usage :
    python scripts/construire.py referentiel --excel "chemin/DONNEES COMMUNES.xlsx"
    python scripts/construire.py panneaux --excel "chemin/glanage.xlsx"

Sorties (dans data/) :
  - communes.json                 512 communes (attributs + centre)
  - communes_contours.geojson     polygones des communes
  - circonscriptions_contours.geojson (10 circonscriptions législatives)
  - zones.json                    arrondissements / cantons / intercos / circonscriptions
  - panneaux.geojson              résultat du glanage (source de vérité pour uMap et l'app)
  - by_zone/*.geojson             un fichier de panneaux par zone (pratique pour uMap)
"""

import argparse
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent  # dossier du projet
DATA = RACINE / "data"
SOURCES = RACINE / "sources"

URL_API_COMMUNES = (
    "https://geo.api.gouv.fr/communes?codeDepartement=38"
    "&fields=code,nom,codesPostaux,centre,population&format=json"
)

# Contours officiels des circonscriptions législatives (data.gouv.fr)
URL_CIRCOS_FRANCE = (
    "https://static.data.gouv.fr/resources/contours-geographiques-des-"
    "circonscriptions-legislatives/20240613-191520/"
    "circonscriptions-legislatives-p10.geojson"
)

BBOX_ISERE = (-5.6, 44.6, 7.2, 46.3)  # lon_min, lat_min, lon_max, lat_max (généreux)

# Communes officiellement à cheval sur plusieurs circonscriptions mais non
# détectées à cause de la simplification des contours (découpage officiel 2010-2015).
SPLITS_MANUELS = {
    "38185": [1, 3],   # Grenoble (Grenoble-I/II/IV -> 1re ; III/V/VI -> 3e)
    "38053": [6, 10],  # Bourgoin-Jallieu (Nord -> 6e ; Sud -> 10e)
    "38567": [2, 5],   # Chamrousse (partie canton Vizille -> 5e ; reste -> 2e)
    "38292": [5, 7],   # Villages du Lac de Paladru (Paladru -> 5e ; Le Pin -> 7e)
}


def slug(texte: str) -> str:
    """Transforme un nom de zone en identifiant de fichier propre."""
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t


def arrondis(nombre: float, dec=5):
    return round(float(nombre), dec)


def simplifie_geom(geom, dec=5):
    """Arrondit toutes les coordonnées d'une géométrie GeoJSON (lon/lat)."""
    if isinstance(geom[0], (int, float)):
        return [round(float(geom[0]), dec), round(float(geom[1]), dec)]
    return [simplifie_geom(g, dec) for g in geom]


def point_dans_anneau(x, y, anneau) -> bool:
    """Algorithme du lancer de rayon."""
    dedans = False
    n = len(anneau)
    for i in range(n):
        x1, y1 = anneau[i][0], anneau[i][1]
        x2, y2 = anneau[(i + 1) % n][0], anneau[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                dedans = not dedans
    return dedans


def point_dans_geom(x, y, geom) -> bool:
    """Teste un point contre un Polygon ou MultiPolygon (règle pair-impair)."""
    if geom["type"] == "Polygon":
        anneaux = geom["coordinates"]
        dedans = point_dans_anneau(x, y, anneaux[0])
        if not dedans:
            return False
        return not any(point_dans_anneau(x, y, a) for a in anneaux[1:])
    if geom["type"] == "MultiPolygon":
        return any(point_dans_geom(x, y, {"type": "Polygon", "coordinates": p}) for p in geom["coordinates"])
    return False


def circos_touchees(geom_test, circos, pas=25):
    """Circonscriptions touchées par une géométrie (échantillonnage des sommets)."""
    points = []

    def collecte(g):
        if isinstance(g[0], (int, float)):
            points.append((g[0], g[1]))
        else:
            for sub in g:
                collecte(sub)

    collecte(geom_test["coordinates"] if isinstance(geom_test, dict) else geom_test)
    echantillon = points[::pas] or points
    trouvees = {}
    for x, y in echantillon:
        for ci in circos:
            if ci["code"] in trouvees and trouvees[ci["code"]] >= 3:
                continue
            if point_dans_geom(x, y, ci["geometry"]):
                trouvees[ci["code"]] = trouvees.get(ci["code"], 0) + 1
                break
    return trouvees


def charge_api_communes() -> dict:
    """Centres officiels des communes (API découpage administratif), avec cache local."""
    cache = SOURCES / "api_communes_38.json"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL_API_COMMUNES, timeout=60) as rep:
            data = json.loads(rep.read().decode())
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    return json.loads(cache.read_text(encoding="utf-8"))


def charge_circos() -> dict:
    """Contours des circonscriptions législatives de l'Isère.

    Le fichier complet France (5 Mo) est téléchargé automatiquement si le
    cache local n'existe pas, puis filtré sur le département 38. Le cache
    n'est pas commité (voir .gitignore) : chaque environnement le recrée.
    """
    cache = SOURCES / "circonscriptions_38.geojson"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        print("Téléchargement des contours de circonscriptions (data.gouv.fr)…")
        with urllib.request.urlopen(URL_CIRCOS_FRANCE, timeout=240) as rep:
            france = json.loads(rep.read().decode())
        feats = [f for f in france["features"]
                 if f["properties"].get("codeDepartement") == "38"]
        if len(feats) != 10:
            raise SystemExit(f"Attendu 10 circonscriptions pour l'Isère, trouvé {len(feats)}.")
        cache.write_text(
            json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
            encoding="utf-8",
        )
    return json.loads(cache.read_text(encoding="utf-8"))


def construire_referentiel(excel: Path):
    DATA.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(excel, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    centres = {c["code"]: c["centre"]["coordinates"] for c in charge_api_communes()}

    # --- Circonscriptions législatives : rattachement géographique ---
    circos = charge_circos()
    circos_isere = []
    for f in circos["features"]:
        p = f["properties"]
        circos_isere.append({
            "code": int(p["codeCirconscription"][-2:]),
            "nom": p["nomCirconscription"],
            "geometry": f["geometry"],
        })

    communes, contours = [], []
    stats_circo = {}
    for _, r in df.iterrows():
        code = str(r["Code Insee"]).strip().zfill(5)
        nom = str(r["Nom"]).strip()
        pop_txt = re.sub(r"[^0-9]", "", str(r["Population"]))
        population = int(pop_txt or 0)
        bal = int(r["Bal"]) if pd.notna(r["Bal"]) else None
        canton = str(r["Canton"]).strip()
        interco = str(r["Intercommunalité"]).strip()
        arrond = str(r["Arrondissement"]).strip()

        centre = centres.get(code)
        circo_trouvee = None
        if centre:
            for ci in circos_isere:
                if point_dans_geom(centre[0], centre[1], ci["geometry"]):
                    circo_trouvee = ci
                    break
        if circo_trouvee is None:
            raise SystemExit(f"ATTENTION : {nom} ({code}) placée dans aucune circonscription !")

        # Détection des communes à cheval sur plusieurs circonscriptions
        # (la géométrie précise teste tous les sommets échantillonnés).
        geom = r.get("geometry")
        circos_multiples = []
        if isinstance(geom, str) and geom.strip():
            g = json.loads(geom)
            touchees = circos_touchees(g, circos_isere)
            if len(touchees) > 1:
                circos_multiples = sorted(touchees)
            # circo dominante = celle qui contient le plus de sommets
            if touchees:
                dominante = max(touchees, key=touchees.get)
                for ci in circos_isere:
                    if ci["code"] == dominante:
                        circo_trouvee = ci
        if code == "38185":
            # Grenoble : commune à cheval sur les 1re et 3e circonscriptions (pas de
            # polygone dans le fichier source), rattachement historique documenté.
            circos_multiples = [1, 3]
        if code in SPLITS_MANUELS:
            circos_multiples = SPLITS_MANUELS[code]

        communes.append({
            "code": code,
            "nom": nom,
            "code_postal": str(r["Code postal"]).strip(),
            "population": population,
            "boites_aux_lettres": bal,
            "arrondissement": arrond,
            "canton": canton,
            "intercommunalite": interco,
            "circonscription": {
                "code": circo_trouvee["code"],
                "nom": circo_trouvee["nom"],
            },
            "circonscriptions_multiples": circos_multiples,
            "centre": centre,
        })
        stats_circo.setdefault(circo_trouvee["code"], []).append(nom)

        geom = r.get("geometry")
        if isinstance(geom, str) and geom.strip():
            g = json.loads(geom)
            contours.append({
                "type": "Feature",
                "properties": {"code": code, "nom": nom},
                "geometry": {"type": g["type"], "coordinates": simplifie_geom(g["coordinates"])},
            })

    (DATA / "communes.json").write_text(
        json.dumps(communes, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "communes_contours.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "features": contours}, ensure_ascii=False), encoding="utf-8"
    )

    # Contours des circonscriptions (arrondis)
    feats = []
    for ci in circos_isere:
        feats.append({
            "type": "Feature",
            "properties": {"code": ci["code"], "nom": ci["nom"]},
            "geometry": ci["geometry"],
        })
    (DATA / "circonscriptions_contours.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- Zones ---
    def groupe(f):
        out = {}
        for c in communes:
            out.setdefault(f(c), []).append(c)
        return out

    z = lambda membres: {
        "communes": sorted(c["code"] for c in membres),
        "population": sum(c["population"] for c in membres),
        "boites_aux_lettres": sum(c["boites_aux_lettres"] or 0 for c in membres),
    }

    zones = {}
    for cle in ("arrondissement", "canton", "intercommunalite"):
        zones[cle] = [
            {"nom": nom, "slug": slug(nom), **z(membres)}
            for nom, membres in sorted(groupe(lambda c, k=cle: c[k]).items())
        ]
    # Circonscriptions : une commune éclatée sur plusieurs circo y apparaît
    # dans chacune (documenté dans le README).
    par_circo = {}
    for c in communes:
        for num in (c["circonscriptions_multiples"] or [c["circonscription"]["code"]]):
            par_circo.setdefault(num, []).append(c)
    zones["circonscription"] = [
        {
            "code": num,
            "nom": membres[0]["circonscription"]["nom"],
            "slug": f"{num:02d}",
            **z(membres),
        }
        for num, membres in sorted(par_circo.items())
    ]
    (DATA / "zones.json").write_text(
        json.dumps(zones, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Référentiel construit : {len(communes)} communes, "
          f"{len(contours)} contours, circos = "
          + ", ".join(f"{k}:{len(v)}" for k, v in sorted(stats_circo.items())))
    return communes, zones


def _groupe_circo(communes):
    out = {}
    for c in communes:
        out.setdefault(c["circonscription"]["code"], []).append(c)
    return out


def charger_zones():
    return json.loads((DATA / "zones.json").read_text(encoding="utf-8"))


def construire_panneaux(excel: Path, communes: list | None = None, zones=None):
    """Convertit le classeur de glanage en panneaux.geojson + un fichier par zone."""
    if communes is None:
        communes = json.loads((DATA / "communes.json").read_text(encoding="utf-8"))
    if zones is None:
        zones = charger_zones()
    par_code = {c["code"]: c for c in communes}

    df = pd.read_excel(excel, sheet_name="Waypoints", engine="openpyxl", header=None)
    # Trouver la vraie ligne d'en-tête (le gabarit a des lignes de titre au-dessus)
    ligne_entete = None
    for i, row in df.iterrows():
        if any(str(v).strip() == "Longitude" for v in row):
            ligne_entete = i
            break
    if ligne_entete is None:
        raise SystemExit("Feuille 'Waypoints' : colonne 'Longitude' introuvable.")
    df.columns = [str(v).strip() for v in df.iloc[ligne_entete]]
    df = df.iloc[ligne_entete + 1:].reset_index(drop=True)

    erreurs, features = [], []

    def txt(v):
        return "" if v is None or pd.isna(v) else str(v).strip()

    for i, r in df.iterrows():
        ligne = i + ligne_entete + 2  # numéro de ligne réel dans Excel
        if pd.isna(r.get("Longitude")) and pd.isna(r.get("Latitude")):
            continue  # ligne vide
        code = str(r.get("Code_INSEE", "")).strip().zfill(5)
        if pd.isna(r.get("Code_INSEE")) or code not in par_code:
            erreurs.append(f"ligne {ligne} : code INSEE '{code}' inconnu")
            continue
        try:
            lon = float(r["Longitude"])
            lat = float(r["Latitude"])
        except (TypeError, ValueError):
            erreurs.append(f"ligne {ligne} : coordonnées illisibles")
            continue
        if not (BBOX_ISERE[0] < lon < BBOX_ISERE[2] and BBOX_ISERE[1] < lat < BBOX_ISERE[3]):
            erreurs.append(f"ligne {ligne} : point hors de l'Isère ({lon}, {lat})")
            continue
        c = par_code[code]
        props = {
            "id": txt(r.get("ID_Waypoint")) or f"auto-{code}-{i}",
            "nom": txt(r.get("Nom_Waypoint")),
            "description": txt(r.get("Description")),
            "commune": c["nom"],
            "code_insee": code,
            "canton": c["canton"],
            "intercommunalite": c["intercommunalite"],
            "circonscription": c["circonscription"]["code"],
            "remarques": txt(r.get("Remarques")),
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    if erreurs:
        for e in erreurs:
            print("  ERREUR :", e)
        raise SystemExit(f"{len(erreurs)} erreur(s) dans le glanage : corrigez puis relancez.")

    fc = {"type": "FeatureCollection", "features": features}
    (DATA / "panneaux.geojson").write_text(
        json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # Un fichier par zone (pour calques uMap ciblés)
    out_dir = DATA / "by_zone"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.geojson"):
        f.unlink()
    for type_zone in ("arrondissement", "canton", "intercommunalite", "circonscription"):
        for zn in zones[type_zone]:
            codes = set(zn["communes"])
            sous = [f for f in features if f["properties"]["code_insee"] in codes]
            nom_fichier = f"{type_zone[:4]}-{zn['slug']}.geojson"
            (out_dir / nom_fichier).write_text(
                json.dumps({"type": "FeatureCollection", "features": sous}, ensure_ascii=False),
                encoding="utf-8",
            )
    print(f"Panneaux : {len(features)} intégrés, "
          f"{len(list(out_dir.glob('*.geojson')))} fichiers par zone générés.")
    return fc


def main():
    p = argparse.ArgumentParser(description="Construit les données panneaux-isere")
    p.add_argument("commande", choices=["referentiel", "panneaux"])
    p.add_argument("--excel", required=True, type=Path)
    args = p.parse_args()

    if args.commande == "referentiel":
        construire_referentiel(args.excel)
        print("Référentiel OK →", DATA)
    else:
        construire_panneaux(args.excel)


if __name__ == "__main__":
    main()
