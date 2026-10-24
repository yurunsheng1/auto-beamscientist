# Auto BeamScientist — WIP project website

**AI for better optics.** An early project preview emphasizing autonomous optical research and PDF manuscripts. The palette uses optical blue and cyan, with restrained spectral accents. Static GitHub Pages site; no sign-in, backend or model API calls. Editorial direction references the light academic presentation of [AFTD](https://rainwangphy.github.io/aftd-platform/); layout and copy are original.

## Build and preview

```sh
python3 build_site.py
python3 verify_site.py
python3 -m unittest discover -s tests -q
python3 -m http.server 8080 --directory dist
```

GitHub Actions builds and checks the catalog, then deploys `dist/` to GitHub Pages on each push to `main`. Set the repository's Pages source to **GitHub Actions**. All asset links are relative, supporting the repository URL path.

## Add a paper

1. Place the PDF and its preview image in `dist/assets/`.
2. Add an entry to `data/papers.json`, with a unique `id`, exact title/authors, year, topic, manuscript status, relative `pdf` and `preview` paths, summary, abstract, limitations, and the PDF's SHA-256.
3. Run the checks above and push to `main`.

The catalog and paper count are generated into HTML at build time, so all papers remain readable without JavaScript. Search filters title and topic in the browser. No hard-coded paper limit. Existing entries are distinct studies; earlier formatting variants of the same manuscript are not counted separately.

## Research provenance

- `core-energy-concentration`: `runs/pgcd/paper/preprint1.pdf`, preview from the matching `build/first_page.png`.
The earlier phase-only manuscript is not currently featured. Its original research files remain in the project workspace.

These are simulation research manuscripts, not claimed peer-reviewed publications. Keep `SIMULATION_ONLY`, `NOVELTY_NOT_VERIFIED`, and `NOT_PUBLICATION_READY` until reviewed status changes are supported. The abstract hero artwork is decorative, not physics output. Website changes do not modify or execute the research solver. No live-status or daily-release schedule is claimed.

## Page-view counter

The footer embeds an external [Hits](https://github.com/silentsoft/hits) SVG badge, keyed to the GitHub Pages URL. It starts when added; no historical traffic is reconstructed and no artificial offset is set. Counts approximate badge requests, not unique people: repeat visits, caching, bots, blockers and service availability affect them. Visitors request the badge directly from hits.sh; no analytics script, API key, local-storage counter or backend is added. A link opens the provider’s statistics.

The public collection is labeled **Autonomous Research Reports**. Reports are shared for exploration and discussion rather than formal publication; this states the current website purpose without claiming any permanent restriction on future submissions.
