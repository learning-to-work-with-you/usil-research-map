"""Literature discovery for the USIL research map.

  discover  Find papers the map is missing: backward citations of every map paper, forward
            citations of core papers, deduplicated and ranked into a short review queue.
            Free (OpenAlex + Semantic Scholar); no LLM calls.
  record    Save the decisions you typed into review_queue.csv (include / maybe / exclude).
  promote   List the included papers for `python -m usil_pipeline add --from` (reads and adds each one).

Typical loop
  python -m usil_pipeline.discovery discover
  # edit out_discovery/review_queue.csv: decision, tier, pillars, notes
  python -m usil_pipeline.discovery record
  python -m usil_pipeline.discovery promote
  python -m usil_pipeline add --from out_discovery/to_add.txt                        # read + add each paper
"""
import argparse, json, os, sys

from ..cli import load_env
from .run import discover, promote, record
from .sources import BudgetExhausted

DEFAULT_SEEDS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "papers.csv")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="usil_pipeline.discovery", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="collect, deduplicate, and rank candidate papers")
    d.add_argument("--seeds", default=DEFAULT_SEEDS, help="the map's source CSV")
    d.add_argument("--out", default="out_discovery")
    d.add_argument("--config", default="config/discovery.json")
    d.add_argument("--cache", default=".cache/discovery")
    d.add_argument("--registry", default="data/discovery/registry.json")
    d.add_argument("--decisions", default="data/discovery/review_decisions.csv")
    d.add_argument("--forward", choices=["none", "core", "all"], help="which map papers to follow forward (default: config)")
    d.add_argument("--queue-size", type=int)
    d.add_argument("--no-s2", action="store_true", help="skip the Semantic Scholar reference fallback (faster)")

    r = sub.add_parser("record", help="save decisions from a filled-in review_queue.csv")
    r.add_argument("--queue", default="out_discovery/review_queue.csv")
    r.add_argument("--decisions", default="data/discovery/review_decisions.csv")

    p = sub.add_parser("promote", help="list included papers for `add --from`")
    p.add_argument("--decisions", default="data/discovery/review_decisions.csv")
    p.add_argument("--candidates", default="out_discovery/candidates.json")
    p.add_argument("--seeds", default=DEFAULT_SEEDS)
    p.add_argument("--out", default="out_discovery/to_add.txt")

    a = ap.parse_args(argv)
    load_env()

    if a.cmd == "discover":
        cfg = json.load(open(a.config))
        if a.queue_size:
            cfg["budget"]["queue_size"] = a.queue_size
        try:
            log = discover(cfg, a.seeds, a.out, a.cache, a.registry, a.decisions, forward=a.forward, no_s2=a.no_s2)
        except BudgetExhausted as e:
            sys.exit(f"\nStopped: {e}")
        print(f"\n{log['candidates']} candidates ({log['new_candidates']} new) from {log['seeds']} map papers; "
              f"{log['dropped']['already_on_map']} already on the map were skipped.")
        print(f"Suggested tiers: {log['tiers']}.  Review queue: {log['queue']} papers -> {a.out}/review_queue.md")
        if log["seeds_unresolved"]:
            print(f"Not found in OpenAlex ({len(log['seeds_unresolved'])}): {', '.join(log['seeds_unresolved'][:12])}"
                  + (" ..." if len(log["seeds_unresolved"]) > 12 else ""))
    elif a.cmd == "record":
        n, total = record(a.queue, a.decisions)
        print(f"Recorded {n} decisions ({total} total) in {a.decisions}.")
    elif a.cmd == "promote":
        rows, missing = promote(a.decisions, a.candidates, a.seeds, a.out)
        print(f"Listed {len(rows)} papers in {a.out}.")
        if missing:
            print(f"{len(missing)} included ids are not in {a.candidates} (rerun discover): {', '.join(missing[:5])}")
        if rows:
            print(f"Next: python -m usil_pipeline add --from {a.out}   # read, label, and add each to data/papers.csv")


if __name__ == "__main__":
    sys.exit(main())
