"""Stage 1a: fetch and parse full text with page markers.

Tries, in order: arXiv PDF, Semantic Scholar open-access PDF, the CSV URL if it is (or
can be turned into) a PDF (ACL Anthology, OpenReview). Falls back to the abstract and marks
the paper 'abstract-only'. Full texts are cached locally and never written to the outputs.
"""
import glob, hashlib, os, re
import requests
try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # older PyMuPDF
    import fitz

UA = {"User-Agent": "Mozilla/5.0 (usil-pipeline literature map)"}
MAX_CHARS = 450_000  # ~110k tokens; long appendices are truncated


def _candidate_urls(row, meta):
    urls = list(meta.get("pdf_candidates") or [])
    u = (row.get("url") or "").strip()
    if u:
        if "aclanthology.org" in u and not u.endswith(".pdf"):
            urls.append(u.rstrip("/") + ".pdf")
        elif "openreview.net/forum" in u:
            urls.append(u.replace("/forum", "/pdf"))
        elif u.endswith(".pdf"):
            urls.append(u)
    seen, out = set(), []
    for x in urls:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def pdf_to_pages(data: bytes):
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for i, p in enumerate(doc, start=1):
        t = p.get_text("text")
        t = t.replace("­", "")                     # soft hyphens
        t = re.sub(r"-\n(?=[a-z])", "", t)              # de-hyphenate line breaks
        t = re.sub(r"[ \t]+", " ", t)
        pages.append(t.strip())
    return pages


def with_markers(pages):
    text = "\n\n".join(f"[[PAGE {i}]]\n{t}" for i, t in enumerate(pages, start=1))
    return text[:MAX_CHARS]


def match_local_pdfs(titles, dirs):
    """{key: path} for PDFs in dirs: a file named <key>.pdf, or one whose first two pages contain the key's title."""
    from rapidfuzz import fuzz
    alnum = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    want = {k: alnum(t) for k, t in titles.items() if len(alnum(t)) > 12}
    found = {}
    paths = [p for d in dirs for p in sorted(glob.glob(os.path.join(os.path.expanduser(d), "*.pdf")))]
    for path in paths:  # explicit names win (for PDFs whose title is an image or set in display type)
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in titles:
            found[stem] = path
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(os.path.expanduser(d), "*.pdf"))):
            if path in found.values():
                continue
            try:
                doc = fitz.open(path)
                head = alnum(" ".join(doc[i].get_text("text") for i in range(min(2, len(doc)))))
            except Exception:
                continue
            for k, t in want.items():
                if k not in found and (t in head or fuzz.partial_ratio(t, head) >= 92):
                    found[k] = path
    return found


def fetch(row, meta, cache_dir, local_path=None):
    os.makedirs(cache_dir, exist_ok=True)
    if local_path:
        pages = pdf_to_pages(open(local_path, "rb").read())
        if sum(len(p) for p in pages) > 2000:
            return {"mode": "full-text", "source_url": local_path, "pages": pages, "text": with_markers(pages)}
    for url in _candidate_urls(row, meta):
        fn = os.path.join(cache_dir, hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf")
        data = None
        if os.path.exists(fn):
            data = open(fn, "rb").read()
        else:
            try:
                r = requests.get(url, headers=UA, timeout=60, allow_redirects=True)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    data = r.content
                    open(fn, "wb").write(data)
            except requests.RequestException:
                data = None
        if data:
            try:
                pages = pdf_to_pages(data)
            except Exception:
                continue
            if sum(len(p) for p in pages) > 2000:
                return {"mode": "full-text", "source_url": url, "pages": pages, "text": with_markers(pages)}
    abstract = meta.get("abstract") or ""
    return {"mode": "abstract-only" if abstract else "none", "source_url": None,
            "pages": [abstract] if abstract else [], "text": f"[[PAGE 1]]\n{abstract}" if abstract else ""}
