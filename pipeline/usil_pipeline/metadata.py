"""Stage 0: metadata from bibliographic APIs (no LLM).

By identifier first: arXiv API (arXiv IDs), Crossref (DOIs), Semantic Scholar (either). Without an identifier, by
title: OpenAlex, then Crossref, then Semantic Scholar; a result counts only if its title matches after cleanup.
A matching arXiv ID with a different title is checked against every arXiv version, so a renamed paper is reported
as renamed, not as a mismatch. When all of this fails, metadata_llm.py can read the authors and venue from the
PDF's first page (verified against the page text); the model never supplies metadata from memory.
"""
import html, os, re, time, unicodedata, xml.etree.ElementTree as ET
import requests
from rapidfuzz import fuzz

UA = {"User-Agent": "usil-pipeline/0.1 (research literature map)"}
S2 = "https://api.semanticscholar.org/graph/v1/paper/"
S2_FIELDS = "title,authors,year,venue,publicationVenue,externalIds,openAccessPdf,abstract,url"


def _get(url, params=None, headers=None, tries=4, timeout=30):
    h = dict(UA, **(headers or {}))
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** i + 1)
                continue
            return r
        except requests.RequestException:
            time.sleep(2 ** i)
    return None


def arxiv_id_from(row):
    for v in (row.get("arxiv_id") or "", row.get("url") or "", row.get("venue") or ""):
        m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", v)
        if m:
            return m.group(1)
    return None


def doi_from(row):
    for v in (row.get("doi") or "", row.get("url") or "", row.get("venue") or ""):
        m = re.search(r"10\.\d{4,9}/[^\s,;}]+", v)
        if m:
            return m.group(0).rstrip(".")
    return None


def arxiv_meta(aid):
    r = _get("https://export.arxiv.org/api/query", params={"id_list": aid})
    if not r or r.status_code != 200:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    e = ET.fromstring(r.text).find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return None
    title = " ".join(e.find("a:title", ns).text.split())
    if title.lower() == "error":
        return None
    return {
        "title": title,
        "authors": ", ".join(a.find("a:name", ns).text for a in e.findall("a:author", ns)),
        "year": int(e.find("a:published", ns).text[:4]),
        "abstract": " ".join(e.find("a:summary", ns).text.split()),
        "journal_ref": (e.find("x:journal_ref", ns).text if e.find("x:journal_ref", ns) is not None else ""),
        "comment": (e.find("x:comment", ns).text if e.find("x:comment", ns) is not None else ""),
        "pdf_url": f"https://arxiv.org/pdf/{aid}",
    }


def s2_meta(paper_ref):
    key = os.environ.get("S2_API_KEY")
    r = _get(S2 + paper_ref, params={"fields": S2_FIELDS}, headers={"x-api-key": key} if key else None)
    if not key:
        time.sleep(1.1)  # unauthenticated S2 rate limit
    if not r or r.status_code != 200:
        return None
    d = r.json()
    pv = d.get("publicationVenue") or {}
    return {
        "title": d.get("title"),
        "authors": ", ".join(a.get("name", "") for a in d.get("authors") or []),
        "year": d.get("year"),
        "venue": d.get("venue") or pv.get("name") or "",
        "abstract": d.get("abstract") or "",
        "pdf_url": (d.get("openAccessPdf") or {}).get("url"),
        "external_ids": d.get("externalIds") or {},
        "s2_url": d.get("url"),
    }


def clean_title(t):
    """Comparable form of a title: no HTML, accents, punctuation, or extra spaces."""
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def same_title(a, b):
    a, b = clean_title(a), clean_title(b)
    if not a or not b:
        return False
    if fuzz.ratio(a, b) >= 92:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 20 and long_.startswith(short)  # one has a subtitle the other dropped


def arxiv_version_titles(aid, max_versions=12):
    titles = []
    for v in range(1, max_versions + 1):
        r = _get("https://export.arxiv.org/api/query", params={"id_list": f"{aid}v{v}"})
        if not r or r.status_code != 200:
            break
        e = ET.fromstring(r.text).find("{http://www.w3.org/2005/Atom}entry")
        t = e.find("{http://www.w3.org/2005/Atom}title") if e is not None else None
        if t is None or not (t.text or "").strip() or t.text.strip().lower() == "error":
            break
        titles.append(" ".join(t.text.split()))
    return titles


def s2_search(title):
    key = os.environ.get("S2_API_KEY")
    r = _get(S2 + "search/match", params={"query": title, "fields": S2_FIELDS},
             headers={"x-api-key": key} if key else None)
    if not key:
        time.sleep(1.1)
    if not r or r.status_code != 200:
        return None
    data = (r.json() or {}).get("data") or []
    if not data or not same_title(data[0].get("title"), title):
        return None
    return s2_meta(data[0]["paperId"])


def openalex_search(title):
    params = {"search": clean_title(title), "per-page": 5,
              "select": "title,doi,publication_year,authorships,primary_location,ids"}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    r = _get("https://api.openalex.org/works", params=params)
    if not r or r.status_code != 200:
        return None
    for w in (r.json() or {}).get("results") or []:
        if same_title(w.get("title"), title):
            src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
            return {"title": w.get("title"), "year": w.get("publication_year"), "venue": src,
                    "authors": ", ".join((a.get("author") or {}).get("display_name", "") for a in w.get("authorships") or []),
                    "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None}
    return None


def crossref_search(title):
    r = _get("https://api.crossref.org/works", params={"query.bibliographic": title, "rows": 5})
    if not r or r.status_code != 200:
        return None
    for m in ((r.json() or {}).get("message") or {}).get("items") or []:
        t = (m.get("title") or [""])[0]
        if same_title(t, title):
            return {"title": t, "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0],
                    "venue": (m.get("container-title") or [""])[0], "doi": m.get("DOI"),
                    "authors": ", ".join(f"{a.get('given', '')} {a.get('family', '')}".strip() for a in m.get("author", []))}
    return None


def crossref_meta(doi):
    r = _get(f"https://api.crossref.org/works/{doi}")
    if not r or r.status_code != 200:
        return None
    m = r.json().get("message", {})
    return {
        "title": (m.get("title") or [""])[0],
        "authors": ", ".join(f"{a.get('given','')} {a.get('family','')}".strip() for a in m.get("author", [])),
        "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0],
        "venue": (m.get("container-title") or [""])[0],
    }


def resolve(row):
    """Verified metadata + discrepancies against the CSV row."""
    aid, doi = arxiv_id_from(row), doi_from(row)
    title = row.get("title") or ""
    out = {"arxiv_id": aid, "doi": doi, "sources": []}
    ax = arxiv_meta(aid) if aid else None
    cr = crossref_meta(doi) if doi else None
    s2 = s2_meta(f"arXiv:{aid}") if aid else (s2_meta(f"DOI:{doi}") if doi else None)
    oa = None
    if not (ax or cr or s2) and title:  # no identifier, or the identifier lookups failed: search by title
        oa = openalex_search(title)
        if not oa:
            cr = crossref_search(title)
        if not (oa or cr):
            s2 = s2_search(title)
        doi = doi or (oa or cr or {}).get("doi")
        out["doi"] = doi
    for name, m in (("arxiv", ax), ("semantic_scholar", s2), ("crossref", cr), ("openalex", oa)):
        if m:
            out["sources"].append(name)
    best = ax or s2 or cr or oa or {}
    out["title"] = best.get("title") or title
    out["authors"] = next((m["authors"] for m in (ax, s2, cr, oa) if m and m.get("authors")), "") or row.get("authors")
    out["year"] = (s2 or {}).get("year") or (ax or {}).get("year") or (cr or {}).get("year") or (oa or {}).get("year")
    venues = [(m or {}).get("venue") or "" for m in (s2, cr, oa)]
    # "arXiv" / "arXiv.org" from these databases means unpublished, not a venue
    out["venue_api"] = next((v for v in venues if v and not re.fullmatch(r"(?i)arxiv(\.org)?( \(cornell university\))?", v.strip())), "")
    out["arxiv_journal_ref"] = (ax or {}).get("journal_ref", "")
    out["arxiv_comment"] = (ax or {}).get("comment", "")
    # what a reader would cite: the published venue, else the arXiv preprint
    out["venue"] = out["venue_api"] or out["arxiv_journal_ref"] or (f"arXiv preprint arXiv:{aid}" if ax else "")
    out["abstract"] = (ax or {}).get("abstract") or (s2 or {}).get("abstract") or ""
    out["pdf_candidates"] = [u for u in [(ax or {}).get("pdf_url"), (s2 or {}).get("pdf_url")] if u]
    if aid and not out["pdf_candidates"]:  # the APIs can fail (rate limits); the arXiv PDF is still there
        out["pdf_candidates"].append(f"https://arxiv.org/pdf/{aid}")
    if not aid and s2:
        a2 = (s2.get("external_ids") or {}).get("ArXiv")
        if a2:
            out["arxiv_id"] = a2
            out["pdf_candidates"].insert(0, f"https://arxiv.org/pdf/{a2}")
    issues = []
    out["renamed_from"] = ""
    if not out["sources"]:
        issues.append("NOT FOUND in arXiv/Semantic Scholar/Crossref/OpenAlex — verify the paper exists")
    elif title and not same_title(out["title"], title):
        if ax and any(same_title(t, title) for t in arxiv_version_titles(aid)):
            out["renamed_from"] = title
            issues.append(f"renamed on arXiv: '{title}' -> '{out['title']}'")
        else:
            issues.append(f"title differs: API='{out['title']}' (check that the link points to this paper)")
    if out["year"] and str(out["year"]) != str(row.get("year", "")).strip():
        issues.append(f"year differs: API={out['year']}")
    out["metadata_issues"] = issues
    return out
