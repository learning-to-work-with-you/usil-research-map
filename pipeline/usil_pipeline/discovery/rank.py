"""Transparent ranking for the review queue.

Every factor is a 0-1 score from title + abstract and citation links, combined with the weights
in config/discovery.json. The score only orders human review; it never adds a paper to the map.
Tier and pillar labels here are suggestions for the reviewer, not decisions.
"""
import math, re

TIER_MEANING = {
    "A": "Core predecessor: learns, models, or evaluates how an agent interacts with a particular user",
    "B": "Enabling research: an essential USIL component (feedback, memory, clarification, individualized evaluation)",
    "C": "Adjacent: personalizes outputs, goals, or rewards rather than interaction procedure",
    "D": "Background / out of scope",
}


class Rubric:
    def __init__(self, cfg):
        self.w = cfg["weights"]
        total = sum(self.w.values()) or 1
        self.w = {k: v / total for k, v in self.w.items()}
        self.terms = {g: [re.compile(p, re.I) for p in ps] for g, ps in cfg["terms"].items()}
        self.pillar_terms = {p: [re.compile(t, re.I) for t in ts] for p, ts in cfg["pillars"].items()}

    def hits(self, text, group):
        """The words actually found (not the patterns), so reviewers can read them."""
        found = set()
        for p in self.terms.get(group, []):
            m = p.search(text)
            if m:
                found.add(m.group(0).lower().strip())
        return sorted(found)

    def pillars(self, text):
        return [p for p, pats in self.pillar_terms.items() if any(x.search(text) for x in pats)]

    def score(self, rec, seed_index, pillar_share, max_proximity):
        text = f"{rec.get('title','')}. {rec.get('abstract','')}"
        h = {g: self.hits(text, g) for g in self.terms}
        cover = lambda g: min(1.0, len(h[g]) / 2)

        relevance = (0.35 * cover("procedure") + 0.30 * cover("individual")
                     + 0.20 * cover("learning") + 0.15 * cover("context"))
        if h["procedure"] and h["individual"]:  # interaction procedure *and* the individual: the USIL cell
            relevance = min(1.0, relevance + 0.15)
        if not h["context"]:  # no agent / assistant / robot / interaction: "intervention" is likely medical, etc.
            relevance *= 0.5

        contribution = (0.3 * bool(rec.get("abstract")) + 0.2 * (rec.get("type") in ("article", "proceedings-article", "preprint", ""))
                        + 0.5 * cover("contribution"))

        pillars = self.pillars(text)
        pillar_gap = (1 - min(pillar_share.get(p, 0) for p in pillars)) if pillars else 0.3
        novelty = 0.5 * (1 - seed_index.nearest_similarity(rec.get("title"))) + 0.5 * pillar_gap

        weighted_citers = rec.get("_citer_weight", 0)
        proximity = math.log1p(weighted_citers) / math.log1p(max_proximity) if max_proximity else 0.0

        y = rec.get("year")
        recency = 0.3 if not y else max(0.0, min(1.0, (y - 1990) / (2023 - 1990)))

        parts = {"relevance": relevance, "contribution": contribution, "novelty": novelty,
                 "proximity": proximity, "recency": recency}
        total = sum(self.w[k] * v for k, v in parts.items())
        return round(total, 4), {k: round(v, 3) for k, v in parts.items()}, h, pillars


def suggest_tier(h):
    proc, ind, learn, ctx = (bool(h[g]) for g in ("procedure", "individual", "learning", "context"))
    if proc and ind and learn and ctx:
        return "A"
    if ctx and ((proc and (learn or ind)) or (ind and learn)):
        return "B"
    if ind or (learn and any("preference" in p for p in h["learning"])):
        return "C"
    return "D"


def why(rec, seed_titles, h):
    """Human-readable provenance: why this paper surfaced."""
    bits = []
    citers = sorted(rec.get("seed_citers", ()))
    if citers:
        names = ", ".join(seed_titles.get(k, k) for k in citers[:3])
        more = f" +{len(citers) - 3}" if len(citers) > 3 else ""
        bits.append(f"cited by {len(citers)} map paper{'s' if len(citers) > 1 else ''} ({names}{more})")
    fwd = sorted(rec.get("forward_from", ()))
    if fwd:
        bits.append("cites " + ", ".join(seed_titles.get(k, k) for k in fwd[:3]))
    matched = [m for g in ("procedure", "individual") for m in h.get(g, [])][:4]
    if matched:
        bits.append("matches: " + ", ".join(matched))
    if not rec.get("abstract"):
        bits.append("no abstract (title-only score)")
    return "; ".join(bits)
