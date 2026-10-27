"""Check that every quote the model returns actually appears in the paper text."""
import re, unicodedata
from rapidfuzz import fuzz

LIG = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
       "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in LIG.items():
        s = s.replace(a, b)
    s = re.sub(r"-\s+(?=[a-z])", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def locate(quote, pages, page_hint=None, threshold=90):
    """Return (status, page) where status is 'exact', 'approx' or 'not_found'."""
    q = norm(quote)
    if len(q) < 8:
        return "not_found", None
    order = list(range(len(pages)))
    if page_hint and 1 <= page_hint <= len(pages):
        order.remove(page_hint - 1)
        order.insert(0, page_hint - 1)
    normed = [norm(p) for p in pages]
    for i in order:
        if q in normed[i]:
            return "exact", i + 1
    # quotes can straddle a page break
    for i in range(len(pages) - 1):
        if q in normed[i] + " " + normed[i + 1]:
            return "exact", i + 1
    best, best_i = 0, None
    for i in order:
        s = fuzz.partial_ratio(q, normed[i]) if len(q) <= len(normed[i]) else 0
        if s > best:
            best, best_i = s, i
    if best >= threshold:
        return "approx", best_i + 1
    return "not_found", None


def check_evidence(evidence: dict, pages):
    """Annotate each quote with verification status; return (evidence, stats)."""
    total = ok = 0
    for field, v in evidence.items():
        kept = []
        for q in v.get("quotes", []):
            status, page = locate(q.get("quote", ""), pages, q.get("page"))
            q["verified"] = status
            if page and status != "not_found":
                q["page"] = page
            total += 1
            ok += status != "not_found"
            kept.append(q)
        v["quotes"] = kept
        # a field marked demonstrated/claimed must keep at least one verified quote
        if v.get("status") in ("demonstrated", "claimed") and not any(q["verified"] != "not_found" for q in kept):
            v["status_flag"] = "no verified quote — treat as unsupported"
    return evidence, {"quotes_total": total, "quotes_verified": ok,
                      "quote_verification_rate": round(ok / total, 3) if total else None}
