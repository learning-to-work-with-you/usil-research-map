"""Discovery run: seeds -> citation neighbors -> unique candidates -> ranked review queue."""
import csv, datetime, json, os, re, time, unicodedata

from rapidfuzz import fuzz

from .identity import Pool, SeedIndex, keys_of, norm_title, seed_identity, stable_id
from .rank import TIER_MEANING, Rubric, suggest_tier, why
from .sources import Cache, OpenAlex, SemanticScholar

QUEUE_COLS = ["rank", "id", "score", "suggested_tier", "suggested_pillars", "title", "year", "venue", "url",
              "why", "new_this_run", "decision", "tier", "pillars", "notes"]
DECISION_COLS = ["id", "title", "decision", "tier", "pillars", "notes", "decided_on"]


def is_core(row):
    """Papers whose citers are worth following forward: those that learn from an individual's evidence."""
    return (row.get("per_user") or "").strip().lower().startswith(("yes", "partial"))


def load_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []


def resolve_seeds(rows, oa, log):
    """Find each map paper in OpenAlex: by DOI (incl. arXiv DOIs), then by title."""
    found = {}
    ident = {r["key"]: seed_identity(r) for r in rows}
    want = {}
    for k, s in ident.items():
        for d in filter(None, [s["doi"], f"10.48550/arxiv.{s['arxiv_id']}" if s["arxiv_id"] else None]):
            want.setdefault(d.lower(), []).append(k)
    for rec in oa.by_dois(list(want)):
        for k in want.get((rec["doi"] or "").lower(), []):
            found.setdefault(k, rec)
    for n, r in enumerate(rows, 1):
        if n % 20 == 0:
            print(f"      title lookups {n}/{len(rows)}", flush=True)
        k = r["key"]
        # Prefer a record that carries references: arXiv records often have none, the published one does.
        if k in found and found[k]["referenced_works"]:
            continue
        best = None
        for cand in oa.search_title(r.get("title", "")):
            sim = fuzz.ratio((cand["title"] or "").lower(), (r.get("title") or "").lower())
            yr_ok = not cand["year"] or not str(r.get("year", "")).isdigit() or abs(cand["year"] - int(r["year"])) <= 2
            if sim >= 90 and yr_ok and (best is None or len(cand["referenced_works"]) > len(best["referenced_works"])):
                best = cand
        if best and (k not in found or len(best["referenced_works"]) > len(found[k]["referenced_works"])):
            found[k] = best
    log["seeds_resolved_openalex"] = len(found)
    log["seeds_unresolved"] = sorted(k for k in ident if k not in found)
    return found


def discover(cfg, seeds_path, out, cache_dir, registry_path, decisions_path, forward=None, no_s2=False):
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    today = datetime.date.today().isoformat()
    log = {"date": today, "seeds_file": seeds_path}
    rows = [r for r in load_csv(seeds_path) if r.get("key") and r.get("title")]
    log["seeds"] = len(rows)
    by_key = {r["key"]: r for r in rows}
    seed_titles = {r["key"]: short_title(r["title"]) for r in rows}

    cache = Cache(cache_dir)
    oa, s2 = OpenAlex(cache), SemanticScholar(cache)
    seed_index = SeedIndex([seed_identity(r) for r in rows])

    print(flush=True); print(f"[1/5] Resolving {len(rows)} map papers in OpenAlex ...")
    resolved = resolve_seeds(rows, oa, log)
    for k, rec in resolved.items():
        seed_index.add(rec, key=k)

    pool = Pool()
    print("[2/5] Backward citations (what the map's papers cite) ...")
    cited_by = {}
    for k, rec in resolved.items():
        for ref in rec["referenced_works"]:
            cited_by.setdefault(ref, set()).add(k)
    for rec in oa.by_ids(list(cited_by)):
        rec.update(seed_citers=cited_by.get(rec["openalex_id"], set()), routes={"backward:openalex"})
        pool.add(rec)
    log["backward_openalex_refs"] = len(cited_by)

    no_refs = [k for k in by_key if k not in resolved or not resolved[k]["referenced_works"]]
    s2_done = 0
    if not no_s2:
        cap = cfg["budget"]["max_s2_reference_lookups"]
        print(f"      Semantic Scholar references for {min(cap, len(no_refs))} papers OpenAlex has no list for", flush=True)
        for n, k in enumerate(no_refs[:cap], 1):
            if n % 10 == 0:
                print(f"      {n}/{min(cap, len(no_refs))}", flush=True)
            s = seed_identity(by_key[k])
            ref = (f"arXiv:{s['arxiv_id']}" if s["arxiv_id"] else f"DOI:{s['doi']}" if s["doi"]
                   else s2.match_title(by_key[k]["title"]))
            if not ref:
                continue
            refs = s2.references(ref)
            s2_done += bool(refs)
            for rec in refs:
                rec.update(seed_citers={k}, routes={"backward:semantic_scholar"},
                           influential_from={k} if rec.pop("influential") else set())
                pool.add(rec)
    log["seeds_needing_s2_references"] = len(no_refs)
    log["seeds_with_s2_references"] = s2_done

    mode = forward or cfg.get("forward_seeds", "core")
    fwd_keys = [k for k in resolved if mode == "all" or (mode == "core" and is_core(by_key[k]))] if mode != "none" else []
    print(f"[3/5] Forward citations (newer work citing {len(fwd_keys)} core papers) ...")
    for k in fwd_keys:
        for rec in oa.citing(resolved[k]["openalex_id"], cfg["budget"]["forward_per_seed"]):
            rec.update(forward_from={k}, routes={"forward:openalex"})
            pool.add(rec)
    log["forward_seeds"] = len(fwd_keys)

    print("[4/5] Deduplicating and ranking ...")
    keep_types = set(cfg["keep_types"])
    rubric = Rubric(cfg)
    cands, dropped = [], {"already_on_map": 0, "type": 0, "no_title": 0}
    for rec in pool.records():
        if not rec.get("title"):
            dropped["no_title"] += 1
        elif seed_index.match(rec):
            dropped["already_on_map"] += 1
        elif rec.get("type") and rec["type"] not in keep_types:
            dropped["type"] += 1
        else:
            cands.append(rec)
    log["candidates_raw"] = len(pool.records())
    log["dropped"] = dropped

    pillar_share = pillar_shares(rows)
    for rec in cands:
        w = sum(2 if is_core(by_key.get(k, {})) else 1 for k in rec["seed_citers"])
        w += 0.5 * len(rec["influential_from"]) + len(rec["forward_from"])
        rec["_citer_weight"] = w
    max_prox = max((r["_citer_weight"] for r in cands), default=0)
    for rec in cands:
        rec["score"], rec["factors"], h, pillars = rubric.score(rec, seed_index, pillar_share, max_prox)
        rec["suggested_tier"] = suggest_tier(h)
        rec["suggested_pillars"] = pillars
        rec["why"] = why(rec, seed_titles, h)
        rec["id"] = stable_id(rec)
    cands.sort(key=lambda r: -r["score"])

    print("[5/5] Updating registry and writing the review queue ...")
    registry = json.load(open(registry_path)) if os.path.exists(registry_path) else {"candidates": {}}
    decisions = {d["id"]: d for d in load_csv(decisions_path) if d.get("id")}
    new_count = 0
    for rec in cands:
        created = rec["id"] not in registry["candidates"]
        e = registry["candidates"].setdefault(rec["id"], {"first_seen": today, "title": rec["title"]})
        new_count += created
        e["last_seen"] = today
        e["routes"] = sorted(set(e.get("routes", [])) | rec["routes"])
        e["seed_citers"] = sorted(set(e.get("seed_citers", [])) | rec["seed_citers"] | rec["forward_from"])
        e["status"] = (decisions.get(rec["id"]) or {}).get("decision") or "pending"
        rec["new_this_run"] = "yes" if e["first_seen"] == today else ""
        rec["status"] = e["status"]
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    json.dump(registry, open(registry_path, "w"), indent=1, sort_keys=True)

    pending = [r for r in cands if r["status"] == "pending"]
    queue = pending[: cfg["budget"]["queue_size"]]
    write_outputs(out, cands, queue, log, dropped, decisions)
    log.update(candidates=len(cands), new_candidates=new_count, pending=len(pending),
               queue=len(queue), seconds=round(time.time() - t0, 1),
               tiers={t: sum(r["suggested_tier"] == t for r in cands) for t in "ABCD"})
    json.dump(log, open(os.path.join(out, "run_summary.json"), "w"), indent=1)
    return log


def pillar_shares(rows):
    counts = {p: 0 for p in ("P1", "P2", "P3", "P4")}
    for r in rows:
        for p in re.findall(r"P[1-4]", r.get("pillars", "")):
            counts[p] += 1
    top = max(counts.values()) or 1
    return {p: c / top for p, c in counts.items()}


def short_title(t):
    t = (t or "").split(":")[0].strip()
    return t if len(t) <= 40 else t[:37] + "..."


def plain(rec):
    out = {k: v for k, v in rec.items() if not k.startswith("_")}
    for k, v in out.items():
        if isinstance(v, set):
            out[k] = sorted(v)
    return out


def write_outputs(out, cands, queue, log, dropped, decisions):
    json.dump([plain(r) for r in cands], open(os.path.join(out, "candidates.json"), "w"), indent=1)
    with open(os.path.join(out, "candidates.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "score", "suggested_tier", "suggested_pillars", "status", "title", "year", "venue",
                    "doi", "arxiv_id", "openalex_id", "url", "seed_citers", "forward_from", "routes", "why"])
        for r in cands:
            w.writerow([r["id"], r["score"], r["suggested_tier"], " ".join(r["suggested_pillars"]), r["status"],
                        r["title"], r.get("year") or "", r.get("venue") or "", r.get("doi") or "",
                        r.get("arxiv_id") or "", r.get("openalex_id") or "", r.get("url") or "",
                        " ".join(sorted(r["seed_citers"])), " ".join(sorted(r["forward_from"])),
                        " ".join(sorted(r["routes"])), r["why"]])
    with open(os.path.join(out, "review_queue.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=QUEUE_COLS)
        w.writeheader()
        for i, r in enumerate(queue, 1):
            w.writerow({"rank": i, "id": r["id"], "score": r["score"], "suggested_tier": r["suggested_tier"],
                        "suggested_pillars": " ".join(r["suggested_pillars"]), "title": r["title"],
                        "year": r.get("year") or "", "venue": r.get("venue") or "", "url": r.get("url") or "",
                        "why": r["why"], "new_this_run": r["new_this_run"],
                        "decision": "", "tier": "", "pillars": "", "notes": ""})
    lines = [f"# USIL discovery review — {log['date']}", "",
             f"{len(cands)} candidates after removing {dropped['already_on_map']} already on the map. "
             f"Showing the top {len(queue)} pending. Fill `decision` (include / maybe / exclude), `tier`, and "
             f"`pillars` in `review_queue.csv`, then run `record`.", "", "## Tiers", ""]
    lines += [f"- **{t}** — {m}" for t, m in TIER_MEANING.items()]
    lines += ["", "## Queue", ""]
    for i, r in enumerate(queue, 1):
        lines.append(f"{i}. **{r['title']}** ({r.get('year') or 'n.d.'}) — score {r['score']}, "
                     f"suggested tier {r['suggested_tier']} {' '.join(r['suggested_pillars'])}  ")
        lines.append(f"   {r['why']}  ")
        if r.get("url"):
            lines.append(f"   {r['url']}")
    open(os.path.join(out, "review_queue.md"), "w").write("\n".join(lines) + "\n")


def record(queue_path, decisions_path):
    """Copy reviewed rows from a review_queue.csv into the persistent decisions file."""
    have = {d["id"]: d for d in load_csv(decisions_path)}
    today = datetime.date.today().isoformat()
    n = 0
    for r in load_csv(queue_path):
        dec = (r.get("decision") or "").strip().lower()
        if dec not in ("include", "maybe", "exclude"):
            continue
        have[r["id"]] = {"id": r["id"], "title": r["title"], "decision": dec, "tier": (r.get("tier") or "").strip().upper(),
                         "pillars": (r.get("pillars") or "").strip(), "notes": r.get("notes", ""), "decided_on": today}
        n += 1
    os.makedirs(os.path.dirname(decisions_path) or ".", exist_ok=True)
    with open(decisions_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DECISION_COLS)
        w.writeheader()
        w.writerows(have.values())
    return n, len(have)


def map_key(rec, taken):
    first = (rec.get("authors") or "").split(",")[0].strip().split(" ")[-1] or "anon"
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().lower() or "anon"
    word = next((w for w in re.findall(r"[a-z]+", (rec.get("title") or "").lower())
                 if w not in {"a", "an", "the", "on", "of", "for", "to", "and", "in", "with", "towards", "toward"}), "x")
    base = f"{first}{rec.get('year') or ''}{word}"
    key, i = base, 2
    while key in taken:
        key, i = f"{base}{i}", i + 1
    taken.add(key)
    return key


def promote(decisions_path, candidates_path, seeds_path, out_txt):
    """Write the included papers as a list of links (one per line) for `python -m usil_pipeline add --from`,
    which reads, labels, and adds each one to data/papers.csv. Papers already on the map are skipped."""
    cands = {c["id"]: c for c in json.load(open(candidates_path))}
    on_map = {norm_title(s.get("title")) for s in load_csv(seeds_path)}
    lines, missing = [], []
    for d in load_csv(decisions_path):
        if d.get("decision") != "include":
            continue
        c = cands.get(d["id"])
        if not c:
            missing.append(d["id"])
            continue
        if norm_title(c.get("title")) in on_map:
            continue
        link = (f"https://arxiv.org/abs/{c['arxiv_id']}" if c.get("arxiv_id") else
                f"https://doi.org/{c['doi']}" if c.get("doi") else c.get("url") or c["title"])
        lines.append(f"{link}  # {c['title']}")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return lines, missing
