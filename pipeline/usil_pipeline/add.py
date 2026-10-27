"""Add one paper to the map: look it up, read it with Claude, and append a finished row to data/papers.csv.

  python -m usil_pipeline add "https://arxiv.org/abs/2602.16173"
  python -m usil_pipeline add "10.1145/1031607.1031690" --pdf ~/papers/busybody.pdf
  python -m usil_pipeline add "Learning Personalized Agents from Human Feedback"
  python -m usil_pipeline add "<title>" --no-llm --category "Human–AI collaboration" --pillars "P1;P3" --summary "..."

Needs ANTHROPIC_API_KEY in pipeline/.env (about $0.10-0.20 per paper with Sonnet) unless --no-llm. Without full
text (paywalled papers: pass --pdf), the row is added as "pending" for a maintainer to annotate.
"""
import argparse, os, re, sys, unicodedata
from types import SimpleNamespace

from rapidfuzz import fuzz

from . import fulltext, metadata, publish, report
from .cli import DEFAULT_MODEL, load_env, pdf_dirs
from .pipeline import process

STOP = {"a", "an", "the", "on", "of", "for", "to", "in", "and", "with", "towards", "toward", "from", "how", "when", "what", "why", "is", "are", "do", "does"}
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pipeline/


def _ascii(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", _ascii(t)).strip()


def query_row(q):
    """A minimal row metadata.resolve understands, from an arXiv id/link, a DOI, a URL, or a title."""
    q = q.strip()
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", q)
    if m and ("arxiv" in q.lower() or re.fullmatch(r"(arxiv:)?\d{4}\.\d{4,5}(v\d+)?", q, re.I)):
        return {"title": "", "url": f"https://arxiv.org/abs/{m.group(1)}"}
    m = re.search(r"10\.\d{4,9}/\S+", q)
    if m:
        return {"title": "", "doi": m.group(0).rstrip("."), "url": f"https://doi.org/{m.group(0).rstrip('.')}"}
    if q.startswith("http"):
        return {"title": "", "url": q}
    return {"title": q, "url": ""}


def duplicate_of(meta, url, rows):
    title = _norm_title(meta.get("title"))
    aid, doi = meta.get("arxiv_id"), (meta.get("doi") or "").lower()
    for r in rows:
        u = (r.get("url") or "").lower()
        if (aid and aid in u) or (doi and doi in u) or (url and url.lower() == u):
            return r
        if title and fuzz.ratio(title, _norm_title(r.get("title"))) >= 94:
            return r
    return None


def make_key(meta, rows):
    first = re.split(r"[,;]| and ", meta.get("authors") or "")[0].strip()
    surname = re.sub(r"[^a-z]", "", _ascii(first.split()[-1])) if first else "anon"
    word = next((w for w in _norm_title(meta.get("title")).split() if w not in STOP), "paper")
    base = f"{surname}{meta.get('year') or ''}{word}"[:40]
    taken, key, i = {r["key"] for r in rows}, base, 0
    while key in taken:
        i += 1
        key = f"{base}{chr(97 + i)}"
    return key


def main(argv=None):
    ap = argparse.ArgumentParser(prog="usil_pipeline add", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paper", nargs="?", help="arXiv id or link, DOI, URL, or title")
    ap.add_argument("--from", dest="from_file", help="a file with one paper per line (e.g. from discovery promote); '#' starts a comment")
    ap.add_argument("--pdf", help="a local PDF of the paper (for paywalled papers)")
    ap.add_argument("--category", help="override the research area")
    ap.add_argument("--pillars", help="override the challenges, e.g. 'P1;P3'")
    ap.add_argument("--summary", help="override the summary")
    ap.add_argument("--no-llm", action="store_true", help="metadata only; the row is added as pending (needs --category, --pillars, --summary)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="out_add", help="where the evidence file goes")
    a = ap.parse_args(argv)
    if a.from_file:
        papers = [ln.split("#")[0].strip() for ln in open(os.path.expanduser(a.from_file), encoding="utf-8")]
        papers = [p for p in papers if p]
        rest = [x for x in (argv or []) if x not in (a.from_file, "--from")]
        for i, p in enumerate(papers, 1):
            print(f"\n[{i}/{len(papers)}] {p}")
            try:
                main([p] + rest)
            except SystemExit as e:  # duplicates and lookup failures: report and continue
                if e.code not in (None, 0):
                    print(e.code)
        return
    if not a.paper:
        ap.error("give a paper (link, DOI, or title) or --from FILE")
    os.chdir(HERE)  # config/ and .cache/ are relative to pipeline/
    load_env()

    cols, rows = publish.read_papers()
    q = query_row(a.paper)
    meta = metadata.resolve(q)
    if not meta.get("sources"):
        sys.exit("Could not find this paper in arXiv, Semantic Scholar, or Crossref. Try its arXiv link or DOI.")
    url = q["url"] or (f"https://arxiv.org/abs/{meta['arxiv_id']}" if meta.get("arxiv_id") else (f"https://doi.org/{meta['doi']}" if meta.get("doi") else ""))
    dup = duplicate_of(meta, url, rows)
    if dup:
        sys.exit(f"Already on the map: {dup['key']}: {dup['title']}")
    key = make_key(meta, rows)
    row = {c: "" for c in cols}
    row.update(key=key, title=meta.get("title") or q["title"], authors=meta.get("authors") or "", year=str(meta.get("year") or ""),
               venue=meta.get("venue") or "",
               url=url, annotation_source="pending")
    print(f"Found: {row['title']} ({row['year']}), {row['authors'][:80]}\nKey: {key}")

    ev = None
    if not a.no_llm:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY in pipeline/.env, or use --no-llm.")
        from .llm import LLM
        llm = LLM(os.path.join(".cache", "llm"))
        cfg = SimpleNamespace(stages={"meta", "extract", "map", "verify"}, force=set(), cache=".cache",
                              context=open("config/context.md", encoding="utf-8").read(), extract_model=a.model,
                              map_model=a.model, verify_model=a.model, min_quote_rate=0.7, dry_run=False,
                              local_pdfs={key: os.path.expanduser(a.pdf)} if a.pdf else
                              fulltext.match_local_pdfs({key: row["title"]}, pdf_dirs().split(",")))
        rec = process(row, cfg, llm, log=print)
        report.write([row], [rec], a.out)
        ev = publish.load_evidence(a.out, key)
        if not ev:
            print(f"No text could be read ({'; '.join(rec.get('errors') or []) or rec.get('text_mode')}). Pass --pdf to use a local copy.")
        print(f"Claude cost: ~${llm.cost_estimate()}")
    mp = (ev or {}).get("mapping") or {}
    categories = publish.vocab.schema()["categories"]
    row["category"] = a.category or (mp.get("category") if mp.get("category") in categories else "")
    row["pillars"] = a.pillars or ";".join(mp.get("pillars") or [])
    row["summary"] = a.summary or mp.get("summary_100w", "")
    changes = publish.apply_record(row, ev) if ev else []
    if ev and not changes and row["annotation_source"] == "pending":
        row["notes"] = f"read from the {ev.get('text_mode')}; labels left for a maintainer"
    missing = [c for c in ("category", "pillars", "summary") if not row[c]]
    if missing:
        sys.exit(f"Not added: {', '.join(missing)} could not be filled. Pass --{' --'.join(missing)}.")
    rows.append(row)
    publish.write_papers(cols, rows)
    ok, out = publish.run_check()
    status = "annotated from full text" if row["annotation_source"] == "pipeline-fulltext" else "added as pending (not yet annotated)"
    print(f"Added {key} to data/papers.csv, {status}: {row['category']}; {row['pillars']}")
    print(out[-1] if out else "", "" if ok else "<- run python scripts/check_papers.py and fix before committing")


if __name__ == "__main__":
    main()
