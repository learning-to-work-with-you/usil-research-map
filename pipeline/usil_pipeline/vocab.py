"""Translate pipeline output (and older free-text labels) into the values allowed by data/schema.json."""
import json, os, re

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "schema.json")

# Pipeline (schemas.py) wording -> schema value, per column.
STUDY = {
    "paper_type": {"method": "method", "benchmark, dataset, or environment": "benchmark", "user study": "user-study",
                   "survey or position": "survey", "theory": "theory", "system or framework": "system"},
    "settings": {"coding agent": "coding-agent", "web or gui agent": "web-gui-agent", "chat assistant": "chat-assistant",
                 "embodied robot": "robot", "decision support": "decision-support", "recommendation": "recommendation",
                 "education": "education", "health": "health", "productivity or office": "productivity", "other": "other"},
    "user_signals": {"edits or corrections": "edits", "approvals or rejections": "approvals", "takeovers or interventions": "takeovers",
                     "answers to questions": "answers", "ratings or comparisons": "ratings", "stated preferences or profile": "stated-preferences",
                     "implicit behavior or history": "behavior-history", "persona or demographics": "persona", "none": "none"},
    "user_representation": {"natural-language profile or memory": "profile-memory", "latent vector": "latent-vector",
                            "per-user parameters": "per-user-parameters", "reward or preference model": "reward-model",
                            "rules or permissions": "rules", "belief distribution": "belief", "none": "none"},
    "preference_change": {"assumes fixed preferences": "fixed", "handles drift or change": "handles-drift"},
    "personalization_unit": {"individual user": "individual", "group or persona": "group", "repository or project": "repository",
                             "population": "population"},
    "evaluation_users": {"real users": "real", "simulated users": "simulated", "both": "both", "no user evaluation": "none"},
    "per_person_results": {"yes": "yes", "no": "no"},
    "interaction_cost_metrics": {"questions asked": "questions", "interruptions": "interruptions", "user effort or time": "effort-time",
                                 "trust": "trust", "satisfaction or preference": "satisfaction", "workload": "workload", "none": "none"},
    "decision_factors": {"stakes": "stakes", "reversibility": "reversibility", "uncertainty": "uncertainty",
                         "authorization or permission": "permission", "user expertise": "expertise",
                         "workload or interruptibility": "interruptibility", "none": "none"},
}
LIST_COLUMNS = {"settings", "user_signals", "interaction_cost_metrics", "decision_factors", "resources"}

# Free-text interaction decisions -> schema values (first match per rule; order matters).
DECISION_RULES = [
    ("ask", r"\bask|clarif|elicit|question|query"),
    ("confirm", r"confirm|approv|permission|verify|sign.?off"),
    ("act", r"\bact\b|act \(|delegat|autonom|assist|do nothing|grant|initiative"),
    ("suggest", r"suggest|proactiv|recommend"),
    ("explain", r"explain"),
    ("interrupt", r"interrupt|warn|notif"),
    ("intervene", r"interven|takeover|take over"),
    ("defer", r"defer|return.?control|leave it to the user|withhold"),
    ("communicate", r"communicat"),
]
UNKNOWN = re.compile(r"^(not established|not verified|not yet verified|review full paper before coding|unknown|n\.?e\.?)\b", re.I)


def schema():
    return json.load(open(SCHEMA_PATH, encoding="utf-8"))


def level(raw):
    """'partial (style-level)' -> ('partial', 'style-level'); unknown -> ('', ''). 'n/a' counts as no."""
    v = (raw or "").strip()
    if not v or UNKNOWN.match(v):
        return "", ""
    low = v.lower()
    for lv in ("yes", "partial", "no", "n/a", "not-stated"):
        if low.startswith(lv):
            detail = v[len(lv):].strip(" ()-:;,.")
            return ("no" if lv == "n/a" else lv), detail
    return "", v


def decisions(raw):
    """Free text or a pipeline list -> (sorted schema values, leftover note). Unknown -> ([], '')."""
    v = (raw or "").strip()
    if not v or UNKNOWN.match(v):
        return [], ""
    if v.lower() == "not-stated":
        return ["not-stated"], ""
    if v.lower().startswith("none"):
        return ["none"], ""
    found = [name for name, pat in DECISION_RULES if re.search(pat, v.lower())]
    return found, ("" if found else v)


def study_value(column, raw):
    """Pipeline value(s) for a study column -> schema value(s) joined with ';'. Unrecognized values are dropped."""
    m = STUDY.get(column)
    items = [x.strip() for x in (raw if isinstance(raw, list) else str(raw or "").split(";")) if x.strip()]
    if column == "resources":
        return ";".join(x for x in items if x.startswith("http"))
    out = [m[x.lower()] for x in items if m and x.lower() in m]
    if column not in LIST_COLUMNS:
        return out[0] if out else ""
    out = list(dict.fromkeys(out))
    if len(out) > 1 and "none" in out:  # 'none' only stands alone
        out.remove("none")
    return ";".join(out)
