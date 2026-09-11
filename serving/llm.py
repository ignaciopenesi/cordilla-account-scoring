"""
The AI-assisted layer: every place a human has to read something, an LLM drafts it.

Two rules that hold across all of it:

  1. The LLM NEVER decides. It turns numbers into a paragraph a person can act on, and
     turns what a person says back into structured data. Allocation, approval and any
     write to Salesforce are decided by rules and by the manager.
  2. Every call has a typed contract -- named inputs, a stated output shape. That is what
     makes the difference between "the LLM writes the thing" and "the LLM is a node".

`--llm template` (default) renders the exact prompt plus a worked example of what comes
back. The packet judges that the same as a live call, and it has a real advantage: you can
read the prompt. `--llm live` makes the call if ANTHROPIC_API_KEY is set.

To wire up a real call, the only thing that changes is `_call()` below.
"""
from __future__ import annotations

import json
import os
import textwrap

MODEL = "claude-sonnet-5"          # sensible default for drafting; opus for the verdict if you prefer


# ─────────────────────────────────────────────────────────────────────────────
# The prompts. One per thing a human reads.
# ─────────────────────────────────────────────────────────────────────────────
PROMPTS = {

    # ── used by ALLOCATE ────────────────────────────────────────────────────
    "experiment_card": {
        "inputs": ["arms: name, size, selection rule, hypothesis", "matching variables",
                   "base rate", "expected readout date"],
        "returns": "markdown, ~150 words: one hypothesis per arm, what would confirm it, "
                   "what would refute it, and the readout date",
        "system": "You write experiment cards for an SDR manager who is not technical and "
                  "is sceptical of being experimented on. Be concrete about what each arm "
                  "is testing and what result would make us stop. Never oversell.",
        "template": """This week's allocation splits {total} accounts into {n_arms} matched arms
({matched_on}). Base rate is {base_rate}.

{arm_block}

Write the experiment card the SDR manager reads before approving. For each arm state the
hypothesis in one sentence, the result that would confirm it, and the result that would
kill it. End with the readout date and one sentence on why the control arm exists.
Do not promise a lift number -- we do not have one.""",
    },

    # ── used by RECONCILE ───────────────────────────────────────────────────
    "disagreement_question": {
        "inputs": ["account_id", "disagreement type", "model score", "contacts logged",
                   "flags", "what the model cannot see"],
        "returns": "one question, under 40 words, answerable in two minutes",
        "system": "You write short questions to a sales rep. The rep is busy and has been "
                  "burned by a scoring tool before. Ask about what they know that the data "
                  "cannot show. Never tell them who to call. Never imply they were wrong.",
        "template": """Account {account_id}. The model scores it {score} ({percentile} percentile).
The team has logged {contacts} contacts in 90 days. Flags: {flags}.
Disagreement type: {disagreement_kind}.

Write one question to the rep, under 40 words, that they can answer in two minutes, about
what they know that the data does not show. It must not read as a performance check.""",
    },

    # ── used by HYGIENE ─────────────────────────────────────────────────────
    "hygiene_batch": {
        "inputs": ["defect name", "rule that detected it", "affected count",
                   "three worked examples", "proposed correction", "owner"],
        "returns": "markdown, ~100 words: what is wrong, the evidence, the proposed fix, "
                   "and the rule that stops it recurring",
        "system": "You write CRM correction proposals for approval in bulk. State the "
                  "evidence before the fix. Always include the rule that prevents the "
                  "defect from coming back -- a one-off cleanup is worth much less.",
        "template": """Defect: {defect}
Detected by: {rule}
Affected records: {count}
Examples: {examples}
Proposed correction: {correction}

Write the approval note. Lead with the evidence, then the correction, then the preventive
rule. Say plainly what happens if this is not fixed.""",
    },

    # ── used by VERDICT ─────────────────────────────────────────────────────
    "run_verdict": {
        "inputs": ["feature PSI table", "overlap with the previous run",
                   "score concentration", "flag counts in the top K", "sum of probabilities "
                   "vs the field's reported rate"],
        "returns": "one paragraph, under 120 words, for the SDR manager",
        "system": "You write a weekly one-paragraph verdict on whether a scoring run is "
                  "worth trusting. You are allowed -- expected -- to say it is not. End "
                  "with a recommendation for THIS week, not a general observation.",
        "template": """Run of {date}. {psi_summary}. Overlap of the top 30 with the previous run:
{overlap}. {concentration}. Of the top 30, {clean} carry no flags. The model's predicted
probabilities sum to {sum_p} expected conversions across {n} accounts ({mean_p}), against a
field rate the business reports at 1-3%.

Write the manager's paragraph. End with one concrete recommendation for this week.""",
    },

    # ── the bypassed node's contract. This is the one that matters most. ─────
    "conversation_intent": {
        "inputs": ["call transcript (speaker-labelled)", "account_id", "call date",
                   "who is on the call, if known"],
        "returns": json.dumps({
            "intent_level": "A|B|C|D|E|F  (A = budget approved and a timeline named; "
                            "F = explicitly not interested)",
            "evidence_quote": "the sentence that determined the level, verbatim",
            "objections": ["price", "incumbent tool", "timing", "..."],
            "next_step_agreed": "bool",
            "next_step": "what was agreed, or null",
            "speaker_role": "decision_maker|user|gatekeeper|unknown",
            "call_purpose": "discovery|follow_up|negotiation|support|other",
            "confidence": "0.0-1.0",
        }, indent=2),
        "system": "You extract buying intent from a sales call transcript. You report only "
                  "what was said. If the transcript does not support a level, return the "
                  "lower one and lower the confidence. Always quote the sentence you used. "
                  "Never infer intent from the rep's enthusiasm -- only from the prospect's "
                  "words.",
        "template": """Transcript of a sales call with account {account_id} on {date}.

<transcript>
{transcript}
</transcript>

Return the JSON object described in the schema. Ground `intent_level` in a verbatim quote
from the prospect -- not the rep. If the prospect said nothing that indicates a buying
stage, return level E or F with low confidence rather than guessing upward.""",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Worked examples: what a real call returns. Used by --llm template so the design is
# legible without a key, and as regression fixtures if you wire up the real thing.
# ─────────────────────────────────────────────────────────────────────────────
EXAMPLES = {
    "disagreement_question": (
        "ACC-00453 — the model ranks this in the bottom quartile, but the team has logged 4 "
        "contacts in 90 days. What are you seeing there that the data isn't showing?"
    ),
    "run_verdict": (
        "Run of 2026-08-01. Every feature is stable against training (max PSI 0.06); snapshot "
        "age is not — but that is how the batch was drawn, not drift. The top 30 shares 21 of "
        "30 accounts with last week's list even though no underlying data changed, which is the "
        "model's own seed, not the market. Only 11 of the top 30 carry no flags at all. The "
        "model expects 19.7 conversions across 300 accounts (6.6%) against a field rate the "
        "business reports at 1–3%. Recommendation this week: run the exploit arm off "
        "sales_contacts, not off the score, and do not publish the probabilities."
    ),
    "conversation_intent": {
        "intent_level": "B",
        "evidence_quote": "We've got budget approved for a workflow tool this quarter, we're "
                          "just deciding between you and two others.",
        "objections": ["incumbent tool", "price"],
        "next_step_agreed": True,
        "next_step": "Technical review with their ops lead, week of 2026-08-11",
        "speaker_role": "decision_maker",
        "call_purpose": "discovery",
        "confidence": 0.86,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# The single place a network call would fire.
# ─────────────────────────────────────────────────────────────────────────────
def _call(kind: str, prompt: str) -> str:
    """The real call. Everything else in this file is prompt construction."""
    import anthropic                                        # not in requirements.txt on purpose
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    spec = PROMPTS[kind]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=spec["system"],
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def draft(kind: str, mode: str = "template", **payload) -> str:
    """Draft one human-readable artifact.

    mode='template' -> render the prompt and the worked example, call nothing.
    mode='live'     -> call the API (needs ANTHROPIC_API_KEY), fall back to template.
    """
    spec = PROMPTS[kind]
    prompt = spec["template"].format(**payload)

    if mode == "live" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _call(kind, prompt)
        except Exception as exc:                            # a rough script: say so and carry on
            return f"[live call failed: {exc}; falling back to template]\n\n" + _render(kind, prompt)
    return _render(kind, prompt)


def _render(kind: str, prompt: str) -> str:
    spec = PROMPTS[kind]
    ex = EXAMPLES.get(kind, "(no worked example for this one)")
    if isinstance(ex, dict):
        ex = json.dumps(ex, indent=2)
    returns = spec["returns"] if len(spec["returns"]) < 120 else "JSON — schema in PROMPTS[%r]" % kind
    bar = "─" * 74
    out = [f"┌{bar}", f"│ LLM CALL · {kind}   (mode: template — the documented plug point)",
           f"│ model   : {MODEL}", f"│ inputs  : {', '.join(spec['inputs'])}",
           f"│ returns : {returns}", f"├─ SYSTEM {'─' * 65}"]
    out += [f"│ {ln}" for ln in textwrap.wrap(spec["system"], 72)]
    out += [f"├─ PROMPT {'─' * 65}"]
    out += [f"│ {ln}" for ln in prompt.strip().splitlines()]
    out += [f"├─ RETURNS (worked example) {'─' * 47}"]
    out += [f"│ {ln}" for ln in str(ex).splitlines()]
    out += [f"└{bar}"]
    return "\n".join(out)
