# Bird gallery

A static site for my bird photography, built from the
[“Birds!” album on Flickr](https://www.flickr.com/photos/sethreznik/albums/72177720327508687).
It shows every photo with the species, its scientific name and family, a short
note about the bird, and where and when the photo was taken. You can filter by
species and by location, browse by species or by place, and share any view by
URL.

```
bird-gallery/
├── data/
│   ├── raw_photos.json   cached Flickr metadata (written by sync.py --fetch)
│   ├── species.json      bird details + name aliases      ← edit me
│   ├── places.json       named birding spots by GPS       ← edit me
│   └── wiki_cache.json   Wikipedia blurbs for species not in species.json (auto)
├── scripts/sync.py       Flickr → site/photos.json (Python stdlib only)
└── site/                 the website (static: index.html, app.js, styles.css, photos.json)
```

## How the data is derived

* **Species** comes from the Flickr photo **title**. Matching ignores case,
  hyphens and apostrophes, so `Red tailed hawk` and `Red-Tailed Hawk` both
  become *Red-tailed Hawk*. Qualifiers become a badge on the photo:
  `Female Cardinal` → Northern Cardinal (*Female*), `Saffron Finch (female)`,
  `American robin(?)` → *Tentative ID*. Titles that are still filenames
  (`DSC05503-….jpg`) show up as **Unidentified**, so rename them on Flickr.
* **Bird details** (scientific name, family, short note) come from
  `data/species.json`. When you photograph a species that isn't listed, the
  sync asks Claude to write its entry in the same style and adds it to
  `species.json` marked `"auto"` with the date (needs the `ANTHROPIC_API_KEY`
  Actions secret; costs a few cents per new species). Review those entries,
  edit them freely, and delete `"auto"` once checked: the sync never
  overwrites existing entries. If a title is too vague to name one species
  ("Sparrow"), the run summary says so and the title is noted in
  `data/species_skipped.json`; retitle the photo on Flickr. To fix a
  mismatched title, add it to that species' `aliases`.
* **Location** comes from the photo's geotag. If it falls inside a spot in
  `data/places.json` it gets that name (e.g. *Prospect Park*). Otherwise it
  falls back to Flickr's borough or county. Photos with no geotag borrow the
  place of a geotagged photo taken within 4 hours on the same day, and are
  marked “approximate”.

## Not Birds

The header's **Birds / Not Birds** switch shows a second set from the
[“Not Birds” album](https://www.flickr.com/photos/sethreznik/albums/72177720337069318),
newest first, filterable by camera settings (camera, lens, shutter speed,
aperture, ISO). Each photo's side page shows where and when it was taken (with
a map when geotagged) and its camera settings, plus "More like this" buttons
that filter by any of them. The sync pulls the album into
`data/raw_notbirds.json` and `site/notbirds.json`, including each photo's EXIF
(fetched once and cached). `data/cameras.json` maps camera and lens codes to
readable names (`ILCE-7CR` → Sony α7CR); add a line when new gear shows up.

Each Not Birds photo is titled by its landmark when it shows a specific
building or structure (Empire State Building, United Nations Secretariat),
otherwise by its place (Chicago, Antelope Island), otherwise by its date.
Landmarks and locations for photos without GPS live in
`data/notbirds_notes.json`. Those locations come from the photo's other Flickr
album, from recognizing the place in the photo, or from same-day photos, and
the site shows them like any other location. New photos are reviewed
automatically: the sync sends each one to Claude (needs `ANTHROPIC_API_KEY`),
which names a landmark when the photo's subject is a specific building or
structure, and a place when the photo has no GPS and the location is clear.
Its entries are marked `"auto"` for review, and each photo is reviewed once
(an empty entry means nothing was found).

## Featured rotator

A rotating banner above each set's photo grid shows your favorites. Tag a photo
on Flickr with `bird_favorite` (Birds) or `build_favorite` (Not Birds); Flickr
stores these as `birdfavorite` / `buildfavorite`, and either tag works in
either set. They appear in the album's order, so rearrange the album in
Flickr's Organizr to choose which comes first. The banner hides while filters
are on or on the Species / Places tabs, and stops rotating when a visitor
picks a slide or prefers reduced motion.

## Updating

The sync re-reads the whole album every time, so it picks up:

* **new photos** added to the album
* **edits** to existing photos on Flickr: retitled (re-identified) birds, captions,
  tags, dates, moved or added geotags, and replaced image files
* **removals**: photos deleted or taken out of the album disappear from the site

The GitHub Action (`.github/workflows/bird-gallery.yml`) runs this every 6 hours,
commits the refreshed data back to the repo, and redeploys. Each run's summary
lists exactly what was added, edited and removed. To sync right away after
editing on Flickr, open **Actions → Bird gallery → Run workflow**.

To sync by hand:

```bash
FLICKR_API_KEY=your_key python bird-gallery/scripts/sync.py --fetch
```

```
Flickr changes: 1 added, 2 changed, 1 removed
  - added Black and White Warbler (55640551719)
  - edited American Kestrel (55639360732) [title]: “Sparrow” → “American Kestrel”
  - edited Magnolia Warbler (55640757630) [location]
  - removed Deleted bird (999)
```

A run with no Flickr changes rewrites nothing, so it creates no commit.

After editing `species.json` or `places.json`, rebuild without hitting Flickr:

```bash
python bird-gallery/scripts/sync.py
```

Preview locally:

```bash
python -m http.server -d bird-gallery/site 8000
```

## Link previews

Shared links show `site/share.jpg` (1200×630): the kestrel, the title and four
photos. To feature different photos, edit the ids in
`scripts/share-card.js` and run `node bird-gallery/scripts/share-card.js`.

Each photo also has its own link, `…/p/<photo id>/`, which the **Share this
photo** button copies (or opens the phone's share sheet). That page carries the
photo's own preview (image, species, place and date) and jumps straight to the
photo in the gallery. `sync.py` regenerates these pages in `site/p/` on every
build; they are not committed.

## Publishing on GitHub Pages (one-time setup)

1. Repo **Settings → Secrets and variables → Actions → New repository secret**:
   name `FLICKR_API_KEY`, value = your Flickr API key. Only the key is needed;
   the secret is not.
   Optionally add `ANTHROPIC_API_KEY` too, so new species get entries written
   automatically.
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Merge this into the default branch (or run the *Bird gallery* workflow from
   the Actions tab). The site deploys to `https://<user>.github.io/<repo>/`.

Never commit the API key; it belongs in the Actions secret.
