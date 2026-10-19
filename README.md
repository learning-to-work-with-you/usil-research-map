# USIL Research Map

An annotated, interactive map of research related to **User-Specific Interaction Learning (USIL)**: how AI agents learn from an individual user's own evidence *how* to work with that user—when to ask, act, confirm, explain, or defer.

## Websites

- **Interactive Research Map:** https://map.learntoworkwithyou.org/
- **USIL Research Initiative:** https://learntoworkwithyou.org/
- **ICLR 2027 Workshop Proposal:** https://learning-to-work-with-you.github.io/

The research map is a static application (HTML, CSS, and plain JavaScript, with no build tools or backend). It is deployed from this repository through **Cloudflare Workers Static Assets**, with `map.learntoworkwithyou.org` as its custom domain. The main USIL website and the workshop website are maintained separately.

## What the site shows

- **The landscape at a glance.** Clickable charts that filter the papers by:
  - how many papers combine each USIL ingredient (learning from an individual's evidence → adapting interaction decisions → across sessions → with a transfer evaluation);
  - outcome vs. procedure × population vs. individual (the 2×2 framework in the position paper);
  - papers per year, interaction decisions studied, research areas, and research areas × challenges P1–P4;
  - how clearly each property is established ("not established" means the paper does not report it).
- **Closest predecessors.** The 14 papers from Table 1 of the position paper, with ratings checked against the full text.
- **Browse the papers.** Search and filter the corpus. Each paper's detail view includes metadata, a summary, its relationship to USIL, the overlap and open question for USIL, its role in the position paper, and provenance.

## Data

```text
data/source/usil_literature_map.csv   editorial map, one row per paper (edit this)
data/source/verification.json         full-text verification pipeline output (summaries, overlap, open question, quote-check rate)
data/source/table1.json               full-text-checked ratings for Table 1 of the position paper
scripts/build_data.py                 builds the two generated files below
data/papers.json                      data read by the site (generated; do not edit by hand)
data/papers.csv                       downloadable reader export (generated)
```

After editing files in `data/source/`, rebuild and commit the generated files:

```bash
python scripts/build_data.py
```

### How the labels are derived

- **Levels** (`per_user`, `across_sessions`, `transfer`) are collapsed from free text to **yes / partial / no / not established**. For the 14 Table 1 papers, hand-checked ratings override catalog values.
- **Interaction decisions** are mapped from free text to a controlled vocabulary: ask or clarify, confirm, act or delegate, suggest, explain, interrupt or notify, intervene or take over, defer or return control, communicate. The rules are defined in `DECISION_RULES` in `scripts/build_data.py`.
- **2×2 placement:** **individual** if the paper learns from an individual's evidence (yes or partial), **population** otherwise; **procedure** if it affects at least one interaction decision, **outcome** otherwise. Papers missing either label are not placed.
- **Summaries** are drawn from full text where the verification pipeline read it, and otherwise from the catalog. Each detail view identifies its source.

### Provenance and caveats

Labels describe what each paper reports, not what its methods could theoretically support. Annotations were drafted with the assistance of a language model instructed to support its judgments with quotations from papers; quotation matches were checked automatically against the available text and annotations were reviewed by the author. Table 1 ratings were checked by hand.

Errors and omissions are possible. Please open an issue or pull request with a correction and a paper section or page reference.

**This is a living literature map, not a systematic review.** The labels and visualizations should not be interpreted as exhaustive claims about the literature.

## Contributing

Contributions are welcome, including:

- Suggestions for missing or newly published papers.
- Corrections to bibliographic metadata or factual annotations.
- Revised classifications supported by evidence from the paper.
- Improvements to search, filtering, visualizations, or accessibility.

Please open a GitHub issue or submit a pull request to this repository. Changes are reviewed by maintainers before merging. If you change source data, run `python scripts/build_data.py` and include the updated generated files.

## Run locally

```bash
python -m http.server 8000
# Open http://localhost:8000/
```

Opening `index.html` directly from disk may not work because the application fetches `data/papers.json`.

## Deployment: Cloudflare Workers

The public research map is deployed at **https://map.learntoworkwithyou.org/**, using Cloudflare Workers Static Assets connected to the `main` branch of the GitHub repository `learning-to-work-with-you/usil-research-map`.

For a static application with `index.html` in the repository root and no build step:

1. In Cloudflare, open **Workers & Pages → usil-research-map**.
2. Check the Git integration and ensure its production build tracks the `main` branch.
3. Configure static-asset deployment from the repository root. For a Wrangler-based setup, an example deploy command is `npx wrangler deploy --assets .`.
4. Under **Settings → Domains & Routes**, associate the Worker with the custom domain `map.learntoworkwithyou.org`.
5. Push changes to `main` to trigger deployment, then verify the deployment's **Ready** status and the live URL.

The Cloudflare configuration is separate from the main research initiative at `learntoworkwithyou.org`. Do **not** configure this repository to claim the main site's apex domain. GitHub Pages is an alternative host for this static site, but it is **not the current production host**.

## Citing a snapshot

The position paper refers to a fixed snapshot of this map. For each reproducible snapshot, create a Git release (for example, `v0.2`) and consider archiving it on Zenodo for a DOI. Update `meta.snapshot` in `scripts/build_data.py` to match the archived version.

## License

**Suggested (not yet confirmed):** MIT for the site code and CC BY 4.0 for curated annotations in `data/`. Add the corresponding license files only once these terms are finalized. Summaries should be original paraphrases; do not reproduce copyrighted paper text without appropriate permission.
