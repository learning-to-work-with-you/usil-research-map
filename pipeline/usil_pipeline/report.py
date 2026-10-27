"""Write outputs: updated map (CSV + JSON), review queue, per-paper evidence, run summary."""
import csv, json, os

MAP_FIELDS = ["what_is_learned", "per_user", "across_sessions", "interaction_decisions", "evaluates_transfer",
              "pillars", "category"]
EXTRA = ["paper_type", "settings", "user_signals", "user_representation", "preference_change", "personalization_unit",
         "evaluation_users", "evaluation_scale", "per_person_results", "interaction_cost_metrics", "decision_factors", "resources"]
NEW_COLS = ["cell_2x2", "closest_overlap", "remaining_question", "summary_100w"] + EXTRA + ["text_mode",
            "quote_verification_rate", "verifier_confidence", "needs_review", "review_reasons",
            "venue_api", "arxiv_journal_ref", "evidence_file"]


def _fmt(v):
    if isinstance(v, list):
        return ";".join(v)
    return "" if v is None else str(v)


def write(rows, records, out_dir, apply_changes=True):
    os.makedirs(os.path.join(out_dir, "evidence"), exist_ok=True)
    by_key = {r["key"]: r for r in records}
    base_cols = list(rows[0].keys()) if rows else []
    cols = base_cols + [c for c in NEW_COLS if c not in base_cols] + [f"prev_{f}" for f in MAP_FIELDS]
    out_rows, queue = [], []
    for row in rows:
        r = dict(row)
        rec = by_key.get(row["key"])
        if rec:
            meta = rec.get("meta") or {}
            mp = rec.get("mapping") or {}
            vf = rec.get("verification") or {}
            if mp:
                for f in MAP_FIELDS:
                    new = mp.get(f if f != "what_is_learned" else "what_is_learned")
                    if new is None:
                        continue
                    if f == "what_is_learned" and mp.get("what_is_learned_detail"):
                        new = f"{new}: {mp['what_is_learned_detail']}" if new == "other" else new
                    if _fmt(new) != (row.get(f) or ""):
                        r[f"prev_{f}"] = row.get(f, "")
                        if apply_changes:
                            r[f] = _fmt(new)
                r["usil_relation"] = f"{mp.get('closest_overlap','')} Open question: {mp.get('remaining_question','')}".strip() if apply_changes else row.get("usil_relation", "")
                r["closest_overlap"] = mp.get("closest_overlap", "")
                r["remaining_question"] = mp.get("remaining_question", "")
                r["summary_100w"] = mp.get("summary_100w", "")
                r["cell_2x2"] = mp.get("cell_2x2", "")
                for f in EXTRA:
                    r[f] = _fmt(mp.get(f))
            r["text_mode"] = rec.get("text_mode", "")
            r["quote_verification_rate"] = _fmt((rec.get("quote_stats") or {}).get("quote_verification_rate"))
            r["verifier_confidence"] = vf.get("overall_confidence", "")
            r["needs_review"] = "yes" if rec.get("needs_review") else ("no" if mp else "")
            r["review_reasons"] = " || ".join(rec.get("review_reasons", []) + rec.get("errors", []))
            r["venue_api"] = meta.get("venue_api", "")
            r["arxiv_journal_ref"] = meta.get("arxiv_journal_ref", "")
            if rec.get("evidence"):
                fn = f"evidence/{row['key']}.json"
                json.dump({k: rec.get(k) for k in ["key", "text_mode", "text_source", "quote_stats", "evidence",
                                                   "mapping", "verification", "review_reasons"]} | {"metadata": {k: meta.get(k) for k in ["title", "authors", "year", "venue_api", "arxiv_id", "doi", "arxiv_journal_ref", "arxiv_comment", "sources", "metadata_issues"]}},
                          open(os.path.join(out_dir, fn), "w"), indent=1, ensure_ascii=False)
                r["evidence_file"] = fn
            if rec.get("needs_review") or rec.get("errors"):
                queue.append({"key": row["key"], "title": row.get("title", ""), "flag": "error" if rec.get("errors") else (
                              "verifier: unsupported" if any("unsupported" in x for x in rec.get("review_reasons", [])) else "changed"),
                              "reasons": r["review_reasons"], "evidence_file": r.get("evidence_file", "")})
        out_rows.append(r)

    with open(os.path.join(out_dir, "papers_full.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    json.dump(out_rows, open(os.path.join(out_dir, "papers_full.json"), "w"), indent=1, ensure_ascii=False)
    # most important first: verifier-flagged, then errors (no text), then plain label changes
    pri = {"verifier: unsupported": 0, "error": 1, "changed": 2}
    queue.sort(key=lambda q: pri.get(q["flag"], 3))
    with open(os.path.join(out_dir, "review_queue.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["key", "title", "flag", "reasons", "evidence_file"])
        w.writeheader()
        w.writerows(queue)
    return len(out_rows), len(queue)
