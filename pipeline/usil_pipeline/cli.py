"""Command-line entry point.

Examples (run from pipeline/; reads ../data/papers.csv)
  python -m usil_pipeline add "https://arxiv.org/abs/2602.16173"     # add one paper to the map
  python -m usil_pipeline fill-metadata                               # fill blank authors / venues
  python -m usil_pipeline --dry-run                                   # free: downloads + cost estimate
  python -m usil_pipeline --pending --out out_pending                 # annotate the papers marked pending
  python -m usil_pipeline --keys liang2026pahf,shukla2026hedwig --out out_check
  python -m usil_pipeline.publish --run out_pending                   # merge a run into ../data/papers.csv
"""
import argparse, csv, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

from .pipeline import process
from . import report

DEFAULT_MODEL = "claude-sonnet-5-5"


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def pdf_dirs():
    """Local PDF folders: pipeline/pdfs (git-ignored) plus any listed in PDF_DIRS in .env, comma-separated."""
    return ",".join(["pdfs"] + [d.strip() for d in os.environ.get("PDF_DIRS", "").split(",") if d.strip()])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["add"]:
        from .add import main as add_main
        return add_main(argv[1:])
    if argv[:1] == ["fill-metadata"]:
        from .fill_metadata import main as fill_main
        return fill_main(argv[1:])
    ap = argparse.ArgumentParser(prog="usil_pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "..", "..", "data", "papers.csv"),
                    help="CSV with at least key,title,year,url (default: the map's data/papers.csv)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--context", default="config/context.md", help="research context injected into stages 2-3")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--keys", default="", help="comma-separated keys to process")
    ap.add_argument("--limit", type=int, default=0, help="process only the first N rows")
    ap.add_argument("--pending", action="store_true", help="only rows with annotation_source = pending")
    ap.add_argument("--stages", default="meta,extract,map,verify")
    ap.add_argument("--force", default="", help="comma-separated stages to recompute despite cache (extract,map,verify)")
    ap.add_argument("--extract-model", default=DEFAULT_MODEL)
    ap.add_argument("--map-model", default=DEFAULT_MODEL)
    ap.add_argument("--verify-model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--min-quote-rate", type=float, default=0.7)
    ap.add_argument("--pdf-dirs", default=None,
                    help="comma-separated folders of local PDFs, used before downloading (default: pdfs/ plus PDF_DIRS from .env)")
    ap.add_argument("--dry-run", action="store_true", help="metadata + text download only; prints a token/cost estimate")
    ap.add_argument("--no-apply", action="store_true", help="keep original CSV values; only add new columns")
    a = ap.parse_args(argv)

    load_env()
    rows = list(csv.DictReader(open(a.input, encoding="utf-8")))
    if not rows or "key" not in rows[0]:
        sys.exit("input CSV needs a 'key' column")
    sel = rows
    if a.keys:
        want = {k.strip() for k in a.keys.split(",")}
        sel = [r for r in rows if r["key"] in want]
    if a.pending:
        sel = [r for r in sel if r.get("annotation_source") == "pending"]
    if a.limit:
        sel = sel[: a.limit]

    stages = {s.strip() for s in a.stages.split(",") if s.strip()}
    cfg = SimpleNamespace(stages=stages, force={s.strip() for s in a.force.split(",") if s.strip()},
                          cache=a.cache, context=open(a.context, encoding="utf-8").read(),
                          extract_model=a.extract_model, map_model=a.map_model, verify_model=a.verify_model,
                          min_quote_rate=a.min_quote_rate, dry_run=a.dry_run, local_pdfs={})
    if a.pdf_dirs is None:
        a.pdf_dirs = pdf_dirs()
    if a.pdf_dirs and "meta" != a.stages:
        from .fulltext import match_local_pdfs
        cfg.local_pdfs = match_local_pdfs({r["key"]: r.get("title", "") for r in sel}, [d.strip() for d in a.pdf_dirs.split(",") if d.strip()])
        print(f"Local PDFs matched: {len(cfg.local_pdfs)}")

    llm = None
    if not a.dry_run and stages - {"meta"}:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY (in your shell or a .env file).")
        from .llm import LLM
        llm = LLM(os.path.join(a.cache, "llm"))

    print(f"Processing {len(sel)} of {len(rows)} papers | stages={sorted(stages)} | dry_run={a.dry_run}")
    t0, records = time.time(), []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process, r, cfg, llm): r["key"] for r in sel}
        for i, f in enumerate(as_completed(futs), 1):
            k = futs[f]
            try:
                rec = f.result()
            except Exception as e:  # keep going; record the failure
                rec = {"key": k, "errors": [f"{type(e).__name__}: {e}"]}
            records.append(rec)
            flag = "REVIEW" if rec.get("needs_review") else ("ERROR" if rec.get("errors") else "ok")
            print(f"[{i}/{len(sel)}] {k}: {rec.get('text_mode','-')} {flag}")

    os.makedirs(a.out, exist_ok=True)
    summary = {"papers": len(sel), "seconds": round(time.time() - t0, 1),
               "text_modes": {m: sum(1 for r in records if r.get("text_mode") == m) for m in ["full-text", "abstract-only", "none"]},
               "metadata_issues": {r["key"]: r["meta"]["metadata_issues"] for r in records if (r.get("meta") or {}).get("metadata_issues")},
               "errors": {r["key"]: r["errors"] for r in records if r.get("errors")}}
    if a.dry_run:
        chars = sum(r.get("text_chars", 0) for r in records)
        tok = chars / 3.5
        summary["estimate"] = {"input_tokens_extract": int(tok),
                               "approx_cost_usd_sonnet_all_stages": round(tok * 2.0 / 1e6 * 1.25 + len(sel) * 0.06, 2)}
        print(json.dumps(summary, indent=1))
        json.dump(summary, open(os.path.join(a.out, "dry_run_summary.json"), "w"), indent=1)
        return
    if llm:
        summary["usage"] = llm.usage
        summary["approx_cost_usd"] = llm.cost_estimate()
    n, q = report.write(rows if not (a.keys or a.limit or a.pending) else sel, records, a.out, apply_changes=not a.no_apply)
    summary["review_queue"] = q
    json.dump(summary, open(os.path.join(a.out, "run_summary.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: summary[k] for k in summary if k in ("papers", "text_modes", "review_queue", "approx_cost_usd")}, indent=1))
    print(f"Wrote {n} rows -> {a.out}/papers_full.csv ; review queue: {q} -> {a.out}/review_queue.csv")


if __name__ == "__main__":
    main()
