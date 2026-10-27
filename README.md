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

## Automatic manuscript publishing

`export_manuscripts.py` runs on 4090hk and exports only manuscripts whose pipeline
has reached `completed` / `finished` and has saved its automatic review. Intermediate
PDFs do not qualify. It extracts the actual title, author and compiled abstract,
renders the first page, and supplies the PDF SHA-256. Retries of the same study
update one catalog entry. This completion gate describes a finished research
report; it does not imply a positive result or journal acceptance.

The authorized sharing threshold also requires scientific soundness of at least
3/4 and either an AI `Accept` or an AI `Reject` with Overall 4–5/10. The latter
are shared as preprints with the actual Reject decision and scores retained in
catalog metadata. Per the owner's display preference, homepage cards and citation
notes omit AI review labels and scores. Paper actions are **Paper**, **Code** (when available) and **BibTeX**;
the underlying review records and export checks remain unchanged.
This is permission to share a
draft, not peer-reviewed acceptance. Numerical confirmation, faithful protocols,
independent questions, controls and evidence/TeX/PDF integrity checks remain
required. Superseded revisions and internal audit PDFs are excluded.

`sync_manuscripts.py` runs on the connected Mac, reads the public artifacts through
the existing VS Code tunnel bridge, verifies them, rebuilds and checks the site,
commits the changed catalog/assets, and pushes to `github/main`. The existing
GitHub Pages workflow deploys the update. The publisher uses the Mac's existing
Git credentials; no model API keys or GitHub credentials are uploaded to the GPU
or included in public bundles. Failed pushes retry without duplicate studies.

```sh
python3 sync_manuscripts.py --watch --push --interval 60 --max-hours 8 \
  --state-dir ../../runs/site_sync
```

The Mac and its VS Code connection to 4090hk must stay online while syncing.
Progress is recorded in `publisher_state.json` and `publisher.log` in the state
directory. Create `STOP` there to stop the watcher. Uncommitted website edits or
a divergent branch stop that sync attempt and preserve the edits.

For a local checkout with an existing `origin` remote, publish with:

```sh
python3 sync_manuscripts.py --local --remote origin --push \
  --source /path/to/run/system --state-dir /path/to/run/publication
```

Install `pdftotext` and `pdftoppm` on the exporting machine. Use a fresh state
directory when replacing a stopped publisher so its `STOP` file remains effective.

## Research provenance

- `core-energy-concentration`: `runs/pgcd/paper/preprint1.pdf`, preview from the matching `build/first_page.png`.
The earlier phase-only manuscript is not currently featured. Its original research files remain in the project workspace.

These are simulation research manuscripts, not claimed peer-reviewed publications. Keep `SIMULATION_ONLY`, `NOVELTY_NOT_VERIFIED`, and `NOT_PUBLICATION_READY` until reviewed status changes are supported. The abstract hero artwork is decorative, not physics output. Website changes do not modify or execute the research solver. No live-status or daily-release schedule is claimed.

## Page-view counter

The footer embeds an external [Hits](https://github.com/silentsoft/hits) SVG badge, keyed to the GitHub Pages URL. It starts when added; no historical traffic is reconstructed and no artificial offset is set. Counts approximate badge requests, not unique people: repeat visits, caching, bots, blockers and service availability affect them. Visitors request the badge directly from hits.sh; no analytics script, API key, local-storage counter or backend is added. A link opens the provider’s statistics.

The public collection is labeled **Autonomous Research Reports**. Reports are shared for exploration and discussion rather than formal publication; this states the current website purpose without claiming any permanent restriction on future submissions.

## Cite a report

Each report has a **BibTeX** link to a citation subpage with readable citation text, a copy button, and a `.bib` download. Clipboard failures offer manual selection and download. The builder generates `dist/citations/<id>.bib` from catalog metadata. Citations use `@misc` and a braced project author to preserve the group name, with the report's direct PDF URL. No DOI or journal is implied. Regenerate citations when titles or metadata change.

Paper 01 also includes a **Runnable code** download. It contains only the bounded CUDA scripts and their required solver modules, dependencies, and frozen input protocol. Manuscripts and archived result data are excluded. See `reproducibility/paper_01/README.md` for run instructions.

## Research activity snapshot

The homepage's 665 hypothesis records, 13,433 physics evaluations and 129 critique cycles describe the completed campaign associated with the first report, recorded 24 October 2026. Source: `runs/pgcd/latest_status/loop_state.json` (`recorded_hypotheses`, `physics_evaluations`, `completed_cycles`), corroborated by the first report's campaign description. The loop increments `completed_cycles` after saving its scientific critique. These fixed activity counts include repeated attempts, failures and related candidates; they are not discovery counts or live telemetry.

The footer’s **Cite this project** entry opens `citations/auto-beamscientist.html`, with a copyable website-level BibTeX citation and `.bib` download. It cites the project website rather than a specific report or a journal publication. Project metadata is generated by `project_bibtex()` in the builder.

## Fixed numerical code for the Airy and Gaussian-vortex papers

Both new papers have individual **Runnable code** downloads. Their sources are
under `reproducibility/pgcd-25b0e6a5f760/` and
`reproducibility/pgcd-2c909e8b5d78/`. Rebuild with
`python3 package_paper_code.py`, then rebuild and verify the site.
The packager uses an explicit seven-file allowlist and adds a hash manifest.
Only the fixed numerical runtime, parameters, scalar reference values and run
instructions are included. Autonomous research, model access, prompts, scheduling,
writing, reviewing, publication code and credentials are excluded from downloads.
Each download computes new values and checks them against the archived numbers;
results are never substituted for calculations. Full validation includes mesh,
window, axial, direct Fresnel and perturbation probes. CUDA is optional for readers.
Future manuscript synchronization retains these links for the same PDF hash;
a replacement PDF requires its runtime to be reviewed again.

The centroid-inversion report has a separate fixed runtime under
`reproducibility/pgcd-5c2846632a64/`. It reproduces the four weights, six numerical
tiers, matched coherent/incoherent centroids and fixed-propagation detector
windows. Its download uses the same explicit seven-file allowlist and hash
manifest. The numerical solver is standalone; no autonomous research engine,
model access, prompts, scheduling, writing, review or publishing code is included.

New research campaigns use a frozen `publication_namespace.json` with a unique `namespace` slug under their source directory. Manuscript IDs then include that campaign identity, so reusing a batch/branch number cannot overwrite a different study from an earlier run. Legacy paper URLs remain unchanged.
## Verifiable public-release times

Each report links to a publication record on its citation page. The record separates its earliest verified successful GitHub Pages deployment from the first verified deployment of the **current PDF hash**. Times are displayed as UTC+08:00 and link to GitHub's deployment-status API, the exact source commit, and the PDF preserved at that commit. `dist/publication-records.json` provides downloadable receipts. Git author/committer dates and model completion times are not treated as publication evidence.

`data/publication-records.json` preserves the initial verified receipts. With GitHub CLI authenticated, `python3 publication_records.py` refreshes evidence using read-only API requests and verifies PDF bytes against the deployed source commits. `build_site.py` is offline and never manufactures timestamps. Missing evidence or a new PDF hash displays **verification pending**.

The normal Pages workflow reads available deployment records before building. A separate `Refresh public-release records` workflow runs once after a successful normal deployment to capture newly public PDFs and republish the verified timestamps. It listens only to `Deploy GitHub Pages`, so its own deployment does not trigger a loop. Neither workflow pushes repository changes or changes manuscript content. The two workflows share the Pages concurrency group.

These records establish the public availability observed in GitHub's deployment history, not independent scientific priority or protection against competing work. They are not a qualified timestamp authority. GitHub documents a 90-day retention period for previous deployment statuses; full API responses are preserved here, but a saved response is not a cryptographically signed attestation. Preserve the repository and consider a separate archival release for longer-term records.

## Country and region statistics

The footer's small bottom-right geography counter embeds the live country-flag image from `https://flagcounter.me/kMd`, with the public aggregate statistics at `https://flagcounter.me/details/kMd`. The image displays country counts; the provider's detail page also supports subdivision (state/province) statistics for this new counter, currently offered as a free preview. No fake sample traffic or historical counts are inserted.

The service estimates locations from requests' IP addresses. Its unique count is lifetime per IP, not verified people, and is independent of the existing Hits page-view count. VPNs, shared IPs, image proxies, browser caches and blockers affect it. The provider processes IP/user-agent information; public statistics do not display IP addresses. The widget is loaded directly by the visitor's browser as an external image; no tracking script or location-permission request is added. The widget is requested when the homepage loads, even before a visitor scrolls to the statistics section. See [provider privacy](https://www.flagcounter.me/privacy).

One-time management credentials are saved only in the local `.private/visitor-geography-access.json` and setup receipt `.private/geography-created.html`, both excluded by `.gitignore`. Do not commit or publish those files, and reuse counter `kMd` for future edits.
