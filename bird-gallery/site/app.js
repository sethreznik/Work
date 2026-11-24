/* Bird gallery: loads photos.json (built by scripts/sync.py) and renders
   a filterable photo grid, species index, places index and a detail lightbox.
   Filter state lives in the URL hash so any view can be linked to. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const UNIDENTIFIED = "Unidentified";

  const state = { set: "birds", view: "photos", q: "", group: "", species: "", place: "", sort: "new", photo: null };
  // The gallery's own folder (e.g. "/Work/"), captured before we ever change the path.
  const BASE = location.pathname.replace(/[^/]*$/, "");
  const photoPath = (id) => `${BASE}p/${encodeURIComponent(id)}/`;
  let DATA = { photos: [], species: {} };
  // "Not Birds": a second, plain photo set (notbirds.json) shown via the header switch.
  let NB = null, nbReady = null;
  const isNB = () => state.set === "notbirds";
  const BIRDS_TITLE = document.title;
  let filtered = [];
  let lbIndex = -1;

  const el = {
    summary: $("#summary"), clear: $("#clear"), empty: $("#empty"),
    q: $("#q"), group: $("#group"), species: $("#species"), place: $("#place"), sort: $("#sort"),
    photos: $("#view-photos"), speciesView: $("#view-species"), placesView: $("#view-places"),
    updated: $("#updated"),
    lb: $("#lightbox"), lbImg: $("#lb-img"), lbInfo: $("#lb-info"),
  };

  // ------------------------------------------------------------ helpers
  const img = (p, size) => `${p.src}_${size}.jpg`;   // z=640, c=800, b=1024 on the long edge
  const srcset = (p) => `${img(p, "z")} 640w, ${img(p, "c")} 800w, ${img(p, "b")} 1024w`;
  const plural = (n, w) => `${n.toLocaleString()} ${w}${n === 1 || w === "species" ? "" : "s"}`;

  function fmtDate(s, withTime = true) {
    if (!s) return "";
    const [d, t = "00:00:00"] = s.split(" ");
    const [y, m, day] = d.split("-").map(Number);
    const [hh, mm] = t.split(":").map(Number);
    const date = new Date(y, m - 1, day, hh, mm);
    const ds = date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
    return withTime ? `${ds} · ${date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}` : ds;
  }

  function placeLine(p) {
    return [p.place, p.area, p.region, p.country].filter((x, i, a) => x && a.indexOf(x) === i).join(", ");
  }

  // Location filter keys: "p:<place>", "r:<region>", "c:<country>"
  function matchesPlace(p, key) {
    if (!key) return true;
    const [kind, val] = [key.slice(0, 1), key.slice(2)];
    if (kind === "p") return p.place === val;
    if (kind === "r") return p.region === val;
    if (kind === "c") return p.country === val;
    if (kind === "u") return !p.place;
    return true;
  }

  function placeLabel(key) {
    if (!key) return "";
    if (key === "u:") return "an unrecorded location";
    return key.slice(2);
  }

  function haystack(p) {
    const s = DATA.species[p.species] || {};
    return [p.species, p.note, s.scientific, s.family, p.place, p.area, p.region, p.country, p.description]
      .filter(Boolean).join(" ").toLowerCase();
  }

  // ------------------------------------------------------------ state <-> URL
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    state.set = h.get("set") === "notbirds" ? "notbirds" : "birds";
    state.view = ["photos", "species", "places"].includes(h.get("view")) ? h.get("view") : "photos";
    state.q = h.get("q") || "";
    state.group = h.get("group") || "";
    state.species = h.get("species") || "";
    state.place = h.get("place") || "";
    state.sort = ["new", "old", "az"].includes(h.get("sort")) ? h.get("sort") : "new";
    state.photo = h.get("photo");
  }

  function writeHash() {
    const h = new URLSearchParams();
    if (isNB()) h.set("set", "notbirds");
    if (state.view !== "photos") h.set("view", state.view);
    if (state.q) h.set("q", state.q);
    if (state.group) h.set("group", state.group);
    if (state.species) h.set("species", state.species);
    if (state.place) h.set("place", state.place);
    if (state.sort !== "new") h.set("sort", state.sort);
    const s = h.toString();
    // While a photo is open, show its own page (p/<id>/) in the address bar:
    // that URL has the photo's link preview, so copying it shares the photo.
    // (A #photo= link can't: preview bots never see anything after the #.)
    const path = state.photo ? photoPath(state.photo) : BASE;
    history.replaceState(null, "", path + (s ? `#${s}` : ""));
  }

  // ------------------------------------------------------------ controls
  function buildControls() {
    const photos = DATA.photos;
    const count = (f) => photos.filter(f).length;

    // Bird groups, in field-guide order, with photo counts (only groups present).
    el.group.innerHTML = `<option value="">All groups</option>` + GROUPS
      .map(([name]) => [name, count((p) => p._group === name)])
      .filter(([, n]) => n)
      .map(([name, n]) => `<option value="${esc(name)}">${esc(name)} (${n})</option>`).join("");

    // Locations grouped country → region → place.
    const tree = new Map();
    photos.forEach((p) => {
      if (!p.place) return;
      if (!tree.has(p.country)) tree.set(p.country, new Map());
      const regions = tree.get(p.country);
      if (!regions.has(p.region)) regions.set(p.region, new Map());
      const places = regions.get(p.region);
      places.set(p.place, (places.get(p.place) || 0) + 1);
    });
    const countries = [...tree.keys()].sort((a, b) =>
      count((p) => p.country === b) - count((p) => p.country === a));
    let html = `<option value="">All locations</option>`;
    const sp = " ";
    for (const c of countries) {
      html += `<optgroup label="${esc(c)}"><option value="c:${esc(c)}">All of ${esc(c)} (${count((p) => p.country === c)})</option>`;
      const regions = [...tree.get(c).entries()].sort((a, b) => a[0].localeCompare(b[0]));
      for (const [r, places] of regions) {
        if (regions.length > 1) html += `<option value="r:${esc(r)}">${sp}${esc(r)} (${count((p) => p.region === r)})</option>`;
        const pad = regions.length > 1 ? sp + sp + sp : sp;
        [...places.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
          .forEach(([name, n]) => (html += `<option value="p:${esc(name)}">${pad}${esc(name)} (${n})</option>`));
      }
      html += `</optgroup>`;
    }
    const unknown = count((p) => !p.place);
    if (unknown) html += `<option value="u:">Location not recorded (${unknown})</option>`;
    el.place.innerHTML = html;

    if (DATA.generated) el.updated.textContent = `Updated ${fmtDate(DATA.generated.slice(0, 10), false)}`;
  }

  // Species dropdown lists only species in the chosen group (if any).
  let speciesOptionsFor = null;
  function buildSpeciesOptions() {
    if (speciesOptionsFor === state.group) return;
    speciesOptionsFor = state.group;
    const counts = {};
    DATA.photos.forEach((p) => {
      if (!state.group || p._group === state.group) counts[p.species] = (counts[p.species] || 0) + 1;
    });
    const names = Object.keys(counts).sort((a, b) =>
      (a === UNIDENTIFIED) - (b === UNIDENTIFIED) || a.localeCompare(b));
    const n = names.filter((x) => x !== UNIDENTIFIED).length;
    el.species.innerHTML = `<option value="">${state.group ? `All ${n} species` : `All species (${n})`}</option>` +
      names.map((x) => `<option value="${esc(x)}">${esc(x)} (${counts[x]})</option>`).join("");
  }

  function syncControls() {
    el.q.value = state.q;
    el.group.value = state.group;
    if (el.group.value !== state.group) state.group = "";
    buildSpeciesOptions();
    el.species.value = state.species;
    if (el.species.value !== state.species) state.species = "";
    el.place.value = state.place;
    if (el.place.value !== state.place) state.place = "";
    el.sort.value = state.sort;
    el.group.classList.toggle("active", !!state.group);
    el.species.classList.toggle("active", !!state.species);
    el.place.classList.toggle("active", !!state.place);
    document.querySelectorAll(".tabs button").forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
  }

  // ------------------------------------------------------------ filtering
  function applyFilters() {
    const terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    filtered = DATA.photos.filter((p) =>
      (!state.group || p._group === state.group) &&
      (!state.species || p.species === state.species) &&
      matchesPlace(p, state.place) &&
      (!terms.length || terms.every((t) => p._hay.includes(t))));
    const by = {
      new: (a, b) => (b.taken || "").localeCompare(a.taken || ""),
      old: (a, b) => (a.taken || "9").localeCompare(b.taken || "9"),
      az: (a, b) => a.species.localeCompare(b.species) || (b.taken || "").localeCompare(a.taken || ""),
    }[state.sort];
    filtered.sort(by);
  }

  function loadNB() {
    nbReady ??= fetch(`${BASE}notbirds.json`)
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((d) => { NB = d; })
      .catch((err) => { nbReady = null; throw err; });
    return nbReady;
  }
  const ready = () => (isNB() ? loadNB() : Promise.resolve());

  function syncSetSwitch() {
    document.body.classList.toggle("is-notbirds", isNB());
    document.querySelectorAll(".sets button").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.set === state.set)));
    document.title = isNB() ? "Not Birds · Seth Reznik" : BIRDS_TITLE;
    // Header mark and tab icon: kestrel for Birds, city at dusk for Not Birds.
    const icon = `${BASE}${isNB() ? "notbirds.svg" : "kestrel.svg"}`;
    const mark = $(".mark");
    if (mark && !mark.src.endsWith(icon)) mark.src = icon;
    const fav = document.querySelector('link[rel="icon"]');
    if (fav && fav.getAttribute("href") !== icon) fav.setAttribute("href", icon);
  }

  // Not Birds: just the photos, newest first; no filters, tabs or details.
  function renderNotBirds() {
    if (!NB) {
      el.summary.textContent = "Loading…";
      loadNB().then(render, () => { el.summary.textContent = "Couldn't load photos."; });
      return;
    }
    filtered = NB.photos;
    writeHash();
    el.summary.innerHTML = `<b>${plural(filtered.length, "photograph")}</b>`;
    el.clear.hidden = true;
    el.photos.hidden = false;
    el.speciesView.hidden = el.placesView.hidden = true;
    el.empty.hidden = filtered.length > 0;
    renderGrid();
  }

  function render() {
    syncSetSwitch();
    if (isNB()) return renderNotBirds();
    syncControls();
    applyFilters();
    writeHash();

    const nSp = new Set(filtered.map((p) => p.species).filter((s) => s !== UNIDENTIFIED)).size;
    const nPl = new Set(filtered.map((p) => p.place).filter(Boolean)).size;
    let what = `<b>${plural(filtered.length, "photo")}</b> · ${plural(nSp, "species")} · ${plural(nPl, "location")}`;
    const bits = [];
    if (state.species) bits.push(`of <b>${esc(state.species)}</b>`);
    else if (state.group) bits.push(`in <b>${esc(state.group)}</b>`);
    if (state.place) bits.push(`at <b>${esc(placeLabel(state.place))}</b>`);
    if (state.q) bits.push(`matching “${esc(state.q)}”`);
    el.summary.innerHTML = bits.length ? `${what} ${bits.join(" ")}` : what;
    el.clear.hidden = !(state.group || state.species || state.place || state.q);

    el.photos.hidden = state.view !== "photos";
    el.speciesView.hidden = state.view !== "species";
    el.placesView.hidden = state.view !== "places";
    el.empty.hidden = filtered.length > 0;

    if (state.view === "photos") renderGrid();
    if (state.view === "species") renderSpecies();
    if (state.view === "places") renderPlaces();
  }

  function renderGrid() {
    el.photos.innerHTML = filtered.map((p, i) => {
      const r = Math.min(Math.max(p.w / p.h, 0.5), 2.4);
      const loc = p.place ? esc(p.place) : "";
      const label = p.species || p.title || "Photograph";
      return `<button class="tile" data-i="${i}" style="width:calc(var(--row) * ${r.toFixed(3)});flex-grow:${r.toFixed(3)}"
        aria-label="${esc(label)}${loc ? ", " + loc : ""}">
        <i style="padding-bottom:${(100 / r).toFixed(3)}%"></i>
        <img loading="lazy" decoding="async" src="${img(p, "z")}" srcset="${srcset(p)}"
          sizes="(max-width: 640px) 50vw, 33vw" alt="${esc(label)}">
        ${p.species ? `<span class="cap"><strong>${esc(p.species)}</strong><span>${loc}${loc && p.taken ? " · " : ""}${p.taken ? fmtDate(p.taken, false) : ""}</span></span>` : ""}
      </button>`;
    }).join("");
    el.photos.querySelectorAll("img").forEach((im) => {
      if (im.complete) im.classList.add("loaded");
      else im.addEventListener("load", () => im.classList.add("loaded"), { once: true });
    });
  }

  function card(cover, title, lines, attrs) {
    return `<button class="card" ${attrs}>
      <div class="thumb"><img loading="lazy" src="${img(cover, "z")}" alt=""></div>
      <h3>${esc(title)}</h3>${lines.map((l) => `<p${l.cls ? ` class="${l.cls}"` : ""}>${l.html}</p>`).join("")}
    </button>`;
  }

  function renderSpecies() {
    const groups = new Map();
    for (const p of filtered) {
      const fam = (DATA.species[p.species] || {}).family || (p.species === UNIDENTIFIED ? "Not yet identified" : "Other");
      if (!groups.has(fam)) groups.set(fam, new Map());
      const g = groups.get(fam);
      if (!g.has(p.species)) g.set(p.species, []);
      g.get(p.species).push(p);
    }
    const fams = [...groups.keys()].sort((a, b) =>
      (a === "Not yet identified") - (b === "Not yet identified") || a.localeCompare(b));
    el.speciesView.innerHTML = fams.map((fam) => {
      const sp = [...groups.get(fam).entries()].sort((a, b) => a[0].localeCompare(b[0]));
      return `<h2 class="group-h">${esc(fam.replace(/ & /g, " and "))}<small>${plural(sp.length, "species")}</small></h2>` +
        sp.map(([name, ps]) => {
          const info = DATA.species[name] || {};
          const places = new Set(ps.map((p) => p.place).filter(Boolean));
          return card(ps[0], name, [
            info.scientific ? { cls: "sci", html: esc(info.scientific) } : null,
            { html: `${plural(ps.length, "photo")}${places.size ? ` · ${plural(places.size, "location")}` : ""}` },
          ].filter(Boolean), `data-species="${esc(name)}"`);
        }).join("");
    }).join("");
  }

  function renderPlaces() {
    const groups = new Map();
    for (const p of filtered) {
      if (!p.place) continue;
      const g = [p.region, p.country].filter(Boolean).join(", ");
      if (!groups.has(g)) groups.set(g, new Map());
      const m = groups.get(g);
      if (!m.has(p.place)) m.set(p.place, []);
      m.get(p.place).push(p);
    }
    const order = [...groups.entries()].sort((a, b) =>
      [...b[1].values()].flat().length - [...a[1].values()].flat().length);
    el.placesView.innerHTML = order.map(([g, places]) =>
      `<h2 class="group-h">${esc(g)}<small>${plural(places.size, "location")}</small></h2>` +
      [...places.entries()].sort((a, b) => b[1].length - a[1].length).map(([name, ps]) => {
        const sp = new Set(ps.map((p) => p.species).filter((s) => s !== UNIDENTIFIED));
        const span = [ps[ps.length - 1].taken, ps[0].taken].filter(Boolean).map((d) => d.slice(0, 4));
        const years = span.length ? [...new Set(span)].sort().join("–") : "";
        return card(ps[0], name, [
          { html: `${plural(sp.size, "species")} · ${plural(ps.length, "photo")}` },
          years ? { html: esc(years) } : null,
        ].filter(Boolean), `data-place="p:${esc(name)}"`);
      }).join("")
    ).join("") || "";
  }

  // ------------------------------------------------------------ bird groups
  // Field-guide-style color coding: each Latin family belongs to a broad group,
  // and the group's color drives the photo view's rule, buttons, links, spine
  // tab and map pin. All colors pass WCAG AA with white text and on the page.
  const GROUPS = [
    ["Waterfowl", "#2c6a86", "Anatidae"],
    ["Grebes, loons & cormorants", "#45618f", "Podicipedidae Gaviidae Phalacrocoracidae"],
    ["Herons, cranes & rails", "#2f7369", "Ardeidae Threskiornithidae Gruidae Rallidae Aramidae"],
    ["Shorebirds & gulls", "#7d6338", "Charadriidae Scolopacidae Recurvirostridae Haematopodidae Jacanidae Laridae Rynchopidae"],
    ["Hawks, eagles & falcons", "#b03d22", "Accipitridae Pandionidae Falconidae Cathartidae"],
    ["Owls", "#6e4c39", "Strigidae Tytonidae"],
    ["Gamebirds", "#94622a", "Phasianidae Odontophoridae"],
    ["Pigeons & doves", "#80577a", "Columbidae"],
    ["Hummingbirds, kingfishers, woodpeckers & parrots", "#3f7330", "Trochilidae Alcedinidae Picidae Psittacidae"],
    ["Flycatchers, swallows, thrushes & kin", "#64508c", "Tyrannidae Furnariidae Corvidae Hirundinidae Paridae Sittidae Troglodytidae Regulidae Turdidae Mimidae Bombycillidae Sturnidae Vireonidae Polioptilidae"],
    ["Warblers", "#836a0d", "Parulidae"],
    ["Sparrows, finches, tanagers & blackbirds", "#a64f1f", "Passerellidae Fringillidae Passeridae Cardinalidae Thraupidae Icteridae Emberizidae Calcariidae"],
  ];
  const GROUP_OF = new Map(GROUPS.flatMap(([name, color, fams]) => fams.split(" ").map((f) => [f, { name, color }])));
  const DEFAULT_GROUP = { name: "", color: "#8a6f4e" };  // unidentified / unknown family
  const groupOf = (family = "") => GROUP_OF.get((family.match(/\(([^)]+)\)/) || [])[1]) || DEFAULT_GROUP;

  // ------------------------------------------------------------ lightbox
  // Photo view: 1024px plus Flickr's 1600/2048px versions; the browser picks
  // what the screen needs. sizes mirrors the layout (image area = viewport
  // minus the 32px spine tab and the clamp(300px, 22vw, 360px) page).
  const LB_SIZES = "(max-width: 900px) 100vw, (max-width: 1360px) calc(100vw - 340px), (max-width: 1640px) calc(78vw - 40px), calc(100vw - 400px)";
  function setLbSources(im, p) {
    const big = p.big || {};
    im.sizes = isNB() ? "100vw" : LB_SIZES;  // Not Birds photos use the full width
    im.srcset = [`${img(p, "b")} 1024w`, big.h && `${big.h} 1600w`, big.k && `${big.k} 2048w`].filter(Boolean).join(", ");
    im.src = img(p, "b");
  }
  function openLightbox(i) {
    if (i < 0 || i >= filtered.length) return;
    lbIndex = i;
    const p = filtered[i];
    state.photo = p.id;
    writeHash();

    // Not Birds: the photo full width, no details panel.
    el.lb.classList.toggle("bare", isNB());
    if (isNB()) {
      setLbSources(el.lbImg, p);
      el.lbImg.alt = p.title || "Photograph";
      [i - 1, i + 1].forEach((j) => { if (filtered[j]) setLbSources(new Image(), filtered[j]); });
      el.lbInfo.innerHTML = "";
      $("#lb-tab").textContent = "";
      $("#lb-prev").hidden = i === 0;
      $("#lb-next").hidden = i === filtered.length - 1;
      if (!el.lb.open) el.lb.showModal();
      return;
    }
    const info = DATA.species[p.species] || {};

    setLbSources(el.lbImg, p);
    el.lbImg.alt = `${p.species}${p.place ? ", " + p.place : ""}`;
    // warm the neighbours
    [i - 1, i + 1].forEach((j) => { if (filtered[j]) setLbSources(new Image(), filtered[j]); });

    const seenInUS = DATA.photos.some((q) => q.species === p.species && q.country === "United States");
    const slug = p.species.replace(/['’]/g, "").replace(/\s+/g, "_");
    const links = [];
    if (p.species !== UNIDENTIFIED) {
      if (seenInUS) links.push(`<a href="https://www.allaboutbirds.org/guide/${encodeURIComponent(slug)}" target="_blank" rel="noopener">All About Birds ↗</a>`);
      links.push(`<a href="${esc(info.wikipedia || "https://en.wikipedia.org/wiki/" + encodeURIComponent(p.species.replace(/\s+/g, "_")))}" target="_blank" rel="noopener">Wikipedia ↗</a>`);
    }
    const nSame = DATA.photos.filter((q) => q.species === p.species).length;
    const nHere = p.place ? DATA.photos.filter((q) => q.place === p.place).length : 0;

    // Field-guide entry: NAME / Scientific / status line, a red rule, then
    // the description and run-in italic labels ("Taken:", "Location:" ...).
    const fam = info.family || "";
    const [, famCommon = fam, famLatin = ""] = fam.match(/^(.*?)\s*\(([^)]+)\)\s*$/) || [];
    $("#lb-tab").textContent = famCommon.replace(/ & /g, " and ");
    const group = groupOf(fam);
    const nGroup = group.name ? DATA.photos.filter((q) => q._group === group.name).length : 0;
    el.lb.style.setProperty("--rule", group.color);
    $("#lb-tab").title = group.name;
    const nPlaces = new Set(DATA.photos.filter((q) => q.species === p.species).map((q) => q.place).filter(Boolean)).size;
    const status = [famLatin, plural(nSame, "photo"), nPlaces ? plural(nPlaces, "location") : ""].filter(Boolean).join(" · ");
    const where = p.place
      ? esc([p.place, p.area, p.region, p.country].reduce((out, x) =>
          // skip empty parts and ones that repeat the previous ("Buenos Aires, Buenos Aires City")
          x && !out.some((y) => x.startsWith(y) || y.startsWith(x)) ? [...out, x] : out, []).join(", ")) +
        (p.place_inferred ? ` <span class="aside">(approximate, from photos taken the same day)</span>` : "")
      : `<span class="aside">not recorded</span>`;
    const fact = (label, html) => `<p class="fact"><em>${label}:</em> ${html}</p>`;

    el.lbInfo.innerHTML = `
      <header class="entry-h">
        <h2>${esc(p.species)}</h2>
        ${info.scientific ? `<p class="sci">${esc(info.scientific)}</p>` : ""}
        <p class="status">${esc(status)}</p>
      </header>
      ${info.about ? `<p class="about">${esc(info.about)}</p>` : p.species === UNIDENTIFIED ? `<p class="about">This bird hasn't been identified yet.</p>` : ""}
      ${p.note ? fact("Note", esc(p.note)) : ""}
      ${fact("Taken", p.taken ? esc(fmtDate(p.taken)) : `<span class="aside">unknown</span>`)}
      ${fact("Location", where)}
      ${p.lat != null ? `<div class="map-slot"></div>
        <p class="map-cap"><a href="https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=15/${p.lat}/${p.lon}" target="_blank" rel="noopener">${p.lat.toFixed(4)}, ${p.lon.toFixed(4)} · Open larger map ↗</a></p>` : ""}
      ${p.description ? fact("Notes", `<span class="desc">${esc(p.description)}</span>`) : ""}
      ${links.length ? `<p class="links">${links.join("")}</p>` : ""}
      <div class="lb-actions">
        ${nSame > 1 && state.species !== p.species ? `<button class="btn primary" data-go-species="${esc(p.species)}">All ${nSame} photos of ${esc(p.species)}</button>` : ""}
        ${nGroup > nSame && state.group !== group.name ? `<button class="btn" data-go-group="${esc(group.name)}">All ${nGroup} photos in ${esc(group.name)}</button>` : ""}
        ${nHere > 1 && state.place !== "p:" + p.place ? `<button class="btn" data-go-place="p:${esc(p.place)}">All ${nHere} photos at ${esc(p.place)}</button>` : ""}
        <button class="btn" data-share="${esc(p.id)}">Share this photo</button>
        <a class="btn" href="https://www.flickr.com/photos/sethreznik/${esc(p.id)}/" target="_blank" rel="noopener">View on Flickr ↗</a>
      </div>
      <p class="counter">${i + 1} of ${filtered.length}</p>`;

    $("#lb-prev").hidden = i === 0;
    $("#lb-next").hidden = i === filtered.length - 1;
    if (!el.lb.open) el.lb.showModal();
    $(".lb").scrollTop = 0;
    el.lbInfo.scrollTop = 0;
    showMap(p, el.lbInfo.querySelector(".map-slot"), group.color);
  }

  // ------------------------------------------------------------ inline map
  // Leaflet (vendored in vendor/leaflet) loads the first time a photo with GPS
  // is opened. One map is reused: its element moves into each new entry.
  // Paths use BASE because the address bar shows p/<id>/ while a photo is open.
  let leafletReady = null, lbMap = null, lbMarker = null;
  const mapEl = document.createElement("div");
  mapEl.className = "lb-map";

  function loadLeaflet() {
    leafletReady ??= new Promise((resolve, reject) => {
      const css = Object.assign(document.createElement("link"), { rel: "stylesheet", href: `${BASE}vendor/leaflet/leaflet.css` });
      const js = Object.assign(document.createElement("script"), { src: `${BASE}vendor/leaflet/leaflet.js` });
      js.onload = () => resolve(window.L);
      js.onerror = () => { leafletReady = null; reject(new Error("Leaflet failed to load")); };
      document.head.append(css, js);
    });
    return leafletReady;
  }

  async function showMap(p, slot, color) {
    if (!slot || p.lat == null) return;
    slot.replaceWith(mapEl);
    mapEl.setAttribute("aria-label", `Map showing where this photo was taken${p.place ? ": " + p.place : ""}`);
    let L;
    try { L = await loadLeaflet(); } catch (_) { mapEl.remove(); return; }
    if (filtered[lbIndex] !== p) return; // user already moved on
    const ll = [p.lat, p.lon];
    if (!lbMap) {
      lbMap = L.map(mapEl, {
        scrollWheelZoom: false,          // scrolling the page shouldn't zoom the map
        dragging: !L.Browser.mobile,     // ...or trap a finger on phones
        tap: false,
      });
      // OpenStreetMap's standard tiles: free with attribution for light use
      // (https://operations.osmfoundation.org/policies/tiles/).
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      }).addTo(lbMap);
      lbMarker = L.circleMarker(ll, { radius: 8, color: "#ffffff", weight: 3, fillColor: "#c9472a", fillOpacity: 1 }).addTo(lbMap);
    }
    lbMap.invalidateSize();
    lbMap.setView(ll, 14, { animate: false });
    lbMarker.setLatLng(ll).setStyle({ fillColor: color });
  }

  function closeLightbox() {
    if (el.lb.open) el.lb.close();
  }

  el.lb.addEventListener("close", () => {
    lbIndex = -1;
    state.photo = null;
    writeHash();
  });

  // ------------------------------------------------------------ events
  function set(patch) {
    Object.assign(state, patch);
    render();
    window.scrollTo({ top: Math.min(window.scrollY, $(".masthead").offsetHeight), behavior: "instant" });
  }

  let qTimer;
  el.q.addEventListener("input", () => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => set({ q: el.q.value.trim() }), 150);
  });
  // Changing group clears a species from another group.
  el.group.addEventListener("change", () => set({ group: el.group.value, species: "" }));
  el.species.addEventListener("change", () => set({ species: el.species.value }));
  el.place.addEventListener("change", () => set({ place: el.place.value }));
  el.sort.addEventListener("change", () => set({ sort: el.sort.value }));
  el.clear.addEventListener("click", () => set({ q: "", group: "", species: "", place: "" }));
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.addEventListener("click", () => set({ view: b.dataset.view })));

  el.photos.addEventListener("click", (e) => {
    const t = e.target.closest(".tile");
    if (t) openLightbox(Number(t.dataset.i));
  });
  el.speciesView.addEventListener("click", (e) => {
    const c = e.target.closest("[data-species]");
    if (c) set({ species: c.dataset.species, view: "photos" });
  });
  el.placesView.addEventListener("click", (e) => {
    const c = e.target.closest("[data-place]");
    if (c) set({ place: c.dataset.place, view: "photos" });
  });

  // Each photo has a static page at p/<id>/ (built by sync.py) carrying its own
  // link-preview tags; it redirects to the photo here. That's the link we share.
  async function sharePhoto(btn) {
    const p = DATA.photos.find((q) => q.id === btn.dataset.share);
    const url = new URL(photoPath(p.id), location.origin).href;
    const title = `${p.species} · Seth Reznik Birds`;
    if (navigator.share && matchMedia("(pointer: coarse)").matches) {
      try { await navigator.share({ title, url }); } catch (_) { /* user cancelled */ }
      return;
    }
    const label = btn.textContent;
    try {
      await navigator.clipboard.writeText(url);
      btn.textContent = "Link copied ✓";
    } catch (_) {
      window.prompt("Copy this link:", url);
      return;
    }
    setTimeout(() => { if (btn.isConnected) btn.textContent = label; }, 2000);
  }

  el.lbInfo.addEventListener("click", (e) => {
    const sh = e.target.closest("[data-share]");
    if (sh) { sharePhoto(sh); return; }
    const s = e.target.closest("[data-go-species]");
    const pl = e.target.closest("[data-go-place]");
    const gr = e.target.closest("[data-go-group]");
    if (!s && !pl && !gr) return;
    // Close the photo and show the filtered gallery, scrolled to the results.
    closeLightbox();
    const patch = s ? { species: s.dataset.goSpecies, group: "", place: "", q: "" }
      : gr ? { group: gr.dataset.goGroup, species: "", place: "", q: "" }
      : { place: pl.dataset.goPlace, group: "", species: "", q: "" };
    set({ ...patch, view: "photos", photo: null });
    window.scrollTo({ top: $(".masthead").offsetHeight, behavior: "instant" });
  });
  $("#lb-prev").addEventListener("click", () => openLightbox(lbIndex - 1));
  $("#lb-next").addEventListener("click", () => openLightbox(lbIndex + 1));
  $("#lb-close").addEventListener("click", closeLightbox);
  el.lb.addEventListener("click", (e) => { if (e.target.classList.contains("lb-media")) closeLightbox(); });
  document.addEventListener("keydown", (e) => {
    if (!el.lb.open) return;
    if (e.key === "ArrowLeft") openLightbox(lbIndex - 1);
    if (e.key === "ArrowRight") openLightbox(lbIndex + 1);
  });
  let touchX = null;
  el.lb.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
  el.lb.addEventListener("touchend", (e) => {
    if (touchX == null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 60) openLightbox(lbIndex + (dx < 0 ? 1 : -1));
  });

  // Header switch: Birds / Not Birds (filters belong to Birds, so they reset).
  document.querySelectorAll(".sets button").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.set === state.set) return;
    set({ set: b.dataset.set, view: "photos", q: "", group: "", species: "", place: "", photo: null });
  }));

  window.addEventListener("hashchange", () => {
    const before = state.photo;
    readHash();
    ready().then(() => {
      render();
      if (state.photo && state.photo !== before) {
        const i = filtered.findIndex((p) => p.id === state.photo);
        if (i >= 0) openLightbox(i);
      } else if (!state.photo) closeLightbox();
    });
  });

  // ------------------------------------------------------------ boot
  fetch("photos.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      DATA = data;
      DATA.photos.forEach((p) => {
        p._group = groupOf((DATA.species[p.species] || {}).family).name;
        p._hay = haystack(p) + " " + p._group.toLowerCase();  // so search finds "owls", "warblers"...
      });
      buildControls();
      readHash();
      return ready().then(() => {
        render();
        if (state.photo) {
          const i = filtered.findIndex((p) => p.id === state.photo);
          if (i >= 0) openLightbox(i);
        }
      });
    })
    .catch((err) => {
      el.summary.textContent = "Couldn't load photos.";
      console.error(err);
    });
})();
