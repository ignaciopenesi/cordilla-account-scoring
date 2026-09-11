"""
Generate SYNTHETIC call transcripts so the pipeline can be run end to end.

⚠️  These are fabricated. They are not Cordilla data and they never touch the two CSVs.
    They exist for one reason: CONVERSATION_INTENT, CALIBRATE_VENDOR and READOUT cannot
    run without transcripts, and a design you cannot execute is hard to judge. Everything
    produced from them is labelled `demo` in the output.

Each transcript is generated from a known intent level, and that level is written to
ground_truth.json. So running the extractor over them is not just a demo — it *measures*
the agent, which is the standard this repo applies to every other instrument in it.

    python extensions/conversation_layer/demo_data/make_transcripts.py
"""
import json
import random
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent

# level -> (what the prospect says that determines it, objections, whether a next step lands)
SCRIPTS = {
    "A": [("We signed off on the budget last week and we need this live before the fiscal "
           "year closes in November. I'm ready to talk contracts.", ["procurement timeline"], True),
          ("Board approved the spend. We want to be in production by Q4, so whatever your "
           "onboarding looks like, we need it to fit that.", ["implementation speed"], True)],
    "B": [("We've got budget approved for this fiscal year, it came through in June. We're "
           "just deciding between you and two others.", ["incumbent tool", "price"], True),
          ("There's money allocated. I'm comparing three vendors and I need to see the "
           "multi-region piece work before I commit.", ["technical fit"], True)],
    "C": [("We're building the business case. Nothing's approved yet but my director asked "
           "me to get numbers together for the planning cycle.", ["no budget yet"], True),
          ("I'd need to justify this internally. If you can help me with an ROI story I "
           "can take it to my VP next month.", ["internal buy-in"], False)],
    "D": [("Honestly we're just looking at what's out there. Nothing's driving this right "
           "now, I'm keeping an eye on the space.", ["no trigger event"], False),
          ("It's on the roadmap for sometime next year maybe. Not this quarter.", ["timing"], False)],
    "E": [("I'm not the right person for this, you'd want to talk to whoever owns ops. I "
           "just took the call because it landed in my inbox.", ["wrong contact"], False),
          ("We looked at this category two years ago and decided to build internally. "
           "That's still where we are.", ["built in-house"], False)],
    "F": [("We just renewed with our current vendor for three years. Please take us off "
           "your list.", ["locked into contract"], False),
          ("I'd rather you didn't call again. We're not interested.", ["explicit no"], False)],
}

OPENERS = [
    "Thanks for making time. Last we spoke you'd mentioned the ops team was drowning in handoffs.",
    "Appreciate you picking up. I wanted to follow up on the whitepaper your team downloaded.",
    "Thanks for the fifteen minutes. I know you're mid-quarter so I'll be quick.",
    "Good to finally connect. Your colleague suggested I reach out about the approvals workflow.",
]
PROBES = [
    "Is that still being handled manually?",
    "How are you solving that today?",
    "What's driving the timing on this?",
    "Who else would need to be involved in a decision like that?",
]
ROLES = [("VP Operations", "decision_maker"), ("Director of RevOps", "decision_maker"),
         ("Ops Manager", "user"), ("Operations Analyst", "user"),
         ("Executive Assistant", "gatekeeper")]
PURPOSES = ["discovery", "follow_up", "negotiation"]


def build(account_id: str, level: str, seed: int) -> tuple[str, dict]:
    rng = random.Random(seed)
    quote, objections, next_step = rng.choice(SCRIPTS[level])
    role_title, role_key = rng.choice(ROLES if level not in "AB" else ROLES[:2])
    purpose = rng.choice(PURPOSES)
    date = f"2026-0{rng.randint(5, 7)}-{rng.randint(10, 28)}"

    lines = [f"[Call · {account_id} · {date} · {rng.randint(6, 22)} min · recorded with disclosure]", "",
             f"REP (Cordilla): {rng.choice(OPENERS)}", "",
             f"PROSPECT ({role_title}): Yeah — it's not where we want it. "
             f"{'It got worse, actually.' if rng.random() > .5 else 'Same as it was.'}", "",
             f"REP: {rng.choice(PROBES)}", "",
             f"PROSPECT ({role_title}): {quote}", ""]
    if objections:
        lines += [f"REP: Understood. What would you need to see to get past {objections[0]}?", "",
                  f"PROSPECT ({role_title}): Proof, mostly. We've been told yes before and it "
                  f"didn't hold up.", ""]
    if next_step:
        lines += ["REP: Would a working session with our ops lead help? Not a demo — the actual config.", "",
                  f"PROSPECT ({role_title}): That would help. Let's find time in the next couple of weeks.", ""]
    else:
        lines += ["REP: Would it be useful to send something over for later?", "",
                  f"PROSPECT ({role_title}): You can, but I wouldn't expect much movement.", ""]

    truth = {"account_id": account_id, "intent_level": level, "speaker_role": role_key,
             # ready_to_act is the v2 primary field: the prospect stated an allocated
             # budget or a concrete timeline. In these scripts that is exactly A and B.
             "ready_to_act": level in ("A", "B"),
             "call_purpose": purpose, "next_step_agreed": next_step,
             "objections": objections, "quote": quote}
    return "\n".join(lines), truth


def main() -> None:
    score = pd.read_csv(ROOT / "data/accounts_to_score.csv")
    had_call = score[score.sales_contacts_90d > 0]
    has_vendor = had_call[had_call.intent_score.notna()]
    no_vendor = had_call[had_call.intent_score.isna()]

    # Cover both quadrants that a transcript can reach, and spread the levels so the
    # extractor is measured across the whole range rather than on easy cases.
    picks = (list(has_vendor.account_id.head(12)) + list(no_vendor.account_id.head(8)))
    levels = list("ABCDEF") * 4
    rng = random.Random(11)
    rng.shuffle(levels)

    out_dir = HERE / "transcripts"
    out_dir.mkdir(exist_ok=True)
    for f in out_dir.glob("*.txt"):
        f.unlink()

    truths = []
    for i, (acc, lvl) in enumerate(zip(picks, levels)):
        text, truth = build(acc, lvl, seed=100 + i)
        (out_dir / f"{acc}.txt").write_text(text)
        truths.append(truth)

    (HERE / "ground_truth.json").write_text(json.dumps(truths, indent=2))
    dist = pd.Series([t["intent_level"] for t in truths]).value_counts().sort_index()
    print(f"wrote {len(truths)} synthetic transcripts to {out_dir.relative_to(ROOT)}")
    print(f"  vendor record + call : {sum(a in set(has_vendor.account_id) for a in picks)}")
    print(f"  no vendor record     : {sum(a in set(no_vendor.account_id) for a in picks)}")
    print(f"  intent levels        : {dict(dist)}")
    print(f"  ground truth         : {(HERE / 'ground_truth.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
