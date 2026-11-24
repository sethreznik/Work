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
* **Bird details** (scientific name, family, blurb) come from
  `data/species.json`. A species that isn't listed there gets a Wikipedia
  summary at sync time. To fix a mismatched title, add it to that species'
  `aliases`.
* **Location** comes from the photo's geotag. If it falls inside a spot in
  `data/places.json` it gets that name (e.g. *Prospect Park*). Otherwise it
  falls back to Flickr's borough or county. Photos with no geotag borrow the
  place of a geotagged photo taken within 4 hours on the same day, and are
  marked “approximate”.

## Updating

New uploads to the album appear automatically: the GitHub Action
(`.github/workflows/bird-gallery.yml`) re-syncs from Flickr every day and
redeploys. To refresh by hand:

```bash
FLICKR_API_KEY=your_key python bird-gallery/scripts/sync.py --fetch
```

After editing `species.json` or `places.json`, rebuild without hitting Flickr:

```bash
python bird-gallery/scripts/sync.py
```

Preview locally:

```bash
python -m http.server -d bird-gallery/site 8000
```

## Publishing on GitHub Pages (one-time setup)

1. Repo **Settings → Secrets and variables → Actions → New repository secret**:
   name `FLICKR_API_KEY`, value = your Flickr API key. Only the key is needed;
   the secret is not.
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Merge this into the default branch (or run the *Bird gallery* workflow from
   the Actions tab). The site deploys to `https://<user>.github.io/<repo>/`.

Never commit the API key; it belongs in the Actions secret.
