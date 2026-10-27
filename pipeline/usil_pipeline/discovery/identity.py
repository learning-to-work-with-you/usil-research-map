"""Paper identity: one record per paper however many routes surface it.

Two records are the same paper if they share a DOI, an arXiv ID, an OpenAlex ID, a Semantic
Scholar ID, or a normalized title. Published versions and their arXiv preprints often carry
different DOIs, so the title key is what usually joins them.
"""
import re

from rapidfuzz import fuzz

from ..metadata import arxiv_id_from, doi_from


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def keys_of(rec):
    ks = []
    if rec.get("doi"):
        ks.append("doi:" + rec["doi"].lower())
    if rec.get("arxiv_id"):
        ks.append("arxiv:" + re.sub(r"v\d+$", "", rec["arxiv_id"]))
    if rec.get("openalex_id"):
        ks.append("oa:" + rec["openalex_id"])
    if rec.get("s2_id"):
        ks.append("s2:" + rec["s2_id"])
    nt = norm_title(rec.get("title"))
    if len(nt) >= 12:  # very short titles ("Introduction") would merge unrelated papers
        ks.append("title:" + nt)
    return ks


def stable_id(rec):
    """The id reviewers see and decisions are stored under; survives reruns."""
    for prefix in ("doi:", "arxiv:", "oa:", "s2:", "title:"):
        for k in keys_of(rec):
            if k.startswith(prefix):
                return k
    return "title:" + norm_title(rec.get("title"))


class Pool:
    """Deduplicating collection of candidate records."""

    def __init__(self):
        self.recs = []
        self.index = {}

    def add(self, rec):
        hits = {self.index[k] for k in keys_of(rec) if k in self.index}
        if hits:
            i = min(hits)
            self._merge(self.recs[i], rec)
            for j in sorted(hits - {i}):  # rec bridged two records: fold the other into i
                old = self.recs[j]
                self._merge(self.recs[i], old)
                for k in keys_of(old):
                    self.index[k] = i
                self.recs[j] = None
        else:
            i = len(self.recs)
            self.recs.append(dict(rec, seed_citers=set(rec.get("seed_citers", ())),
                                  forward_from=set(rec.get("forward_from", ())),
                                  influential_from=set(rec.get("influential_from", ())),
                                  routes=set(rec.get("routes", ()))))
        for k in keys_of(self.recs[i]):
            self.index[k] = i
        return self.recs[i]

    @staticmethod
    def _merge(a, b):
        for f in ("doi", "arxiv_id", "openalex_id", "s2_id", "title", "year", "venue", "authors", "url", "type"):
            if not a.get(f) and b.get(f):
                a[f] = b[f]
        if len(b.get("abstract") or "") > len(a.get("abstract") or ""):
            a["abstract"] = b["abstract"]
        a["cited_by_count"] = max(a.get("cited_by_count") or 0, b.get("cited_by_count") or 0)
        for f in ("seed_citers", "forward_from", "influential_from", "routes"):
            a.setdefault(f, set()).update(b.get(f, ()))

    def records(self):
        return [r for r in self.recs if r is not None]


class SeedIndex:
    """Recognizes papers that are already on the map."""

    def __init__(self, seeds):
        self.keys, self.titles = {}, []
        for s in seeds:
            self.add(s)

    def add(self, s, key=None):
        key = key or s.get("key")
        for k in keys_of(s):
            self.keys[k] = key
        if s.get("title"):
            self.titles.append((s["title"], key))

    def match(self, rec):
        for k in keys_of(rec):
            if k in self.keys:
                return self.keys[k]
        t = rec.get("title") or ""
        if len(norm_title(t)) < 12:
            return None
        for title, key in self.titles:
            if fuzz.ratio(t.lower(), title.lower()) >= 94:
                return key
        return None

    def nearest_similarity(self, title):
        if not title or not self.titles:
            return 0.0
        return max(fuzz.token_set_ratio(title.lower(), t.lower()) for t, _ in self.titles) / 100.0


def seed_identity(row):
    """Identifiers recoverable from a map row (URL, venue)."""
    return {"key": row.get("key"), "title": row.get("title", ""),
            "doi": (doi_from(row) or "").lower() or None, "arxiv_id": arxiv_id_from(row)}
