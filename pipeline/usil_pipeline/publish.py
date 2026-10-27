"""Merge a pipeline run into data/papers.csv (the map's one data file) and write a review spreadsheet.

  python -m usil_pipeline.publish --run out_v1

For each paper the run read, using its evidence file (out_v1/evidence/<key>.json):
- Editorial columns stay as they are: key, title, authors, year, venue, url, category, pillars.
- Labels and text (per_user, interaction_decisions, across_sessions, evaluates_transfer, what_is_learned, summary,
  usil_relation, open_question) and the study columns are taken from the pipeline only when the paper was read in
  FULL TEXT and at least --min-quote-rate of its quotes were found in the PDF. A field the verifier marked
  unsupported keeps its current value, and a definite value is never replaced by "not-stated".
- Such rows get annotation_source = pipeline-fulltext, annotated_on = today, quotes_verified = the quote rate.
Every change is listed on the spreadsheet's "Changes" sheet. Review state (verifier notes) stays in the run folder.
"""
import argparse, csv, datetime, json, os, shutil, subprocess, sys

from . import vocab

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAPERS = os.path.join(ROOT, "data", "papers.csv")
LEVELS = ["per_user", "across_sessions", "evaluates_transfer"]


def load_evidence(run, key):
    p = os.path.join(run, "evidence", f"{key}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def pipeline_values(ev):
    """Public column values from one evidence file (pipeline wording -> schema values)."""
    mp = ev.get("mapping") or {}
    out = {}
    for c in LEVELS:
        lv, _ = vocab.level(mp.get(c))
        out[c] = lv or "not-stated"
    decs, _ = vocab.decisions(";".join(mp.get("interaction_decisions") or []))
    out["interaction_decisions"] = ";".join(decs) or "not-stated"
    learned = mp.get("what_is_learned") or ""
    out["what_is_learned"] = mp.get("what_is_learned_detail") if learned == "other" and mp.get("what_is_learned_detail") else learned
    out["summary"] = mp.get("summary_100w", "")
    out["usil_relation"] = mp.get("closest_overlap", "")
    out["open_question"] = mp.get("remaining_question", "")
    for c in vocab.STUDY:
        out[c] = vocab.study_value(c, mp.get(c))
    out["evaluation_scale"] = (mp.get("evaluation_scale") or "").strip()
    out["resources"] = vocab.study_value("resources", mp.get("resources"))
    return out


def unsupported(ev):
    return {c["field"] for c in ((ev.get("verification") or {}).get("checks") or []) if c.get("verdict") == "unsupported"}


def trusted(ev, min_quote_rate):
    rate = (ev.get("quote_stats") or {}).get("quote_verification_rate")
    return ev.get("text_mode") == "full-text" and rate is not None and rate >= min_quote_rate


def apply_record(row, ev, min_quote_rate=0.7, today=None):
    """Update one papers.csv row in place from its evidence. Returns the list of changes."""
    if not ev or not trusted(ev, min_quote_rate):
        return []
    new, bad, changes = pipeline_values(ev), unsupported(ev), []
    for c, val in new.items():
        old = (row.get(c) or "").strip()
        if not val or val == old or c in bad:
            continue
        if val == "not-stated" and old and old != "not-stated":
            continue  # the pipeline being unsure does not erase a definite value
        changes.append({"key": row["key"], "title": row.get("title", ""), "field": c, "old": old, "new": val})
        row[c] = val
    row["annotation_source"] = "pipeline-fulltext"
    row["annotated_on"] = today or datetime.date.today().isoformat()
    row["quotes_verified"] = str((ev.get("quote_stats") or {}).get("quote_verification_rate", ""))
    for c in ("per_user", "across_sessions", "evaluates_transfer", "interaction_decisions"):
        row[c] = row.get(c) or "not-stated"
    return changes


def read_papers(path=PAPERS):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return [c["name"] for c in vocab.schema()["columns"]], rows


def write_papers(cols, rows, path=PAPERS):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)


def run_check():
    """scripts/check_papers.py, the same check pull requests run."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_papers.py")], capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip().splitlines()


def write_xlsx(path, rows, changes, run):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    head, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="265C4C")

    def table(ws, recs, cols, widths):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = head, fill
        for r in recs:
            ws.append([r.get(c, "") for c in cols])
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = ws.dimensions
        for i, c in enumerate(cols, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(c, 18)

    review = []
    for r in rows:
        ev = load_evidence(run, r["key"]) or {}
        review.append({**r, "unsupported_fields": ";".join(sorted(unsupported(ev))) if ev else "",
                       "review_reasons": " || ".join(ev.get("review_reasons") or []) if ev else ""})
    cols = list(rows[0].keys()) + ["unsupported_fields", "review_reasons"]
    wide = {"key": 24, "title": 50, "summary": 60, "usil_relation": 50, "open_question": 40, "review_reasons": 60}
    table(wb.active, review, cols, wide)
    wb.active.title = "Papers"
    table(wb.create_sheet("Changes"), changes, ["key", "title", "field", "old", "new"], {"title": 45, "old": 50, "new": 50})
    g = wb.create_sheet("Field guide")
    table(g, [{"column": c["name"], "group": c["group"], "meaning": c.get("help", ""),
               "allowed values": "; ".join(c["values"]) if isinstance(c.get("values"), (list, dict)) else ""}
              for c in vocab.schema()["columns"]], ["column", "group", "meaning", "allowed values"],
          {"column": 24, "meaning": 70, "allowed values": 80})
    wb.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="usil_pipeline.publish", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="out_v1", help="a pipeline output folder (with evidence/)")
    ap.add_argument("--min-quote-rate", type=float, default=0.7)
    ap.add_argument("--xlsx", help="review spreadsheet (default: <run>/papers_review.xlsx)")
    a = ap.parse_args(argv)
    cols, rows = read_papers()
    shutil.copy(PAPERS, os.path.join(a.run, "papers.before_publish.csv"))  # undo point
    changes = []
    for r in rows:
        changes += apply_record(r, load_evidence(a.run, r["key"]), a.min_quote_rate)
    write_papers(cols, rows)
    xlsx = a.xlsx or os.path.join(a.run, "papers_review.xlsx")
    write_xlsx(xlsx, rows, changes, a.run)
    ok, out = run_check()
    print(f"{len(changes)} field changes across {len({c['key'] for c in changes})} papers. Wrote {PAPERS} and {xlsx}.")
    print(f"Undo: copy {a.run}/papers.before_publish.csv over data/papers.csv.")
    print(out[-1] if out else "", "" if ok else "  <- fix these before committing (python scripts/check_papers.py)")


if __name__ == "__main__":
    main()
