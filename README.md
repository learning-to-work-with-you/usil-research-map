# USIL Research Map

An annotated, interactive map of research related to **User-Specific Interaction Learning (USIL)**: how AI agents learn from an individual user's own evidence *how* to work with that user—when to ask, act, confirm, explain, or defer.

## Websites

- **Interactive Research Map:** https://map.learntoworkwithyou.org/
- **USIL Research Initiative:** https://learntoworkwithyou.org/
- **ICLR 2027 Workshop Proposal:** https://learning-to-work-with-you.github.io/

The research map is a static application (HTML, CSS, and plain JavaScript, with no build tools or backend). It is deployed from this repository through **Cloudflare Workers Static Assets**, with `map.learntoworkwithyou.org` as its custom domain. The main USIL website and the workshop website are maintained separately.

## What the site shows

- **Where the work sits.** The 2×2 framework (outcome vs. procedure × population vs. individual) with one dot per paper and a year slider, and papers per year.
- **How much of USIL each paper covers.** The four USIL ingredients (learning from one person's evidence, adapting interaction decisions, adapting across sessions, testing transfer to new tasks), each counted on its own; how many of the four each paper covers; and the papers that have all four.
- **The four research challenges.** For each challenge (P1–P4): paper counts, how many papers have each ingredient, active areas, and what full-text reading found (signals learned from, user representations, decision factors, who the evaluation users are).
- **More about the collection.** Interaction decisions by whose evidence they are learned from, who the users are in evaluations, how few papers report results for each person, and research areas.
- **Browse the papers.** Search and filter; each paper's detail view has a summary, its labels, study design, relation to USIL, an open question, and provenance.

## Repository layout

```text
index.html, app.js, style.css, assets/   the site (static; no build step)
data/papers.csv           the map: one row per paper. Edit this file; it is also the site's download.
data/schema.json          the columns and their allowed values (read by the site, the check, and the pipeline)
data/LICENSE.md           license for the annotations (CC BY 4.0)
scripts/check_papers.py   checks papers.csv against the schema
pipeline/                 optional: reads papers with Claude and fills in rows (see pipeline/README.md)
.github/                  pull-request checks (papers.csv + pipeline tests) and the PR template
LICENSE                   license for the code (MIT)
```

## Data

There is no build step: the site loads `data/papers.csv` and `data/schema.json` directly.

### Columns of `papers.csv`

| Group | Columns | Notes |
|---|---|---|
| Required | `key`, `title`, `year`, `url`, `category`, `pillars`, `summary` | `key`: lowercase surname + year + word, e.g. `liang2026pahf`. `category`: one of the eight areas in `schema.json`. `pillars`: any of `P1;P2;P3;P4`. |
| Recommended | `authors`, `venue` | |
| Chart labels | `per_user`, `interaction_decisions`, `across_sessions`, `evaluates_transfer` | Required unless `annotation_source` is `pending`. `yes` / `partial` / `no` / `not-stated`; decisions are a list (`ask;confirm`), `none`, or `not-stated`. |
| Optional text | `what_is_learned`, `user_evidence`, `usil_relation`, `open_question`, `notes` | Shown in the paper's detail view. |
| Study design | `paper_type` … `resources` | Usually filled by the pipeline; allowed values in `schema.json`. |
| Provenance | `annotation_source`, `annotated_on`, `quotes_verified` | `pending`, `manual`, `pipeline-fulltext`, or `pipeline-abstract`. |

Lists use `;`. A blank cell means unknown; `not-stated` means the paper was read and does not say.
A `pending` paper is listed in Browse as "Not yet annotated" and joins the charts once labeled.

### How the site uses the labels

- **2×2 placement:** individual if `per_user` is yes or partial, population if no; procedure if the paper has at least one interaction decision, outcome if `none`. Papers with `not-stated` in either are not placed.
- **Ingredients:** a paper has an ingredient when its label is yes or partial (for decisions: at least one decision). Each ingredient is counted independently; no order is implied.
- **Summaries and labels** come from the full text where `annotation_source` is `pipeline-fulltext`; the detail view says which.

### Provenance and caveats

Labels describe what each paper reports, not what its methods could theoretically support. Rows marked `pipeline-fulltext` were drafted by a language model from the paper's full text, with every supporting quotation checked automatically against the PDF (`quotes_verified` is the share found); they have not all been reviewed by hand.

Errors and omissions are possible. Please open an issue or pull request with a correction and a paper section or page reference.

**This is a living literature map, not a systematic review.** The labels and visualizations should not be interpreted as exhaustive claims about the literature.

## Contributing

Contributions are welcome, including:

- Suggestions for missing or newly published papers.
- Corrections to bibliographic metadata or factual annotations.
- Revised classifications supported by evidence from the paper.
- Improvements to search, filtering, visualizations, or accessibility.

Please open a GitHub issue or submit a pull request to this repository. Changes are reviewed by maintainers before merging.

**To suggest a paper without editing anything**, open an issue with its link (arXiv, DOI, or publisher page) and,
if you like, a sentence on why it belongs. A maintainer will add it.

**To add a paper yourself**, either:
- add a row to `data/papers.csv` with the required columns (set `annotation_source` to `pending` if you leave the labels blank), or
- run the pipeline: `cd pipeline && python -m usil_pipeline add "<arXiv link, DOI, or title>"` (needs an Anthropic API key; see `pipeline/README.md`).

Then run `python scripts/check_papers.py` (it also runs automatically on your pull request) and open a pull request.

## Run locally

```bash
python -m http.server 8000
# Open http://localhost:8000/
```

Opening `index.html` directly from disk may not work because the application fetches `data/papers.csv`.

## Deployment: Cloudflare Workers

The public research map is deployed at **https://map.learntoworkwithyou.org/**, using Cloudflare Workers Static Assets connected to the `main` branch of the GitHub repository `learning-to-work-with-you/usil-research-map`.

For a static application with `index.html` in the repository root and no build step:

1. In Cloudflare, open **Workers & Pages → usil-research-map**.
2. Check the Git integration and ensure its production build tracks the `main` branch.
3. Configure static-asset deployment from the repository root. For a Wrangler-based setup, an example deploy command is `npx wrangler deploy --assets .`. `.assetsignore` keeps `pipeline/`, `scripts/`, and `.github/` out of the published site.
4. Under **Settings → Domains & Routes**, associate the Worker with the custom domain `map.learntoworkwithyou.org`.
5. Push changes to `main` to trigger deployment, then verify the deployment's **Ready** status and the live URL.

The Cloudflare configuration is separate from the main research initiative at `learntoworkwithyou.org`. Do **not** configure this repository to claim the main site's apex domain. GitHub Pages is an alternative host for this static site, but it is **not the current production host**.

## Citing a snapshot

The map is versioned; the current version is `v1`. The version and "updated" date shown on the site come from
`meta` in `data/schema.json`. To cite a fixed snapshot, update `meta`, create a matching Git release (for example
`v1`), and consider archiving the release on Zenodo for a DOI.

## License

- **Code** (site and pipeline): [MIT](LICENSE).
- **Annotations** in `data/` (`papers.csv`, `schema.json`): [CC BY 4.0](data/LICENSE.md). Please credit the
  USIL Research Map when you reuse them.

Contributions are accepted under these same terms. Summaries are original paraphrases; the papers themselves
remain under their authors' and publishers' terms.
