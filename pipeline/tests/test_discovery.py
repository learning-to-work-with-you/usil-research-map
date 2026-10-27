"""Discovery logic without network: identity, dedupe, ranking, record/promote."""
import csv, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usil_pipeline.discovery.identity import Pool, SeedIndex, stable_id
from usil_pipeline.discovery.rank import Rubric, suggest_tier
from usil_pipeline.discovery.run import promote, record
from usil_pipeline.discovery.sources import abstract_from_index, oa_record

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config", "discovery.json")))


def test_abstract_and_record():
    assert abstract_from_index({"agents": [1], "Personal": [0], "learn.": [2]}) == "Personal agents learn."
    r = oa_record({"id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arXiv.2602.16173",
                   "title": "T", "referenced_works": ["https://openalex.org/W9"]})
    assert r["openalex_id"] == "W1" and r["arxiv_id"] == "2602.16173" and r["referenced_works"] == ["W9"]


def test_preprint_and_published_merge():
    pool = Pool()
    pool.add({"doi": "10.48550/arxiv.2401.00001", "arxiv_id": "2401.00001", "title": "Learning When to Ask Users",
              "seed_citers": {"a"}})
    pool.add({"doi": "10.1145/1234", "title": "Learning when to ask users!", "seed_citers": {"b"}, "abstract": "longer"})
    recs = pool.records()
    assert len(recs) == 1 and recs[0]["seed_citers"] == {"a", "b"} and recs[0]["abstract"] == "longer"
    assert stable_id(recs[0]).startswith("doi:")


def test_bridge_merges_two_records():
    pool = Pool()
    pool.add({"doi": "10.1/x", "title": "Alpha paper about agents and users"})
    pool.add({"arxiv_id": "2501.00002", "title": "Completely different title here"})
    pool.add({"doi": "10.1/x", "arxiv_id": "2501.00002", "title": "Alpha paper about agents and users"})
    assert len(pool.records()) == 1


def test_seed_match():
    idx = SeedIndex([{"key": "pahf", "title": "Learning Personalized Agents from Human Feedback",
                      "doi": None, "arxiv_id": "2602.16173"}])
    assert idx.match({"arxiv_id": "2602.16173v2", "title": "x"}) == "pahf"
    assert idx.match({"title": "Learning personalized agents from human feedback"}) == "pahf"
    assert idx.match({"title": "Something unrelated about protein folding"}) is None


def test_ranking_prefers_usil_cell():
    rub = Rubric(CFG)
    idx = SeedIndex([{"key": "s", "title": "Seed paper", "doi": None, "arxiv_id": None}])
    usil = {"title": "Learning personalized clarification policies for assistants",
            "abstract": "We propose an agent that learns when to ask each user from their feedback.",
            "year": 2025, "type": "article", "_citer_weight": 2}
    bg = {"title": "Efficient protein structure prediction", "abstract": "We present a model.",
          "year": 2025, "type": "article", "_citer_weight": 2}
    s1, _, h1, p1 = rub.score(usil, idx, {"P1": 1, "P2": 1, "P3": 1, "P4": 0.2}, 2)
    s2, _, h2, _ = rub.score(bg, idx, {"P1": 1, "P2": 1, "P3": 1, "P4": 0.2}, 2)
    assert s1 > s2 and suggest_tier(h1) == "A" and suggest_tier(h2) == "D" and "P3" in p1


def test_record_and_promote_roundtrip():
    d = tempfile.mkdtemp()
    q, dec, cand, seeds, out = (os.path.join(d, n) for n in ("q.csv", "dec.csv", "c.json", "s.csv", "new.csv"))
    with open(q, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "title", "decision", "tier", "pillars", "notes"])
        w.writeheader()
        w.writerow({"id": "doi:10.1/a", "title": "A", "decision": "include", "tier": "a", "pillars": "P3", "notes": ""})
        w.writerow({"id": "doi:10.1/b", "title": "B", "decision": "", "tier": "", "pillars": "", "notes": ""})
    assert record(q, dec) == (1, 1)
    json.dump([{"id": "doi:10.1/a", "title": "Learning to ask", "authors": "Ada Lovelace, B C", "year": 2025,
                "venue": "V", "url": "https://doi.org/10.1/a", "routes": ["backward:openalex"],
                "suggested_pillars": ["P1"], "suggested_tier": "B"}], open(cand, "w"))
    with open(seeds, "w", newline="") as f:
        csv.writer(f).writerows([["key", "title"], ["lovelace2025old", "Already on the map"]])
    lines, missing = promote(dec, cand, seeds, out)
    assert not missing and lines == ["https://doi.org/10.1/a  # Learning to ask"]
    assert open(out).read().startswith("https://doi.org/10.1/a")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
