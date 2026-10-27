"""Offline tests: adding papers, publishing a run into data/papers.csv, and the CSV check."""
import csv, importlib.util, json, os

from usil_pipeline import add, publish, vocab

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_query_row():
    assert add.query_row("https://arxiv.org/abs/2602.16173v2")["url"] == "https://arxiv.org/abs/2602.16173"
    assert add.query_row("arXiv:2602.16173")["url"] == "https://arxiv.org/abs/2602.16173"
    assert add.query_row("10.1145/1031607.1031690")["doi"] == "10.1145/1031607.1031690"
    assert add.query_row("Learning Personalized Agents from Human Feedback")["title"].startswith("Learning")


def test_key_and_duplicates():
    rows = [{"key": "liang2026learning", "title": "Learning Personalized Agents from Human Feedback", "url": "https://arxiv.org/abs/2602.16173"}]
    meta = {"authors": "Kaiqu Liang, Julia Kruk", "year": 2026, "title": "Learning Personalized Agents from Human Feedback", "arxiv_id": "2602.16173"}
    assert add.make_key(meta, []) == "liang2026learning"
    assert add.make_key(meta, rows) == "liang2026learningb"
    assert add.duplicate_of(meta, "", rows)["key"] == "liang2026learning"
    assert add.duplicate_of({"title": "learning personalized agents from human feedback."}, "", rows)  # fuzzy title
    assert add.duplicate_of({"title": "Something else entirely", "arxiv_id": "2501.00001"}, "", rows) is None


def test_vocab():
    assert vocab.level("partial (style-level)") == ("partial", "style-level")
    assert vocab.level("not verified") == ("", "")
    assert vocab.decisions("act;ask;return_control;clarify") == (["ask", "act", "defer"], "")
    assert vocab.decisions("none") == (["none"], "")
    assert vocab.study_value("user_signals", ["edits or corrections", "none"]) == "edits"
    assert vocab.study_value("evaluation_users", "real users") == "real"


def _ev(rate=0.9, mode="full-text", unsupported=()):
    return {"text_mode": mode, "quote_stats": {"quote_verification_rate": rate},
            "verification": {"checks": [{"field": f, "verdict": "unsupported"} for f in unsupported]},
            "mapping": {"per_user": "yes", "across_sessions": "not established", "evaluates_transfer": "no",
                        "interaction_decisions": ["ask", "act"], "what_is_learned": "memory", "summary_100w": "New summary.",
                        "closest_overlap": "Overlap.", "remaining_question": "Question?", "evaluation_users": "simulated users",
                        "user_signals": ["answers to questions"], "evaluation_scale": "1,000 personas"}}


def test_apply_record_rules():
    row = {"key": "k", "title": "t", "per_user": "partial", "across_sessions": "yes", "evaluates_transfer": "",
           "interaction_decisions": "", "summary": "Old.", "annotation_source": "manual"}
    ch = publish.apply_record(row, _ev(unsupported=["per_user"]), today="2026-10-27")
    assert row["per_user"] == "partial"  # verifier said unsupported: kept
    assert row["across_sessions"] == "yes"  # not-stated never erases a definite value
    assert row["evaluates_transfer"] == "no" and row["interaction_decisions"] == "ask;act"
    assert row["evaluation_users"] == "simulated" and row["user_signals"] == "answers"
    assert row["annotation_source"] == "pipeline-fulltext" and row["annotated_on"] == "2026-10-27" and row["quotes_verified"] == "0.9"
    assert {c["field"] for c in ch} >= {"evaluates_transfer", "summary", "usil_relation"}
    untouched = {"key": "k", "per_user": "", "annotation_source": "pending"}
    assert publish.apply_record(untouched, _ev(rate=0.3)) == [] and untouched["annotation_source"] == "pending"
    assert publish.apply_record(untouched, _ev(mode="abstract-only")) == []


def test_check_papers(tmp_path):
    spec = importlib.util.spec_from_file_location("check", os.path.join(ROOT, "scripts", "check_papers.py"))
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    cols = [c["name"] for c in json.load(open(os.path.join(ROOT, "data", "schema.json")))["columns"]]
    good = {c: "" for c in cols} | dict(key="a2026x", title="A", authors="A", year="2026", venue="V", url="https://x.org", category="Human–AI collaboration",
                                         pillars="P1", summary="S.", annotation_source="pending")
    bad = dict(good, key="Bad Key", title="A", category="Robots", pillars="P9", annotation_source="manual", per_user="maybe", interaction_decisions="none;ask")
    path = tmp_path / "papers.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows([good, bad])
    errors, _ = check.check(str(path), os.path.join(ROOT, "data", "schema.json"))
    text = "\n".join(errors)
    for expect in ("key must be lowercase", "same title", "category 'Robots'", "'P9'", "per_user", "cannot be combined", "annotated rows need"):
        assert expect in text, expect
    errors, _ = check.check(os.path.join(ROOT, "data", "papers.csv"), os.path.join(ROOT, "data", "schema.json"))
    assert errors == []


def test_title_matching_and_first_page_check():
    from usil_pipeline import metadata, metadata_llm
    assert metadata.same_title("<i>Human‐aware AI</i>\n —A foundational framework", "Human-aware AI —A foundational framework")
    assert metadata.same_title("Human-robot mutual adaptation in collaborative tasks: Models and experiments",
                               "Human-robot mutual adaptation in collaborative tasks")
    assert not metadata.same_title("Learning to Plan with Personalized Preferences",
                                   "Inferring the Unspoken: Aligning Embodied Agents with Implicit Preferences")

    class FakeLLM:
        def __init__(self, out):
            self.out = out

        def structured(self, **kw):
            return self.out, False
    page = ("Learning and Reasoning about Interruption\nEric Horvitz and Johnson Apacible\nMicrosoft Research\n"
            "Proceedings of the Fifth International Conference on Multimodal Interfaces (ICMI 2003)\n" + "text " * 60)
    good = {"authors": "Eric Horvitz, Johnson Apacible", "authors_source": "Eric Horvitz and Johnson Apacible",
            "venue": "ICMI 2003", "venue_source": "International Conference on Multimodal Interfaces (ICMI 2003)"}
    assert metadata_llm.read_first_page(FakeLLM(good), "m", "k", "t", [page]) == {"authors": good["authors"], "venue": "ICMI 2003"}
    invented = dict(good, venue="CHI 2003", venue_source="CHI 2003, Fort Lauderdale")  # not on the page: dropped
    assert metadata_llm.read_first_page(FakeLLM(invented), "m", "k", "t", [page]) == {"authors": good["authors"]}
