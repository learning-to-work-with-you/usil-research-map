"""Per-paper pipeline: metadata -> full text -> evidence (quotes) -> quote check -> mapping -> verification."""
import json, os
from . import metadata, fulltext, prompts
from .quotes import check_evidence
from .schemas import Evidence, Mapping, Verification

COMPARE = ["per_user", "across_sessions", "evaluates_transfer", "category", "pillars"]


def _prev(row):
    return {k: row.get(k, "") for k in ["category", "what_is_learned", "per_user", "across_sessions",
                                        "interaction_decisions", "evaluates_transfer", "pillars",
                                        "usil_relation", "open_question"]}


def _diff(row, mapping):
    out = []
    for k in COMPARE:
        old = (row.get(k) or "").strip()
        new = mapping.get(k)
        if k == "pillars":
            o = {x.strip() for x in old.replace(",", ";").split(";") if x.strip()}
            n = set(new or [])
            if o and o != n:
                out.append(f"pillars: {';'.join(sorted(o))} -> {';'.join(sorted(n))}")
            continue
        if not old:
            continue
        o, n = old.lower(), str(new).lower()
        if k == "per_user" and o.startswith("partial"):
            o = "partial"
        o = o.replace("not-stated", "not established")
        if n not in o and o not in n:
            out.append(f"{k}: {old} -> {new}")
    return out


def _cached_json(path, fn):
    if os.path.exists(path):
        v = json.load(open(path))
        if v.get("sources"):
            return v
    v = fn()
    if v.get("sources"):  # a failed lookup (rate limit, outage) is retried next run, not cached
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(v, open(path, "w"), indent=1, ensure_ascii=False)
    return v


def process(row, cfg, llm, log=print):
    key = row["key"]
    rec = {"key": key, "errors": []}

    meta = _cached_json(os.path.join(cfg.cache, "meta", f"{key}.json"), lambda: metadata.resolve(row))
    rec["meta"] = meta
    if cfg.stages == {"meta"}:
        return rec

    ft = fulltext.fetch(row, meta, os.path.join(cfg.cache, "pdf"), local_path=(cfg.local_pdfs or {}).get(key))
    rec["text_mode"], rec["text_source"] = ft["mode"], ft["source_url"]
    rec["text_chars"] = len(ft["text"])
    if cfg.dry_run or ft["mode"] == "none":
        if ft["mode"] == "none":
            rec["errors"].append("no text or abstract available")
        return rec

    title, year = meta.get("title") or row["title"], meta.get("year") or row.get("year")
    venue = row.get("venue", "")

    if "extract" in cfg.stages:
        ev, cached = llm.structured(
            stage="extract", paper_key=key, model=cfg.extract_model,
            system=prompts.EXTRACT_SYSTEM,
            user=prompts.EXTRACT_USER.format(title=title, year=year, mode=ft["mode"], text=ft["text"]),
            schema=Evidence, max_tokens=16000, force="extract" in cfg.force)
        ev, qstats = check_evidence(ev, ft["pages"])
        rec["evidence"], rec["quote_stats"] = ev, qstats
        log(f"  [{key}] extract {'(cached)' if cached else ''} quotes verified {qstats['quotes_verified']}/{qstats['quotes_total']}")
    else:
        return rec

    ev_json = json.dumps(rec["evidence"], indent=1, ensure_ascii=False)
    if "map" in cfg.stages:
        mp, cached = llm.structured(
            stage="map", paper_key=key, model=cfg.map_model,
            system=prompts.MAP_SYSTEM.format(context=cfg.context),
            user=prompts.MAP_USER.format(title=title, year=year, venue=venue, mode=ft["mode"], evidence=ev_json),
            schema=Mapping, max_tokens=8000, force="map" in cfg.force)
        rec["mapping"] = mp
        rec["changes_vs_csv"] = _diff(row, mp)
    else:
        return rec

    if "verify" in cfg.stages:
        vf, cached = llm.structured(
            stage="verify", paper_key=key, model=cfg.verify_model,
            system=prompts.VERIFY_SYSTEM.format(context=cfg.context),
            user=prompts.VERIFY_USER.format(title=title, year=year, mode=ft["mode"], evidence=ev_json,
                                            mapping=json.dumps(rec["mapping"], indent=1, ensure_ascii=False),
                                            previous=json.dumps(_prev(row), indent=1, ensure_ascii=False)),
            schema=Verification, max_tokens=6000, force="verify" in cfg.force)
        rec["verification"] = vf

    # ---- review decision ----
    reasons = []
    if meta.get("metadata_issues"):
        reasons += meta["metadata_issues"]
    if rec["text_mode"] != "full-text":
        reasons.append(f"text mode: {rec['text_mode']}")
    rate = (rec.get("quote_stats") or {}).get("quote_verification_rate")
    if rate is not None and rate < cfg.min_quote_rate:
        reasons.append(f"low quote verification rate {rate}")
    vf = rec.get("verification") or {}
    bad = [c["field"] for c in vf.get("checks", []) if c["verdict"] == "unsupported"]
    if bad:
        reasons.append("verifier: unsupported " + ", ".join(bad))
    if vf.get("needs_human_review") and vf.get("review_reason"):
        reasons.append("verifier: " + vf["review_reason"])
    if rec.get("changes_vs_csv"):
        reasons.append("changed vs CSV: " + " | ".join(rec["changes_vs_csv"]))
    rec["needs_review"] = bool(reasons)
    rec["review_reasons"] = reasons
    return rec
