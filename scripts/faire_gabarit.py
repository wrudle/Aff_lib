#!/usr/bin/env python3
"""Génère glanage/gabarit_glanage.xlsx (modèle de saisie des panneaux).

Sécurité : si le gabarit existe déjà ET contient des données de glanage
(au moins une longitude saisie), il n'est PAS écrasé, sauf avec --forcer.
"""
import argparse
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RACINE = Path(__file__).resolve().parent.parent

GRISE = Font(name="Arial", size=11, color="303030")
TITRE = Font(name="Arial", size=20, color="303030")
SOUS_TITRE = Font(name="Arial", size=11, color="626262", italic=True)
ENTETE = Font(name="Arial", size=11, color="FFFFFF", bold=True)
SAISIE = Font(name="Arial", size=11, color="1F4E79")
FOND_ENTETE = PatternFill("solid", fgColor="303030")
FOND_SAISIE = PatternFill("solid", fgColor="FFF2CC")
BORD_FIN = Side(style="thin", color="C9C9C9")
BORD_FORT = Side(style="thick", color="FA500F")


def contient_glanage(chemin: Path) -> bool:
    """Vrai si le classeur contient au moins une ligne de glanage saisie."""
    wb = load_workbook(chemin, read_only=True)
    if "Waypoints" not in wb.sheetnames:
        return False
    ws = wb["Waypoints"]
    col_lon = None
    for row in ws.iter_rows(min_row=1, max_row=10):
        for cell in row:
            if cell.value is not None and str(cell.value).strip() == "Longitude":
                col_lon = cell.column
    if col_lon is None:
        return False
    for row in ws.iter_rows(min_row=1):
        c = row[col_lon - 1] if len(row) >= col_lon else None
        if c is not None and isinstance(c.value, (int, float)):
            return True
    return False


def construire(wb: Workbook):
    # ---------------- Feuille 1 : Waypoints ----------------
    ws = wb.active
    ws.title = "Waypoints"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    colonnes = [
        ("B", "ID_Waypoint", 14), ("C", "Code_INSEE", 15), ("D", "Nom_Waypoint", 32),
        ("E", "Description", 52), ("F", "Longitude", 12), ("G", "Latitude", 12),
        ("H", "Remarques", 46),
    ]
    ws["B2"] = "Glanage des panneaux d'affichage libre"
    ws["B2"].font = TITRE
    ws.row_dimensions[2].height = 28
    ws["B3"] = ("Une ligne = un panneau. Le code INSEE est choisi dans la liste "
                "déroulante (feuille Communes). Ne saisissez rien d'autre que des "
                "lignes de données.")
    ws["B3"].font = SOUS_TITRE
    ws["B4"].border = Border(bottom=BORD_FORT)
    ws["B4"] = ""
    for col, titre, largeur in colonnes:
        c = ws[f"{col}5"]
        c.value = titre
        c.font = ENTETE
        c.fill = FOND_ENTETE
        c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[col].width = largeur
    ws.row_dimensions[5].height = 22
    for col in "BCDEFGH":
        for ligne in range(6, 206):
            cell = ws[f"{col}{ligne}"]
            cell.font = SAISIE
            cell.border = Border(bottom=BORD_FIN)
            if col in "CDEFGH":
                cell.fill = FOND_SAISIE
    ws.freeze_panes = "B6"

    # Ligne d'exemple volontairement incomplète (coordonnées vides => ignorée par le script)
    ws["B6"] = "EX-0001"
    ws["C6"] = "38185"
    ws["D6"] = "Panneau mairie - EXEMPLE"
    ws["E6"] = "Face à l'entrée principale, à gauche du plot béton"
    ws["F6"] = None
    ws["G6"] = None
    ws["H6"] = "Remplacez ou effacez cette ligne d'exemple"

    dv = DataValidation(type="list", formula1="=Communes!$B$6:$B$517", allow_blank=True)
    dv.error = "Choisissez un code INSEE présent dans la feuille Communes."
    dv.prompt = "Code INSEE de la commune"
    ws.add_data_validation(dv)
    dv.add("C6:C205")

    # ---------------- Feuille 2 : Communes ----------------
    cs = json.loads((RACINE / "data" / "communes.json").read_text(encoding="utf-8"))
    wc = wb.create_sheet("Communes")
    wc.sheet_view.showGridLines = False
    wc.column_dimensions["A"].width = 2
    wc["B2"] = "Référentiel des communes de l'Isère"
    wc["B2"].font = TITRE
    wc.row_dimensions[2].height = 28
    wc["B3"] = "Données générées par scripts/construire.py : ne pas modifier ici."
    wc["B3"].font = SOUS_TITRE
    entetes = ["Code_INSEE", "Nom", "Canton", "Intercommunalité",
               "Circonscription", "Code postal"]
    for j, h in enumerate(entetes, start=2):
        c = wc.cell(row=5, column=j, value=h)
        c.font = ENTETE
        c.fill = FOND_ENTETE
    for i, c in enumerate(sorted(cs, key=lambda x: x["nom"]), start=6):
        vals = [c["code"], c["nom"], c["canton"], c["intercommunalite"],
                f"{c['circonscription']['code']:02d}", c["code_postal"]]
        for j, v in enumerate(vals, start=2):
            cell = wc.cell(row=i, column=j, value=v)
            cell.font = GRISE
    for j, largeur in enumerate([15, 32, 24, 46, 18, 16], start=2):
        wc.column_dimensions[get_column_letter(j)].width = largeur
    wc.freeze_panes = "B6"

    # ---------------- Feuille 3 : Lisez-moi ----------------
    wl = wb.create_sheet("Lisez-moi")
    wl.sheet_view.showGridLines = False
    wl.column_dimensions["A"].width = 2
    wl.column_dimensions["B"].width = 110
    wl["B2"] = "Mode d'emploi du glanage"
    wl["B2"].font = TITRE
    wl.row_dimensions[2].height = 28
    wl["B3"].border = Border(bottom=BORD_FORT)
    textes = [
        "1. Une ligne = un panneau d'affichage libre. Renseignez toutes les colonnes jaunes.",
        "2. Le Code_INSEE se choisit via la liste déroulante (feuille Communes).",
        "3. Longitude et Latitude : format décimal WGS84 (celui d'OpenStreetMap ou de votre GPS).",
        "   Astuce : sur OpenStreetMap, clic droit sur le panneau puis « Afficher l'adresse »,",
        "   les coordonnées sont dans l'URL. Mettez la longitude en F et la latitude en G.",
        "4. ID_Waypoint : libre, unique par ligne (ex. 38001-1, ou le nom du panneau).",
        "5. Enregistrez le classeur puis poussez-le dans glanage/ sur GitHub :",
        "   l'action intégrera le glanage (refus de tout code inconnu ou point hors Isère),",
        "   régénèrera data/panneaux.geojson et data/by_zone/, et uMap + l'app se",
        "   mettront à jour toutes seules au prochain affichage.",
    ]
    for i, t in enumerate(textes, start=5):
        c = wl.cell(row=i, column=2, value=t)
        c.font = GRISE
    wl.cell(row=6 + len(textes), column=2,
            value=f"Nombre de communes dans le référentiel : {len(cs)}").font = GRISE
    return len(cs)


def main():
    p = argparse.ArgumentParser(description="Génère le gabarit de glanage")
    p.add_argument("--forcer", action="store_true",
                   help="Écraser un gabarit contenant déjà du glanage")
    args = p.parse_args()

    sorti = RACINE / "glanage" / "gabarit_glanage.xlsx"
    if sorti.exists() and not args.forcer and contient_glanage(sorti):
        print("Gabarit NON régénéré : il contient du glanage "
              "(utilisez --forcer pour écraser).")
        return

    wb = Workbook()
    nb = construire(wb)
    sorti.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sorti)
    print(f"Gabarit écrit : {sorti} ({nb} communes de référence)")


if __name__ == "__main__":
    main()
