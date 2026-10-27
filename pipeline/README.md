# Map pipeline

Reads papers with Claude and fills in `../data/papers.csv`: the labels, a summary, and the study-design
columns, each backed by verbatim quotes that are checked against the PDF. It also finds candidate papers
through citations. You don't need it to contribute: a row with the required columns is enough (see the
main README).

```text
add       paper link / DOI / title -> metadata, full text, Claude reading, quote check -> one new row
fill-metadata  blank authors / venues -> APIs, then a verified first-page read
run       re-read papers already on the map (all, --pending, or --keys) -> a run folder
publish   merge a run folder into ../data/papers.csv; writes a review spreadsheet with every change
discovery find candidate papers through the map's citations (free; OpenAlex + Semantic Scholar)
```

## Setup (once)

Needs Python 3.10 or later. Run every command from inside `pipeline/`.

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # put your key in .env: ANTHROPIC_API_KEY=sk-ant-...
```

`.env`, `.cache/` (downloaded PDFs, cached Claude results), and output folders are git-ignored.
PDFs and full texts are never committed; only labels and short quotes reach the repository.

## Local PDFs

The pipeline downloads open-access PDFs itself (arXiv, Semantic Scholar, ACL Anthology, OpenReview). For any other
paper, save the PDF into `pipeline/pdfs/`:

- Any file name works: PDFs are matched to papers by the title on their first pages.
- If a PDF's title can't be read (scanned, or set as an image), name the file `<key>.pdf`, e.g. `hist_29.pdf`.
- `pipeline/pdfs/` is git-ignored: PDFs are never committed (copyright, and size).
- To also use folders elsewhere on your computer, list them in `.env`: `PDF_DIRS=~/papers,~/Downloads/reading`.

## Add a paper

```bash
python -m usil_pipeline add "https://arxiv.org/abs/2602.16173"
python -m usil_pipeline add "10.1145/1031607.1031690" --pdf ~/papers/busybody.pdf   # paywalled: use your copy
python -m usil_pipeline add --from out_discovery/to_add.txt                        # one paper per line
```

It refuses papers already on the map (same arXiv id, DOI, or title), creates the key, and appends a row.
Read from full text with at least 70% of quotes found, the row is `pipeline-fulltext`; otherwise it is added
as `pending` for a maintainer. Cost: about $0.10-0.20 per paper with Sonnet. Then run
`python ../scripts/check_papers.py` and open a pull request.

## Fill missing authors and venues

```bash
python -m usil_pipeline fill-metadata              # every row with a blank author or venue
python -m usil_pipeline fill-metadata --keys hist_06
```

Looks papers up by arXiv ID or DOI, then by title (OpenAlex, Crossref, Semantic Scholar; titles are compared
after removing HTML and punctuation). Unpublished preprints get `arXiv preprint arXiv:<id>`. A paper renamed on
arXiv gets its current title, with the old one in `notes`. If nothing matches, Claude (Haiku) reads the PDF's
first page, and an answer is kept only if its source text is found on that page. Only blank fields are filled.

## Re-read papers already on the map

```bash
python -m usil_pipeline --dry-run                       # free: which papers have text, cost estimate
python -m usil_pipeline --pending --out out_pending     # papers not yet annotated
python -m usil_pipeline --keys liang2026pahf --out out_check
python -m usil_pipeline.publish --run out_pending       # merge into ../data/papers.csv
```

A run folder holds `papers_full.csv` (every column the pipeline produces, including the verifier's notes),
`evidence/<key>.json` (answers and quotes with page numbers), and `review_queue.csv`. `publish` keeps the
editorial columns (title, category, challenges) as they are, takes labels only from full text with checked
quotes, never replaces a definite value with `not-stated`, and lists every change in `papers_review.xlsx`.

Useful options: `--pdf-dirs` (replaces the default `pdfs/` + `PDF_DIRS` folders), `--extract-model / --map-model /
--verify-model` (default Sonnet), `--force map,verify` after editing prompts. `config/context.md` is the
research context given to Claude; editing it re-runs only the mapping and verification steps.

## Find candidate papers

```bash
python -m usil_pipeline.discovery discover   # -> out_discovery/review_queue.md (top candidates, with reasons)
# mark decision = include in out_discovery/review_queue.csv, then:
python -m usil_pipeline.discovery record
python -m usil_pipeline.discovery promote    # -> out_discovery/to_add.txt
python -m usil_pipeline add --from out_discovery/to_add.txt
```

Discovery follows citations backward from every map paper and forward from those that learn from an
individual's evidence, then ranks candidates with a transparent rubric (`config/discovery.json`). Set
`OPENALEX_API_KEY` in `.env` for full runs.

## How values are written

Claude's answers are translated into the allowed values in `../data/schema.json` by `usil_pipeline/vocab.py`.
To add a value, add it to the schema first, then to `vocab.py` and `schemas.py`.

## Tests

```bash
python -m pytest tests      # offline; no network or API calls
```
