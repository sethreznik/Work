#!/usr/bin/env python3
"""Sync bird photos from Flickr and build the site's data file.

    # pull fresh metadata from Flickr, then build site/photos.json
    FLICKR_API_KEY=... python bird-gallery/scripts/sync.py --fetch

    # rebuild site/photos.json from the cached data only (no network)
    python bird-gallery/scripts/sync.py

Inputs (all in bird-gallery/data/):
    raw_photos.json  cached Flickr metadata (written by --fetch)
    species.json     bird details + name aliases (hand-edited)
    places.json      named birding spots matched by GPS (hand-edited)
    wiki_cache.json  Wikipedia summaries for species not in species.json

Output: bird-gallery/site/photos.json
Standard library only.
"""
import argparse
import html
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

DEFAULT_USER_ID = "65463556@N00"          # flickr.com/photos/sethreznik
DEFAULT_ALBUM_ID = "72177720327508687"    # "Birds!" album
API = "https://api.flickr.com/services/rest/"
UA = "bird-gallery-sync/1.0"

NYC_BOROUGHS = {"Kings": "Brooklyn", "New York": "Manhattan", "Queens": "Queens",
                "Bronx": "Bronx", "Richmond": "Staten Island"}
UNIDENTIFIED = "Unidentified"


# ---------------------------------------------------------------- helpers

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write_json(path, obj, indent=1):
    Path(path).write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n")


def http_json(url, params=None, retries=4):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network hiccup: back off and retry
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def flickr(method, key, **params):
    data = http_json(API, {"method": method, "api_key": key, "format": "json",
                           "nojsoncallback": 1, **params})
    if data.get("stat") != "ok":
        raise RuntimeError(f"{method}: {data.get('code')} {data.get('message')}")
    return data


def norm_key(s):
    """Loose match key: case, hyphens, apostrophes and spacing don't matter."""
    s = s.lower().replace("’", "'").replace("'", "")
    s = re.sub(r"[-_]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- fetch

def fetch(key, user_id, album_id, cache):
    """Return raw photo records for every photo in the album.

    Geo place names need one extra call per photo, so they are reused from
    the cache whenever the photo's coordinates haven't changed.
    """
    cached = {p["id"]: p for p in cache}
    out, page, pages = [], 1, 1
    while page <= pages:
        res = flickr("flickr.photosets.getPhotos", key, photoset_id=album_id,
                     user_id=user_id, per_page=500, page=page,
                     extras="date_taken,date_upload,last_update,geo,description,tags,url_l,url_c,url_z")
        ps = res["photoset"]
        pages = int(ps.get("pages", 1))
        for p in ps["photo"]:
            lat = float(p.get("latitude") or 0) or None
            lon = float(p.get("longitude") or 0) or None
            w = int(p.get("width_l") or p.get("width_c") or p.get("width_z") or 1024)
            h = int(p.get("height_l") or p.get("height_c") or p.get("height_z") or 683)
            rec = {
                "id": p["id"],
                "title": p.get("title", "").strip(),
                "description": (p.get("description") or {}).get("_content", "").strip(),
                "tags": p.get("tags", ""),
                "date_taken": p.get("datetaken"),
                "latitude": lat, "longitude": lon,
                "server": p["server"], "secret": p["secret"],
                "width": w, "height": h,
                "date_upload": int(p.get("dateupload") or 0) or None,
                "last_update": int(p.get("lastupdate") or 0) or None,
            }
            old = cached.get(p["id"])
            # Reuse cached place names unless the photo moved or an earlier lookup failed.
            if old and old.get("latitude") == lat and old.get("longitude") == lon \
                    and (lat is None or old.get("country")):
                for k in ("neighbourhood", "locality", "county", "region", "country"):
                    rec[k] = old.get(k)
            elif lat is not None:
                rec.update(fetch_place_names(key, p["id"]))
            out.append(rec)
        print(f"  album page {page}/{pages}: {len(out)} photos", file=sys.stderr)
        page += 1
    return out


TRACKED = {
    "title": "title", "description": "caption", "tags": "tags", "date_taken": "date taken",
    "latitude": "location", "longitude": "location", "secret": "image",
}


def diff(old, new):
    """Compare two raw snapshots -> {"added": [...], "removed": [...], "changed": [(rec, fields)]}."""
    before = {r["id"]: r for r in old}
    after = {r["id"]: r for r in new}
    changed = []
    for pid, r in after.items():
        o = before.get(pid)
        if o:
            fields = sorted({label for k, label in TRACKED.items() if o.get(k) != r.get(k)})
            if fields:
                changed.append((o, r, fields))
    return {
        "added": [r for pid, r in after.items() if pid not in before],
        "removed": [r for pid, r in before.items() if pid not in after],
        "changed": changed,
    }


def report(d):
    """Human-readable change report; returns (one_line_summary, markdown_lines)."""
    parts = [f"{len(d[k])} {k}" for k in ("added", "changed", "removed") if d[k]]
    summary = ", ".join(parts) if parts else "no changes"
    lines = []
    label = lambda r: f"{r.get('title') or '(untitled)'} ({r['id']})"
    for r in d["added"]:
        lines.append(f"- **added** {label(r)}")
    for o, r, fields in d["changed"]:
        extra = f": “{o.get('title')}” → “{r.get('title')}”" if "title" in fields else ""
        lines.append(f"- **edited** {label(r)} [{', '.join(fields)}]{extra}")
    for r in d["removed"]:
        lines.append(f"- **removed** {label(r)}")
    return summary, lines


def fetch_place_names(key, photo_id):
    names = dict.fromkeys(("neighbourhood", "locality", "county", "region", "country"))
    try:
        loc = flickr("flickr.photos.geo.getLocation", key, photo_id=photo_id)["photo"]["location"]
        for k in names:
            names[k] = (loc.get(k) or {}).get("_content") or None
    except Exception as e:
        print(f"  geo lookup failed for {photo_id}: {e}", file=sys.stderr)
    return names


def fetch_wiki(names, cache):
    """Fill cache with Wikipedia summaries for the given species names."""
    for name in names:
        if name in cache:
            continue
        title = urllib.parse.quote(name.replace(" ", "_"))
        try:
            d = http_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
            cache[name] = {"about": first_sentences(d.get("extract", ""), 2),
                           "wikipedia": d.get("content_urls", {}).get("desktop", {}).get("page")}
            print(f"  wikipedia: {name}", file=sys.stderr)
        except Exception as e:
            print(f"  wikipedia lookup failed for {name}: {e}", file=sys.stderr)


def first_sentences(text, n):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n])


# ---------------------------------------------------------------- build

class SpeciesIndex:
    def __init__(self, entries):
        self.entries = {e["name"]: e for e in entries}
        self.lookup = {}
        for e in entries:
            for alias in [e["name"], e.get("scientific", "")] + e.get("aliases", []):
                if alias:
                    self.lookup[norm_key(alias)] = e["name"]

    def resolve(self, title):
        """Map a Flickr title to (species, note).

        "Osprey (juvenile)" -> ("Osprey", "juvenile")
        "Osprey - Prospect Park" -> ("Osprey", "Prospect Park")
        "DSC05503-DxO.jpg" -> ("Unidentified", None)
        """
        t = (title or "").strip()
        if not t or re.search(r"\.(jpe?g|png|tiff?|heic|dng|arw|nef|cr\d)$", t, re.I) \
                or re.match(r"^(DSC|IMG|_?MG|P\d{6}|PXL)[_\-]?\d", t, re.I):
            return UNIDENTIFIED, None
        notes = []
        if re.search(r"\(\s*\?\s*\)|\?$", t):          # "American robin(?)"
            notes.append("tentative ID")
            t = re.sub(r"\(\s*\?\s*\)|\?$", "", t).strip()
        m = re.match(r"^(.*?)\s*\((.+)\)\s*$", t)          # "Saffron Finch (female)"
        if m:
            t = m.group(1)
            notes.insert(0, m.group(2))
        m = re.match(r"^(.*?)\s+[-\u2013\u2014|:]\s+(.+)$", t)  # "Osprey - Prospect Park"
        if m:
            t = m.group(1)
            notes.insert(0, m.group(2))
        m = QUALIFIER.match(t)                            # "Juvenile and male American Goldfinch"
        if m:
            t = t[m.end():]
            notes.insert(0, m.group(0).strip())
        t = re.sub(r"\s*#?\d+$", "", t).strip()          # "Osprey 2"
        note = ", ".join(n[:1].upper() + n[1:] for n in notes) or None
        k = norm_key(t)
        for cand in (k, re.sub(r" duck$", "", k), re.sub(r"s$", "", k)):  # "Mallard duck", "Pigeons"
            if cand in self.lookup:
                return self.lookup[cand], note
        # Unknown species: tidy capitalisation ("ruby throated hummingbird")
        return " ".join(w[:1].upper() + w[1:] for w in t.split()), note


QUALIFIER = re.compile(r"^(?:(?:female|male|juvenile|immature|adult|young|baby|first[- ]year)\s+(?:and\s+|&\s+)?)+", re.I)


def match_place(lat, lon, places):
    if lat is None or lon is None:
        return None
    for pl in places:
        if haversine_km(lat, lon, pl["lat"], pl["lon"]) <= pl["radius_km"]:
            return pl
    return None


def place_for(rec, places, region_names):
    """(place, area, region, country) for a photo, or Nones if it has no location."""
    pl = match_place(rec.get("latitude"), rec.get("longitude"), places)
    if pl:
        return pl["name"], pl.get("area"), pl.get("region"), pl.get("country")
    county, region, country = rec.get("county"), rec.get("region"), rec.get("country")
    shown_region = region_names.get(region, region)
    if country == "United States":
        # Flickr localities in the US are often subdivision names; counties read better.
        if region == "New York" and county in NYC_BOROUGHS:
            return NYC_BOROUGHS[county], None, shown_region, country
        if county:
            name = county if county.endswith(("County", "Parish")) else f"{county} County"
            return name, None, shown_region, country
    name = rec.get("locality") or county
    if not name:
        return None, None, None, None
    return name, None, shown_region, country


def infer_missing_places(photos, max_hours=4):
    """Borrow the place of the nearest-in-time geotagged photo from the same day."""
    located = [p for p in photos if p["place"] and not p.get("place_inferred")]
    for p in photos:
        if p["place"] or not p["taken"]:
            continue
        t = datetime.fromisoformat(p["taken"])
        best, best_dt = None, None
        for q in located:
            if not q["taken"] or q["taken"][:10] != p["taken"][:10]:
                continue
            dt = abs((datetime.fromisoformat(q["taken"]) - t).total_seconds()) / 3600
            if dt <= max_hours and (best_dt is None or dt < best_dt):
                best, best_dt = q, dt
        if best:
            for k in ("place", "area", "region", "country"):
                p[k] = best[k]
            p["place_inferred"] = True


def last_change(raw):
    """Time of the newest Flickr upload/edit, so unchanged data rebuilds byte-for-byte."""
    ts = max((r.get("last_update") or r.get("date_upload") or 0 for r in raw), default=0)
    when = datetime.fromtimestamp(ts, timezone.utc) if ts else datetime.now(timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(raw, species_index, places_cfg, wiki):
    places = places_cfg.get("places", [])
    region_names = places_cfg.get("region_names", {})
    photos, used = [], {}
    for r in raw:
        species, note = species_index.resolve(r["title"])
        place, area, region, country = place_for(r, places, region_names)
        photos.append({
            "id": r["id"],
            "species": species,
            "note": note,
            "description": r.get("description") or None,
            "taken": r.get("date_taken"),
            "place": place,
            "area": area,
            "region": region,
            "country": country,
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
            "src": f"https://live.staticflickr.com/{r['server']}/{r['id']}_{r['secret']}",
            "w": r["width"], "h": r["height"],
        })
        used[species] = True
    infer_missing_places(photos)

    species_out = {}
    for name in sorted(used):
        if name == UNIDENTIFIED:
            continue
        e = dict(species_index.entries.get(name) or {})
        e.pop("aliases", None)
        e.pop("name", None)
        w = wiki.get(name) or {}
        if not e.get("about") and w.get("about"):
            e["about"] = w["about"]
        if w.get("wikipedia"):
            e["wikipedia"] = w["wikipedia"]
        species_out[name] = e

    photos.sort(key=lambda p: p["taken"] or "", reverse=True)
    return {
        "generated": last_change(raw),
        "flickr_user": os.environ.get("FLICKR_USER_ID", DEFAULT_USER_ID),
        "photos": photos,
        "species": species_out,
    }


# ---------------------------------------------------------------- share pages

PHOTO_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Seth Reznik · Birds">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="__SITE_URL__/p/{id}/">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="{w}">
<meta property="og:image:height" content="{h}">
<meta property="og:image:alt" content="{alt}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="__SITE_URL__/p/{id}/">
<link rel="icon" href="../../kestrel.svg" type="image/svg+xml">
<meta http-equiv="refresh" content="0; url=../../#photo={id}">
<script>location.replace("../../#photo={id}");</script>
<style>body{{margin:0;font:16px/1.5 system-ui,sans-serif;background:#f3eee2;color:#24261f;display:grid;place-items:center;min-height:100vh;text-align:center}}img{{max-width:min(90vw,640px);height:auto;border-radius:6px}}a{{color:#3d6b47}}</style>
</head>
<body>
<p><img src="{thumb}" alt="{alt}" width="{tw}" height="{th}"><br>
<a href="../../#photo={id}">{species}: view in the gallery</a></p>
</body>
</html>
"""


def fmt_day(taken):
    if not taken:
        return None
    d = datetime.strptime(taken[:10], "%Y-%m-%d")
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def write_photo_pages(out):
    """site/p/<id>/index.html for each photo: per-photo link-preview tags,
    then an instant redirect to the photo in the gallery. Regenerated from
    scratch on every build, so removed photos lose their page."""
    root = SITE / "p"
    shutil.rmtree(root, ignore_errors=True)
    for p in out["photos"]:
        where = ", ".join(x for x in (p["place"], p["area"] or p["region"]) if x)
        day = fmt_day(p["taken"])
        desc = "Photographed " + " ".join(x for x in (
            f"at {where}" if where else None, f"on {day}" if day else None) if x) + "."
        if desc == "Photographed .":
            desc = "Bird photography by Seth Reznik."
        species = p["species"] if p["species"] != "Unidentified" else "Unidentified bird"
        scale = 1024 / max(p["w"], p["h"])
        tw, th = round(p["w"] * scale * 640 / 1024), round(p["h"] * scale * 640 / 1024)
        e = lambda v: html.escape(str(v), quote=True)
        page = PHOTO_PAGE.format(
            id=e(p["id"]), title=e(f"{species} · Seth Reznik Birds"), desc=e(desc),
            species=e(species), alt=e(f"{species}{', ' + where if where else ''}"),
            image=e(p["src"] + "_b.jpg"), w=round(p["w"] * scale), h=round(p["h"] * scale),
            thumb=e(p["src"] + "_z.jpg"), tw=tw, th=th)
        d = root / p["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page)
    return len(out["photos"])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="pull fresh metadata from Flickr (needs FLICKR_API_KEY)")
    ap.add_argument("--no-wiki", action="store_true", help="skip Wikipedia lookups for unknown species")
    ap.add_argument("--user-id", default=os.environ.get("FLICKR_USER_ID", DEFAULT_USER_ID))
    ap.add_argument("--album-id", default=os.environ.get("FLICKR_ALBUM_ID", DEFAULT_ALBUM_ID))
    args = ap.parse_args()

    raw = load_json(DATA / "raw_photos.json", [])
    species_index = SpeciesIndex(load_json(DATA / "species.json", {"species": []})["species"])
    places = load_json(DATA / "places.json", {"places": []})
    wiki = load_json(DATA / "wiki_cache.json", {})

    if args.fetch:
        key = os.environ.get("FLICKR_API_KEY")
        if not key:
            sys.exit("FLICKR_API_KEY is not set")
        print(f"Fetching album {args.album_id} ...", file=sys.stderr)
        old_raw = raw
        raw = fetch(key, args.user_id, args.album_id, raw)
        write_json(DATA / "raw_photos.json", raw)

        summary, lines = report(diff(old_raw, raw))
        print(f"Flickr changes: {summary}", file=sys.stderr)
        for line in lines:
            print("  " + line.replace("**", ""), file=sys.stderr)
        # Surface the report in GitHub Actions (run summary + commit message).
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write(f"### Flickr sync: {summary}\n\n" + "\n".join(lines) + "\n")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"summary={summary}\n")

        if not args.no_wiki:
            unknown = {species_index.resolve(r["title"])[0] for r in raw}
            unknown -= set(species_index.entries) | {UNIDENTIFIED}
            fetch_wiki(sorted(unknown), wiki)
            write_json(DATA / "wiki_cache.json", wiki)

    out = build(raw, species_index, places, wiki)
    write_json(SITE / "photos.json", out, indent=None)
    n_pages = write_photo_pages(out)
    n_sp = len(out["species"])
    n_pl = len({p["place"] for p in out["photos"] if p["place"]})
    print(f"Wrote site/photos.json: {len(out['photos'])} photos, {n_sp} species, {n_pl} places; {n_pages} share pages in site/p/", file=sys.stderr)
    missing = sorted(s for s in out["species"] if not out["species"][s].get("about"))
    if missing:
        print("Species without details (add them to data/species.json): " + ", ".join(missing), file=sys.stderr)


if __name__ == "__main__":
    main()
