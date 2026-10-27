"""Citation-graph sources for discovery: OpenAlex (primary) and Semantic Scholar (fallback).

Every response is cached on disk by URL, so reruns are fast and free. Set OPENALEX_MAILTO to
join OpenAlex's polite pool, OPENALEX_API_KEY for OpenAlex's keyed daily budget (needed for
full runs: the anonymous budget is shared per IP and small), and S2_API_KEY for a higher
Semantic Scholar rate limit.
"""
import hashlib, json, os, re, time

import requests

from ..metadata import UA, _get

OA = "https://api.openalex.org/works"
OA_FIELDS = ("id,doi,ids,title,publication_year,cited_by_count,referenced_works,"
             "abstract_inverted_index,authorships,primary_location,type")
S2 = "https://api.semanticscholar.org/graph/v1/paper/"
S2_REF_FIELDS = "title,year,externalIds,abstract,venue,citationCount,authors,url"


def _openalex_get(url, params, tries=4):
    """Like metadata._get, but returns OpenAlex's 429 so a used-up daily budget is reported, not retried."""
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
        except requests.RequestException:
            time.sleep(2 ** i)
            continue
        if r.status_code == 429 and "budget" in r.text.lower():
            return r
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** i + 1)
            continue
        return r
    return None


class BudgetExhausted(RuntimeError):
    """OpenAlex refused the request because the daily budget is used up; retrying won't help."""


class Cache:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def get(self, url, params=None, headers=None, pause=0.0):
        key = hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        path = os.path.join(self.root, key + ".json")
        if os.path.exists(path):
            return json.load(open(path))
        r = _openalex_get(url, params) if "openalex" in url else _get(url, params=params, headers=headers)
        if r is not None and r.status_code == 429 and "openalex" in url and "budget" in r.text.lower():
            raise BudgetExhausted(
                "OpenAlex's free daily budget for this network is used up (it resets at midnight UTC). "
                "Get a free API key at https://openalex.org/settings/api and put OPENALEX_API_KEY=... in .env, "
                "then rerun; everything fetched so far is cached.")
        if pause:
            time.sleep(pause)
        if r is not None and r.status_code in (400, 404):
            json.dump(None, open(path, "w"))  # a definitive miss: don't ask again on reruns
            return None
        if not r or r.status_code != 200:
            return None
        data = r.json()
        json.dump(data, open(path, "w"))
        return data


def _oa_params(extra):
    p = {"select": OA_FIELDS, **extra}
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    elif os.environ.get("OPENALEX_MAILTO"):
        p["mailto"] = os.environ["OPENALEX_MAILTO"]
    return p


def abstract_from_index(inv):
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not inv:
        return ""
    words = sorted((pos, w) for w, ps in inv.items() for pos in ps)
    return " ".join(w for _, w in words)


def short_id(oa_id):
    return (oa_id or "").rsplit("/", 1)[-1]


def oa_record(w):
    """Normalize an OpenAlex work into the candidate fields we keep."""
    ids = w.get("ids") or {}
    doi = (w.get("doi") or ids.get("doi") or "").replace("https://doi.org/", "").lower() or None
    arxiv = None
    if doi and doi.startswith("10.48550/arxiv."):
        arxiv = doi.split("arxiv.", 1)[1]
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {}).get("display_name") or ""
    return {
        "openalex_id": short_id(w.get("id")),
        "doi": doi, "arxiv_id": arxiv,
        "title": w.get("title") or "",
        "year": w.get("publication_year"),
        "venue": src,
        "authors": ", ".join((a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])[:12]),
        "abstract": abstract_from_index(w.get("abstract_inverted_index")),
        "cited_by_count": w.get("cited_by_count") or 0,
        "type": w.get("type") or "",
        "url": loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else w.get("id")),
        "referenced_works": [short_id(x) for x in (w.get("referenced_works") or [])],
    }


class OpenAlex:
    def __init__(self, cache):
        self.c = cache

    def by_filter(self, flt, per_page=50, sort=None):
        params = {"filter": flt, "per-page": per_page}
        if sort:
            params["sort"] = sort
        d = self.c.get(OA, _oa_params(params))
        return [oa_record(w) for w in (d or {}).get("results", [])]

    def by_ids(self, ids):
        out = []
        ids = list(dict.fromkeys(i for i in ids if i))
        for i in range(0, len(ids), 50):
            out += self.by_filter("openalex:" + "|".join(ids[i:i + 50]))
        return out

    def by_dois(self, dois):
        out = []
        dois = list(dict.fromkeys(d for d in dois if d))
        for i in range(0, len(dois), 40):
            out += self.by_filter("doi:" + "|".join(dois[i:i + 40]))
        return out

    def search_title(self, title):
        clean = re.sub(r"[^\w\s-]", " ", title or "").strip()
        if not clean:
            return []
        d = self.c.get(OA, _oa_params({"search": clean, "per-page": 5}))
        return [oa_record(w) for w in (d or {}).get("results", [])]

    def citing(self, oa_id, n):
        return self.by_filter(f"cites:{oa_id}", per_page=min(n, 200), sort="publication_date:desc")


class SemanticScholar:
    def __init__(self, cache):
        self.c = cache
        self.key = os.environ.get("S2_API_KEY")

    def _h(self):
        return {"x-api-key": self.key} if self.key else None

    def references(self, ref):
        """ref is 'arXiv:XXXX', 'DOI:...' or an S2 paperId."""
        d = self.c.get(S2 + ref + "/references", {"fields": S2_REF_FIELDS + ",isInfluential", "limit": 500},
                       self._h(), pause=0 if self.key else 1.1)
        out = []
        for item in (d or {}).get("data") or []:
            p = item.get("citedPaper") or {}
            if not p.get("title"):
                continue
            ext = p.get("externalIds") or {}
            out.append({
                "s2_id": p.get("paperId"), "doi": (ext.get("DOI") or "").lower() or None,
                "arxiv_id": ext.get("ArXiv"), "title": p["title"], "year": p.get("year"),
                "venue": p.get("venue") or "", "abstract": p.get("abstract") or "",
                "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:12]),
                "cited_by_count": p.get("citationCount") or 0, "type": "",
                "url": p.get("url") or "", "influential": bool(item.get("isInfluential")),
            })
        return out

    def match_title(self, title):
        d = self.c.get(S2 + "search/match", {"query": title, "fields": "title,externalIds"}, self._h(),
                       pause=0 if self.key else 1.1)
        data = (d or {}).get("data") or []
        return data[0].get("paperId") if data else None
