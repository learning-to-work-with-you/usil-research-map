"""Build data/papers.json (read by the site) and data/papers.csv (download) from the source files.

Sources (edit these, then rerun `python scripts/build_data.py`):
  data/source/usil_literature_map.csv  editorial map: one row per paper, maintained by hand
  data/source/verification.json        output of the full-text verification pipeline (optional)
  data/source/table1.json              ratings checked against full text for the position paper's Table 1
"""
import csv
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "source")

CATEGORY_ORDER = [
    "Mixed-initiative & autonomy", "Human–AI collaboration", "Preference & reward learning",
    "Active elicitation & feedback", "User modeling & personalization", "Agent evaluation & benchmarks",
    "Memory & procedural learning", "Continual / online learning",
]

# Interaction decisions are recorded as free text; map them to a small vocabulary.
DECISION_RULES = [
    ("Ask or clarify", r"\bask|clarif|elicit|question|query"),
    ("Confirm", r"confirm|approv|permission|verify|sign.?off"),
    ("Act or delegate", r"\bact\b|act \(|delegat|autonom|assist|do nothing|grant|initiative"),
    ("Suggest", r"suggest|proactiv|recommend"),
    ("Explain", r"explain"),
    ("Interrupt or notify", r"interrupt|warn|notif"),
    ("Intervene or take over", r"interven|takeover|take over"),
    ("Defer or return control", r"defer|return.?control|leave it to the user|withhold"),
    ("Communicate", r"communicat"),
]


def level(value):
    """Collapse a free-text rating ('yes (portable)', 'partial (style-level)') to a level."""
    v = (value or "").strip().lower()
    if not v:
        return "not established"
    for lv in ("yes", "partial", "not established", "no", "n/a"):
        if v.startswith(lv):
            return lv
    return "not established"


def decisions(value):
    v = (value or "").strip().lower()
    if not v or v.startswith("not verified") or v.startswith("not established"):
        return None  # unknown
    if v.startswith("none"):
        return []
    found = [name for name, pat in DECISION_RULES if re.search(pat, v)]
    return found or ["Other"]


def cell(per_user, decs):
    who = {"yes": "individual", "partial": "individual", "no": "population", "n/a": "population"}.get(per_user)
    what = None if decs is None else ("procedure" if decs else "outcome")
    return f"{what}_{who}" if who and what else None


def main():
    rows = list(csv.DictReader(open(os.path.join(SRC, "usil_literature_map.csv"), encoding="utf-8-sig")))
    ver_path = os.path.join(SRC, "verification.json")
    ver = {r["key"]: r for r in json.load(open(ver_path, encoding="utf-8"))} if os.path.exists(ver_path) else {}
    t1_path = os.path.join(SRC, "table1.json")
    table1 = {r["key"]: r for r in json.load(open(t1_path, encoding="utf-8"))} if os.path.exists(t1_path) else {}

    papers = []
    for r in rows:
        k = r["key"]
        v = ver.get(k, {})
        full = v.get("text_mode") in ("full-text", "full-text-html")
        decs = decisions(r.get("interaction_decisions"))
        t1 = table1.get(k)
        pu = t1["user_evidence"] if t1 else level(r.get("per_user"))
        sessions = t1["longitudinal"] if t1 else level(r.get("across_sessions"))
        transfer = t1["cross_task_transfer"] if t1 else level(r.get("evaluates_transfer"))
        tier = (r.get("cite_tier") or "").strip()
        year = int(r["year"]) if (r.get("year") or "").strip().isdigit() else None
        papers.append({
            "id": k,
            "title": r["title"].strip(),
            "authors": (r.get("authors") or "").strip(),
            "year": year,
            "venue": (r.get("venue") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "category": r.get("category", "").strip(),
            "pillars": [p.strip() for p in (r.get("pillars") or "").split(";") if p.strip()],
            "tier": tier,
            "cited": tier in ("A", "A-"),
            "cite_section": (r.get("cite_section") or "").strip(),
            "cite_role": (r.get("cite_role") or "").strip(),
            "summary": (v.get("summary") if full and v.get("summary") else r.get("summary", "")).strip(),
            "summary_source": "full text" if full and v.get("summary") else "catalog",
            "what_is_learned": (r.get("what_is_learned") or "").strip(),
            "user_evidence": (r.get("user_evidence") or "").strip(),
            "per_user": {"level": pu, "detail": (r.get("per_user") or "").strip()},
            "across_sessions": {"level": sessions, "detail": (r.get("across_sessions") or "").strip()},
            "transfer": {"level": transfer, "detail": (r.get("evaluates_transfer") or "").strip()},
            "decisions": decs if decs is not None else [],
            "decisions_known": decs is not None,
            "decisions_raw": (r.get("interaction_decisions") or "").strip(),
            "cell": cell(pu, decs),
            "relation": (r.get("usil_relation") or "").strip(),
            "closest_overlap": (v.get("closest_overlap") or "").strip() if full else "",
            "remaining_question": (v.get("remaining_question") or "").strip() if full else "",
            "provenance": {
                "text_mode": v.get("text_mode") or "catalog only",
                "quote_verification_rate": v.get("quote_verification_rate"),
                "verifier_confidence": v.get("verifier_confidence") or "",
                "needs_review": v.get("needs_review") == "yes",
                "table1_verified": k in table1,
            },
            "table1": table1.get(k),
            "core": (r.get("paper_core") or "").strip(),
            "source": (r.get("source") or "").strip(),
        })

    papers.sort(key=lambda p: (CATEGORY_ORDER.index(p["category"]) if p["category"] in CATEGORY_ORDER else 99, -(p["year"] or 0), p["title"]))
    meta = {
        "snapshot": "v0.2",
        "papers": len(papers),
        "categories": CATEGORY_ORDER,
        "table1_order": [r["key"] for r in json.load(open(t1_path, encoding="utf-8"))] if table1 else [],
    }
    json.dump({"meta": meta, "papers": papers}, open(os.path.join(ROOT, "data", "papers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    cols = ["id", "title", "authors", "year", "venue", "category", "pillars", "cited", "per_user", "across_sessions",
            "transfer", "decisions", "cell", "summary", "relation", "url"]
    with open(os.path.join(ROOT, "data", "papers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in papers:
            w.writerow([p["id"], p["title"], p["authors"], p["year"], p["venue"], p["category"], ";".join(p["pillars"]),
                        "yes" if p["cited"] else "no", p["per_user"]["level"], p["across_sessions"]["level"],
                        p["transfer"]["level"], ";".join(p["decisions"]) if p["decisions_known"] else "not coded",
                        p["cell"] or "unclassified", p["summary"], p["relation"], p["url"]])
    print(f"wrote {len(papers)} papers")


if __name__ == "__main__":
    main()
