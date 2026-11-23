/* Panneaux d'affichage libre - Isère
   Application 100% statique : lit data/*.json, aucun serveur nécessaire.
   Hébergeable tel quel sur Vercel / GitHub Pages. */

const etat = {
  communes: [],            // data/communes.json
  parCode: new Map(),
  zones: {},               // data/zones.json
  contoursParCode: new Map(), // data/communes_contours.geojson
  panneaux: [],            // data/panneaux.geojson
  panneauxParCode: new Map(), // code INSEE -> [features]
  selection: new Set(),    // codes INSEE sélectionnés
  tournee: [],             // features de panneaux, dans l'ordre
  filtreType: "",
  filtreZone: null,        // objet zone
};

const $ = (id) => document.getElementById(id);

/* ---------- Chargement ---------- */

async function charger() {
  const [communes, zones, contours, panneaux] = await Promise.all([
    fetch("data/communes.json").then(r => r.json()),
    fetch("data/zones.json").then(r => r.json()),
    fetch("data/communes_contours.geojson").then(r => r.json()),
    fetch("data/panneaux.geojson").then(r => r.json()),
  ]);
  etat.communes = communes;
  etat.communes.sort((a, b) => a.nom.localeCompare(b.nom, "fr"));
  etat.communes.forEach(c => etat.parCode.set(c.code, c));
  etat.zones = zones;
  contours.features.forEach(f => etat.contoursParCode.set(f.properties.code, f));
  etat.panneaux = panneaux.features || [];
  etat.panneaux.forEach(p => {
    const code = p.properties.code_insee;
    if (!etat.panneauxParCode.has(code)) etat.panneauxParCode.set(code, []);
    etat.panneauxParCode.get(code).push(p);
  });
  etat.tournee = JSON.parse(localStorage.getItem("tournee") || "[]");
  construireCarte();
  remplirChoixZones();
  afficherCommunes();
  afficherPanneaux();
  afficherTournee();
  majStats();
}

/* ---------- Carte ---------- */

let carte, coucheContours, coucheMarqueurs;

const iconePanneau = (dansTournee) =>
  L.divIcon({
    className: "",
    html: `<span class="${dansTournee ? "pin pin-tournee" : "pin"}">P</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });

function construireCarte() {
  carte = L.map("carte", { preferCanvas: true }).setView([45.35, 5.55], 9);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(carte);

  coucheContours = L.layerGroup().addTo(carte);
  etat.contoursParCode.forEach((f, code) => {
    const poly = L.geoJSON(f, {
      style: () => styleCommune(code),
      onEachFeature: (_, layer) => {
        layer.bindTooltip(etat.parCode.get(code).nom, { sticky: true });
        layer.on("click", () => basculerCommune(code));
      },
    });
    f.__couche = poly;
    poly.addTo(coucheContours);
  });

  coucheMarqueurs = L.layerGroup().addTo(carte);
  etat.panneaux.forEach(p => {
    const m = L.marker([p.geometry.coordinates[1], p.geometry.coordinates[0]], {
      icon: iconePanneau(estDansTournee(p)),
      title: p.properties.nom,
    });
    p.__marqueur = m;
    m.bindPopup(() => popupPanneau(p));
    m.addTo(coucheMarqueurs);
  });
}

function styleCommune(code) {
  const sel = etat.selection.has(code);
  return {
    color: sel ? "#6d4c9f" : "#b9b0c8",
    weight: sel ? 2 : 1,
    fillColor: sel ? "#9b76c9" : "#ece9f0",
    fillOpacity: sel ? 0.35 : 0.4,
  };
}

function rafraichirStyles() {
  etat.contoursParCode.forEach((f, code) =>
    f.__couche.setStyle(styleCommune(code)));
}

function popupPanneau(p) {
  const pr = p.properties;
  const dansT = estDansTournee(p);
  const ids = String(pr.id).replace(/'/g, "\\'");
  return `<b>${pr.nom || pr.id}</b><br>${pr.commune}<br>` +
    `<button class="principal" onclick="basculerPanneau('${ids}')">` +
    (dansT ? "Retirer de la tournée" : "Ajouter à la tournée") + `</button>`;
}

/* ---------- Sélection ---------- */

function basculerCommune(code) {
  if (etat.selection.has(code)) etat.selection.delete(code);
  else etat.selection.add(code);
  afficherCommunes();
  afficherPanneaux();
  rafraichirStyles();
  majStats();
}

function basculerPanneau(id) {
  const p = etat.panneaux.find(x => x.properties.id === id);
  if (!p) return;
  const i = etat.tournee.findIndex(x => x.properties.id === id);
  if (i >= 0) {
    etat.tournee.splice(i, 1);
    p.__marqueur?.setIcon(iconePanneau(false));
  } else {
    etat.tournee.push(p);
    p.__marqueur?.setIcon(iconePanneau(true));
    carte?.panTo([p.geometry.coordinates[1], p.geometry.coordinates[0]]);
  }
  sauverTournee();
  afficherTournee();
  afficherPanneaux();
  if (p.__marqueur?.isPopupOpen?.()) p.__marqueur.setPopupContent(popupPanneau(p));
}

function estDansTournee(p) {
  return etat.tournee.some(x => x.properties.id === p.properties.id);
}

function sauverTournee() {
  localStorage.setItem("tournee", JSON.stringify(
    etat.tournee.map(p => ({ geometry: p.geometry, properties: p.properties }))));
}

/* ---------- Liste des communes ---------- */

function candidats() {
  if (etat.filtreZone) {
    return etat.filtreZone.communes.map(c => etat.parCode.get(c));
  }
  const q = $("recherche").value.trim().toLowerCase();
  if (q) return etat.communes.filter(c => c.nom.toLowerCase().includes(q));
  return etat.communes;
}

function afficherCommunes() {
  const ul = $("liste-communes");
  ul.innerHTML = "";
  const cs = candidats();
  $("nb-affichees").textContent = `(${cs.length})`;
  const frag = document.createDocumentFragment();
  for (const c of cs) {
    const nbP = (etat.panneauxParCode.get(c.code) || []).length;
    const li = document.createElement("li");
    li.innerHTML =
      `<input type="checkbox" ${etat.selection.has(c.code) ? "checked" : ""}>` +
      `<span class="nom">${c.nom}` +
      (c.circonscriptions_multiples.length
        ? `<em title="Commune à cheval sur plusieurs circonscriptions">⇄</em>` : "") +
      `</span>` +
      `<span class="meta">${c.population.toLocaleString("fr")} hab` +
      (nbP ? ` · ${nbP} panneau${nbP > 1 ? "x" : ""}` : "") + `</span>`;
    li.querySelector("input").addEventListener("change", () => basculerCommune(c.code));
    li.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") basculerCommune(c.code);
    });
    frag.appendChild(li);
  }
  ul.appendChild(frag);
}

/* ---------- Liste des panneaux (des communes sélectionnées) ---------- */

function afficherPanneaux() {
  const ul = $("liste-panneaux");
  ul.innerHTML = "";
  const codes = new Set(etat.selection);
  const ps = etat.panneaux.filter(p => codes.has(p.properties.code_insee));
  $("nb-panneaux-selection").textContent = `(${ps.length})`;
  if (!ps.length) {
    ul.innerHTML = `<li class="vide">Aucun panneau pour la sélection. ` +
      `Glanez des panneaux puis relancez le script, ils apparaîtront ici.</li>`;
    return;
  }
  for (const p of ps) {
    const pr = p.properties;
    const li = document.createElement("li");
    li.className = estDansTournee(p) ? "dans-tournee" : "";
    li.innerHTML = `<span class="p-nom">${pr.nom || pr.id}</span>` +
      `<span class="p-commune">${pr.commune}${pr.description ? " · " + pr.description : ""}</span>`;
    li.addEventListener("click", () => basculerPanneau(pr.id));
    ul.appendChild(li);
  }
}

/* ---------- Tournée ---------- */

function afficherTournee() {
  const ol = $("liste-tournee");
  ol.innerHTML = "";
  if (!etat.tournee.length) {
    ol.innerHTML = `<li class="vide">(vide)</li>`;
    return;
  }
  etat.tournee.forEach((p, i) => {
    const pr = p.properties;
    const li = document.createElement("li");
    li.innerHTML = `<span class="t-info">${i + 1}.</span> ${pr.commune} — ` +
      `${pr.nom || pr.id} ` +
      `<button title="Retirer">✕</button>`;
    li.querySelector("button").addEventListener("click", () => basculerPanneau(pr.id));
    ol.appendChild(li);
  });
}

/* ---------- Exports ---------- */

function telecharger(nom, contenu, type) {
  const blob = new Blob([contenu], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nom;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exporterGPX() {
  const echap = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const wpts = etat.tournee.map((p, i) => {
    const [lon, lat] = p.geometry.coordinates;
    const pr = p.properties;
    return `  <wpt lat="${lat}" lon="${lon}">` +
      `<name>${i + 1}. ${echap(pr.nom || pr.id)}</name>` +
      `<desc>${echap(`${pr.commune}. ${pr.description || ""} ${pr.remarques || ""}`)}</desc>` +
      `</wpt>`;
  }).join("\n");
  const gpx = `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<gpx version="1.1" creator="panneaux-isere">\n${wpts}\n</gpx>`;
  telecharger("tournee.gpx", gpx, "application/gpx+xml");
}

function exporterCSV() {
  const lignes = [["ordre", "id", "commune", "nom", "description", "longitude", "latitude", "remarques"]];
  etat.tournee.forEach((p, i) => {
    const pr = p.properties;
    lignes.push([i + 1, pr.id, pr.commune, pr.nom, pr.description || "",
      p.geometry.coordinates[0], p.geometry.coordinates[1], pr.remarques || ""]);
  });
  const csv = lignes.map(l => l.map(v => `"${String(v).replace(/"/g, '""')}"`).join(";")).join("\n");
  telecharger("tournee.csv", "\ufeff" + csv, "text/csv");
}

function exporterGeoJSON() {
  const fc = {
    type: "FeatureCollection",
    features: etat.tournee.map(p => ({ type: "Feature", geometry: p.geometry, properties: p.properties })),
  };
  telecharger("tournee.geojson", JSON.stringify(fc, null, 1), "application/geo+json");
}

/* ---------- uMap ---------- */

function lienNouvelleCarte(url, nom) {
  const p = new URLSearchParams({
    dataUrl: url,
    dataName: nom,
    dataLat: "45.3",
    dataLon: "5.55",
    dataZoom: "9",
  });
  return `https://umap.openstreetmap.fr/fr/map/new/?${p.toString()}`;
}

function ouvrirUMapZone() {
  if (!etat.filtreZone) return;
  const prefix = { arrondissement: "arro", canton: "cant", intercommunalite: "inte", circonscription: "circ" }[etat.filtreType];
  const url = new URL(`data/by_zone/${prefix}-${etat.filtreZone.slug}.geojson`, location.href);
  window.open(lienNouvelleCarte(url.toString(), etat.filtreZone.nom), "_blank");
}

function ouvrirUMapTout() {
  const url = new URL("data/panneaux.geojson", location.href);
  window.open(lienNouvelleCarte(url.toString(), "Panneaux Isère"), "_blank");
}

/* ---------- Zones & filtres ---------- */

function remplirChoixZones() {
  const typeSel = $("type-zone");
  const zoneSel = $("choix-zone");
  typeSel.addEventListener("change", () => {
    etat.filtreType = typeSel.value;
    etat.filtreZone = null;
    zoneSel.innerHTML = "";
    if (!typeSel.value) { zoneSel.disabled = true; }
    else {
      zoneSel.disabled = false;
      const zones = etat.zones[typeSel.value] || [];
      const opt = document.createElement("option");
      opt.value = ""; opt.textContent = "— choisir —";
      zoneSel.appendChild(opt);
      zones.forEach(z => {
        const o = document.createElement("option");
        const etiquette = typeSel.value === "circonscription"
          ? `${z.code}. ${z.nom}` : z.nom;
        o.value = z.slug;
        o.textContent = `${etiquette} (${z.communes.length} comm.)`;
        zoneSel.appendChild(o);
      });
    }
    $("btn-umap-zone").disabled = !etat.filtreZone;
    afficherCommunes();
  });
  zoneSel.addEventListener("change", () => {
    if (!zoneSel.value) { etat.filtreZone = null; }
    else {
      const zones = etat.zones[etat.filtreType] || [];
      etat.filtreZone = zones.find(z =>
        (etat.filtreType === "circonscription" ? z.slug : z.slug) === zoneSel.value) || null;
    }
    $("btn-umap-zone").disabled = !etat.filtreZone;
    afficherCommunes();
    if (etat.filtreZone) zoomerZone();
  });
}

function zoomerZone() {
  const bornes = [];
  etat.filtreZone.communes.forEach(code => {
    const f = etat.contoursParCode.get(code);
    if (f) bornes.push(L.geoJSON(f).getBounds());
  });
  if (bornes.length) {
    const b = bornes.reduce((acc, x) => acc ? acc.extend(x) : x, null);
    carte.fitBounds(b.pad(0.05));
  }
}

/* ---------- Stats ---------- */

function majStats() {
  const sel = [...etat.selection];
  const cs = sel.map(c => etat.parCode.get(c));
  const pop = cs.reduce((s, c) => s + c.population, 0);
  const bal = cs.reduce((s, c) => s + (c.boites_aux_lettres || 0), 0);
  $("stat-communes").textContent = sel.length;
  $("stat-pop").textContent = pop.toLocaleString("fr");
  $("stat-bal").textContent = bal.toLocaleString("fr");
  $("stat-panneaux").textContent = etat.panneaux.length;
}

/* ---------- Init ---------- */

$("btn-tout").addEventListener("click", () => {
  candidats().forEach(c => etat.selection.add(c.code));
  afficherCommunes(); afficherPanneaux(); rafraichirStyles(); majStats();
});
$("btn-rien").addEventListener("click", () => {
  etat.selection.clear();
  afficherCommunes(); afficherPanneaux(); rafraichirStyles(); majStats();
});
$("recherche").addEventListener("input", afficherCommunes);
$("btn-gpx").addEventListener("click", exporterGPX);
$("btn-csv").addEventListener("click", exporterCSV);
$("btn-geojson").addEventListener("click", exporterGeoJSON);
$("btn-vider").addEventListener("click", () => {
  etat.tournee = [];
  sauverTournee(); afficherTournee(); afficherPanneaux();
  etat.panneaux.forEach(p => p.__marqueur?.setIcon(iconePanneau(false)));
});
$("btn-umap-zone").addEventListener("click", ouvrirUMapZone);
$("btn-umap-tout").addEventListener("click", ouvrirUMapTout);

charger();
