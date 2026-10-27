"""Check data/papers.csv against data/schema.json. Run before a pull request (CI runs it too):

    python scripts/check_papers.py

Errors (exit 1): missing required values, unknown categories or label values, duplicate keys or titles,
annotated rows without the four chart labels. Warnings: missing authors or venue.
"""
import csv, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = ["per_user", "interaction_decisions", "across_sessions", "evaluates_transfer"]
EXCLUSIVE = {"none", "not-stated"}  # cannot be combined with other values in a list


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def check(csv_path, schema_path):
    schema = json.load(open(schema_path, encoding="utf-8"))
    cols = {c["name"]: c for c in schema["columns"]}
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    errors, warnings = [], []
    if not rows:
        return ["data/papers.csv has no rows"], []
    header = list(rows[0].keys())
    missing = [c for c in cols if c not in header]
    extra = [c for c in header if c not in cols]
    if missing:
        errors.append(f"header: missing columns {', '.join(missing)}")
    if extra:
        errors.append(f"header: unknown columns {', '.join(extra)} (add them to data/schema.json first)")
    seen_keys, seen_titles = {}, {}
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        key = (r.get("key") or "").strip()
        where = f"line {i} ({key or 'no key'})"
        err = lambda msg: errors.append(f"{where}: {msg}")
        for c, spec in cols.items():
            if spec["group"] == "required" and not (r.get(c) or "").strip():
                err(f"{c} is required")
            if spec["group"] == "recommended" and not (r.get(c) or "").strip():
                warnings.append(f"{where}: {c} is blank")
        if key and not re.fullmatch(r"[a-z0-9_]+", key):
            err("key must be lowercase letters, digits, or _")
        if key in seen_keys:
            err(f"duplicate key (also line {seen_keys[key]})")
        seen_keys[key] = i
        t = norm_title(r.get("title") or "")
        if t and t in seen_titles:
            err(f"same title as line {seen_titles[t]}")
        seen_titles[t] = i
        y = (r.get("year") or "").strip()
        if y and not (re.fullmatch(r"\d{4}", y) and 1900 <= int(y) <= 2100):
            err(f"year '{y}' is not a 4-digit year")
        u = (r.get("url") or "").strip()
        if u and not u.startswith(("http://", "https://")):
            err("url must start with http:// or https://")
        if (r.get("category") or "").strip() and r["category"].strip() not in schema["categories"]:
            err(f"category '{r['category']}' is not one of: {'; '.join(schema['categories'])}")
        for c, spec in cols.items():
            raw = (r.get(c) or "").strip()
            allowed = spec.get("values")
            if not raw or not allowed:
                continue
            allowed = list(allowed) if isinstance(allowed, (list, dict)) else []
            vals = [v.strip() for v in raw.split(";")] if spec.get("list") else [raw]
            bad = [v for v in vals if v not in allowed]
            if bad:
                err(f"{c}: {', '.join(repr(b) for b in bad)} not allowed (use {', '.join(allowed)})")
            if spec.get("list") and len(vals) > 1 and EXCLUSIVE & set(vals):
                err(f"{c}: 'none' and 'not-stated' cannot be combined with other values")
        src = (r.get("annotation_source") or "").strip()
        if not src:
            err("annotation_source is blank (use 'pending' if the labels are not filled yet, or 'manual')")
        elif src != "pending":
            blank = [c for c in LABELS if not (r.get(c) or "").strip()]
            if blank:
                err(f"annotated rows need {', '.join(blank)} (use 'not-stated' if the paper does not say, or set annotation_source to 'pending')")
        d = (r.get("annotated_on") or "").strip()
        if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            err("annotated_on must be YYYY-MM-DD")
        q = (r.get("quotes_verified") or "").strip()
        if q:
            try:
                ok = 0 <= float(q) <= 1
            except ValueError:
                ok = False
            if not ok:
                err("quotes_verified must be a number from 0 to 1")
    return errors, warnings


def main():
    errors, warnings = check(os.path.join(ROOT, "data", "papers.csv"), os.path.join(ROOT, "data", "schema.json"))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
