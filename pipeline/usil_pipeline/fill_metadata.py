"""Fill missing authors and venues in data/papers.csv (and pick up papers renamed on arXiv).

  python -m usil_pipeline fill-metadata                 # every row with a blank author or venue
  python -m usil_pipeline fill-metadata --keys hist_06  # specific rows
  python -m usil_pipeline fill-metadata --no-llm        # APIs only

Order: identifiers (arXiv, DOI) -> title search (OpenAlex, Crossref, Semantic Scholar) -> Claude reading the PDF's
first page, kept only where its source text is found on the page (Haiku; well under $0.01 per paper).
Only blank fields are filled. A paper renamed on arXiv gets its current title, with the old one kept in notes.
"""
import argparse, os, sys

from . import fulltext, metadata, publish
from .cli import load_env, pdf_dirs
from .metadata_llm import read_first_page

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pipeline/


def main(argv=None):
    ap = argparse.ArgumentParser(prog="usil_pipeline fill-metadata", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keys", default="", help="comma-separated keys (default: rows with a blank author or venue)")
    ap.add_argument("--no-llm", action="store_true", help="bibliographic APIs only")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--pdf-dirs", default=None, help="folders of local PDFs (default: pdfs/ plus PDF_DIRS from .env)")
    a = ap.parse_args(argv)
    os.chdir(HERE)
    load_env()
    cols, rows = publish.read_papers()
    want = {k.strip() for k in a.keys.split(",") if k.strip()}
    todo = ([r for r in rows if r["key"] in want] if want
            else [r for r in rows if not r["authors"].strip() or not r["venue"].strip()])
    if not todo:
        sys.exit("Nothing to fill.")
    llm = None
    if not a.no_llm and os.environ.get("ANTHROPIC_API_KEY"):
        from .llm import LLM
        llm = LLM(os.path.join(".cache", "llm"))
    local = fulltext.match_local_pdfs({r["key"]: r["title"] for r in todo}, [d for d in (a.pdf_dirs or pdf_dirs()).split(",") if d.strip()])
    report = []
    for r in todo:
        meta = metadata.resolve(r)
        notes = []
        if meta.get("renamed_from"):
            r["title"] = meta["title"]
            r["notes"] = "; ".join(x for x in [r.get("notes", ""), f"previously titled: {meta['renamed_from']}"] if x)
            notes.append(f"renamed -> {meta['title']}")
        elif any(i.startswith("title differs") for i in meta["metadata_issues"]):
            report.append((r["key"], "skipped", meta["metadata_issues"][0]))
            continue  # the link may point at another paper: don't copy its metadata
        filled = {}
        if not r["authors"].strip() and meta.get("authors"):
            filled["authors"] = meta["authors"]
        if not r["venue"].strip() and meta.get("venue"):
            filled["venue"] = meta["venue"]
        how = ", ".join(meta["sources"]) or "no API match"
        still = [c for c in ("authors", "venue") if not (r[c].strip() or filled.get(c))]
        if still and llm:
            ft = fulltext.fetch(r, meta, os.path.join(".cache", "pdf"), local_path=local.get(r["key"]))
            if ft["mode"] == "full-text":
                got = read_first_page(llm, a.model, r["key"], r["title"], ft["pages"])
                for c in still:
                    if got.get(c):
                        filled[c] = got[c]
                how += "; first page (verified)" if any(c in got for c in still) else "; first page had nothing verifiable"
            else:
                how += "; no PDF for a first-page read"
        r.update(filled)
        report.append((r["key"], ", ".join(f"{c}: {v[:60]}" for c, v in filled.items()) or "nothing found", "; ".join(notes + [how])))
    publish.write_papers(cols, rows)
    for k, what, how in report:
        print(f"{k:<16} {what}\n{'':<16} ({how})")
    ok, out = publish.run_check()
    print(out[-1] if out else "", "" if ok else "<- fix before committing")
    if llm:
        print(f"Claude cost: ~${llm.cost_estimate()}")


if __name__ == "__main__":
    main()
