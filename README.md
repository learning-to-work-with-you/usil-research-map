# USIL Research Map

An annotated, interactive map of the research behind **User-Specific Interaction Learning (USIL)**: how AI agents learn, from an individual user's own evidence, *how* to work with that user (when to ask, act, confirm, explain, or defer).

Live site: <https://learntoworkwithyou.org/research-map/>

The site is static (HTML, CSS, and plain JavaScript, with no build tools and no backend), so it runs on GitHub Pages.

## What the site shows

- **The landscape at a glance.** Charts of the corpus that can be clicked to filter the papers:
  - how many papers combine each USIL ingredient (learning from an individual's evidence → adapting interaction decisions → across sessions → with a transfer evaluation);
  - outcome vs. procedure × population vs. individual (the 2×2 in the position paper);
  - papers per year, interaction decisions studied, research areas, and research areas × challenges P1–P4;
  - how much each property is established ("not established" means the paper does not say).
- **Closest predecessors.** The 14 papers from Table 1 of the position paper, with ratings checked against each paper's full text.
- **Browse the papers.** Search and filters; each paper opens a detail view with metadata, a summary, how it maps to USIL, the overlap and open question for USIL, its role in the position paper, and its provenance.

## Data

```
data/source/usil_literature_map.csv   editorial map, one row per paper (edit this)
data/source/verification.json         full-text verification pipeline output (summaries, overlap, open question, quote-check rate)
data/source/table1.json               ratings checked against full text for Table 1 of the position paper
scripts/build_data.py                 builds the two files below from the sources
data/papers.json                      what the site reads (generated; do not edit by hand)
data/papers.csv                       download for readers (generated)
```

After editing anything in `data/source/`, rebuild and commit the generated files:

```bash
python scripts/build_data.py
```

### How the labels are derived

- **Levels** (`per_user`, `across_sessions`, `transfer`) are collapsed from free text to *yes / partial / no / not established*. For the 14 Table 1 papers, the hand-checked ratings override the catalog values.
- **Interaction decisions** are mapped from free text to a small vocabulary (ask or clarify, confirm, act or delegate, suggest, explain, interrupt or notify, intervene or take over, defer or return control, communicate). The rules are in `DECISION_RULES` in `scripts/build_data.py`.
- **2×2 placement**: *individual* if the paper learns from an individual's evidence (yes or partial), *population* if not; *procedure* if it affects at least one interaction decision, *outcome* if none. Papers missing either label are not placed.
- **Summaries** come from the full text where the verification pipeline read it, otherwise from the catalog. Each paper's detail view states which.

### Provenance and caveats

Labels describe what each paper reports, not what its methods could support. Annotations were drafted with the assistance of a language model that had to support each judgment with quotations from the paper (checked automatically against the text) and then reviewed by the author. The Table 1 ratings were checked by hand. Labels may contain errors; please open an issue or pull request with a correction and a page reference.

This is a living literature map, not a systematic review.

## Run locally

```bash
python -m http.server 8000
# open http://localhost:8000/
```

Opening `index.html` directly from disk will not work, because the page loads `data/papers.json`.

## Publish on GitHub Pages

Settings → Pages → Deploy from a branch → `main`, `/ (root)`. To serve it at `learntoworkwithyou.org/research-map/`, either make this repository the `research-map` path of the main site or point that path at the Pages URL.

## Citing a snapshot

The position paper refers to a fixed snapshot of this map. Tag a release for each snapshot (for example `v0.2`) and archive it on Zenodo to get a DOI; update `meta.snapshot` in `scripts/build_data.py` to match.

## License

Suggested: MIT for the site code; CC BY 4.0 for the curated annotations in `data/`. Summaries are original paraphrases; do not add copyrighted text from the papers.
