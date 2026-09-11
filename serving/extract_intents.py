"""
Batch extraction: run the `conversation_intent` agent over the transcripts and cache the
results. This is the nightly job in the real system -- transcripts arrive continuously and
are processed out of band, so the weekly pipeline reads a cache rather than calling a model
300 times while a manager waits.

Because the demo transcripts carry a known intent level, this also MEASURES the agent:
how often does it recover the level, the role, the next step? That number goes in the
report. An extractor nobody measured is exactly the instrument this whole repo is about.

    python serving/extract_intents.py                 # resume; only processes what is missing
    python serving/extract_intents.py --force         # re-extract everything
    python serving/extract_intents.py --workers 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo_data"
CACHE = DEMO / "intents.json"


def extract_one(path: Path, mode: str) -> tuple[str, dict | None, str]:
    acc = path.stem
    raw = llm.draft("conversation_intent", mode=mode, account_id=acc,
                    date="(see transcript header)", transcript=path.read_text())
    if raw.lstrip().startswith("{"):
        try:
            return acc, json.loads(raw), ""
        except json.JSONDecodeError as exc:
            return acc, None, f"unparseable: {exc}"
    first = next((ln for ln in raw.splitlines() if "AGENT ·" in ln), raw[:80])
    return acc, None, first.strip("│ ").strip()


def score_against_truth(results: dict) -> dict:
    truth_path = DEMO / "ground_truth.json"
    if not truth_path.exists():
        return {}
    truth = {t["account_id"]: t for t in json.loads(truth_path.read_text())}
    got = {k: v for k, v in results.items() if v}
    if not got:
        return {}

    def rate(fn):
        return sum(fn(truth[k], v) for k, v in got.items() if k in truth) / len(got)

    order = "ABCDEF"
    return {
        "n_extracted": len(got),
        # v2 primary: the binary the pipeline actually routes on
        "ready_to_act_exact": rate(lambda t, v: t["ready_to_act"] == v.get("ready_to_act")),
        "ready_to_act_false_cold": sum(
            t["ready_to_act"] and not v.get("ready_to_act") for k, v in got.items()
            for t in [truth[k]] if k in truth),
        "ready_to_act_false_hot": sum(
            (not t["ready_to_act"]) and v.get("ready_to_act") for k, v in got.items()
            for t in [truth[k]] if k in truth),
        "next_step_exact": rate(lambda t, v: t["next_step_agreed"] == v.get("next_step_agreed")),
        # v2 secondary: kept for context, not routed on
        "intent_level_exact": rate(lambda t, v: t["intent_level"] == v.get("intent_level")),
        "intent_level_within_one": rate(
            lambda t, v: v.get("intent_level") in order
            and abs(order.index(t["intent_level"]) - order.index(v["intent_level"])) <= 1),
        "hot_vs_cold_correct": rate(
            lambda t, v: (t["intent_level"] in "ABC") == (v.get("intent_level", "F") in "ABC")),
        "mean_confidence": sum(v.get("confidence", 0) for v in got.values()) / len(got),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--mode", default="live", choices=["live", "template"])
    args = ap.parse_args()

    files = sorted((DEMO / "transcripts").glob("*.txt"))
    if not files:
        print("no transcripts — run serving/demo_data/make_transcripts.py first")
        return

    cache = {} if args.force or not CACHE.exists() else json.loads(CACHE.read_text()).get("intents", {})
    todo = [f for f in files if f.stem not in cache]
    print(f"{len(files)} transcripts · {len(cache)} cached · {len(todo)} to extract "
          f"(mode={args.mode}, {args.workers} workers)")
    if todo:
        print(f"routed to backend '{llm.CONFIG.get('routing', {}).get('conversation_intent')}' "
              f"— a local model takes 1-3 min each, so this is the out-of-band job\n")

    t0, failures = time.time(), {}
    if todo:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for acc, obj, err in pool.map(lambda f: extract_one(f, args.mode), todo):
                if obj:
                    cache[acc] = obj
                    print(f"  ✓ {acc}  act={str(obj.get('ready_to_act')):<5} "
                          f"({obj.get('ready_because')})  level {obj.get('intent_level')}  "
                          f"conf {obj.get('confidence')}  ({len(cache)}/{len(files)})")
                else:
                    failures[acc] = err
                    print(f"  ✗ {acc}  {err[:90]}")

    metrics = score_against_truth(cache)
    CACHE.write_text(json.dumps({
        "_warning": "SYNTHETIC demo data. Not Cordilla data. See demo_data/README.md.",
        "extracted_with": llm.CONFIG.get("backends", {})
                             .get(llm.CONFIG.get("routing", {}).get("conversation_intent"), {})
                             .get("model", "template"),
        "metrics_vs_ground_truth": metrics,
        "failures": failures,
        "intents": cache,
    }, indent=2))

    print(f"\n{len(cache)}/{len(files)} extracted in {time.time() - t0:.0f}s → "
          f"{CACHE.relative_to(HERE.parent)}")
    if metrics:
        print("\nAGENT QUALITY vs known ground truth")
        print("─" * 54)
        for k, v in metrics.items():
            print(f"  {k:<26} {v:.2f}" if isinstance(v, float) else f"  {k:<26} {v}")
        print("\n  This is the measurement the audit demanded of the inherited model,")
        print("  applied to the agent this repo introduces.")


if __name__ == "__main__":
    main()
