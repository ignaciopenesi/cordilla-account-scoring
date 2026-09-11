# serving/ — the pipeline

```bash
python serving/pipeline.py              # 11 of 15 nodes; the rest declare what they need
python serving/pipeline.py --demo       # ALL 15, on synthetic transcripts + simulated outcomes
python serving/pipeline.py --approve    # simulate the SDR manager signing off
python serving/pipeline.py --check-llm  # probe the configured backends and agent routing
python serving/pipeline.py --map        # just the node map
```

**Two modes, deliberately.** Without `--demo` the pipeline runs on the two provided CSVs
and **declares** what it cannot do: 11 nodes run, 2 are partial, 2 are bypassed, each
recording what would unblock it. With `--demo` it runs all 15 end to end on clearly
labelled synthetic inputs from `demo_data/` — because a design you cannot execute is hard
to judge, and harder to poke holes in. Nothing from the demo is presented as a finding
about Cordilla; everything derived from it is marked `SYNTHETIC` or `SIMULATED`.

Runs in about four seconds on the pinned dependencies. No extra packages: `anthropic` is
imported only inside the live-call branch, and the one markdown table is written by hand
rather than pulling in `tabulate`.

## What this is, and why it isn't a list

The audit's finding is that the model's ranking is indistinguishable from noise in-sample
(p = 0.575 against a permutation null) and **below chance forward in time** (AUC 0.474,
against 0.608 for a one-line `ORDER BY sales_contacts_90d DESC`). The nine columns contain
no account-intrinsic signal: the only two that carry any measure what Cordilla already did
to the account.

So a better score is not the deliverable. What this pipeline does is **produce the three
things the data has never had, while it runs**: a control group, the rep's knowledge, and
the prospect's own words. The model is kept — the brief requires scoring the 300, and it
earns its place as **one voice of three**, used only where it disagrees with something
else.

Neither of the two ruled-out shapes appears here. There is no per-account brief, and the
output is not a priority tier or a routing rule — `ALLOCATE` compares *policies* against a
control, which is a different object: it can be wrong, and it tells you when it is.

```
INGEST → VALIDATE → SCORE → ┬ BASELINES
                             ├ FLAGS
                             ├ CONVERSATION_INTENT 🟡
                             └ CALIBRATE_VENDOR ⛔     → RECONCILE 🟡 → ┬ ALLOCATE
                                                                        ├ HYGIENE
                                                                        └ VERDICT
                                                       → PRESCRIBE → ⏸ HITL → EMIT
                                                       ··· 90 days ··· → READOUT ⛔
```

## What runs today and what does not

This distinction is the point, so the pipeline prints it and writes it to `out/run.json`
rather than hiding it. **Bypassed nodes are declared, not stubbed** — each records what it
would produce and what unblocks it.

| node | today | |
|---|---|---|
| `INGEST` | ✅ | CSVs + pickle; declares which capabilities are actually wired |
| `VALIDATE` | ✅ | nulls, ranges, unseen categories, label window, staleness. Touches no CRM data |
| `SCORE` | ✅ | the pickle scores the 300 — required by the brief, and only one input here |
| `BASELINES` | ✅ | `ORDER BY` contacts, random, and what the team does today |
| `FLAGS` | ✅ | per account, the reasons to distrust its score |
| `CONVERSATION_INTENT` | 🟡 | **the four coverage quadrants run** (103 / 67 / 81 / 49); extraction needs transcripts |
| `CALIBRATE_VENDOR` | ⛔ | needs the above; the contrastable set (103 accounts) is already identified |
| `RECONCILE` | 🟡 | model-vs-effort runs (24 / 22 / 9 disagreements); the third voice is missing |
| `ALLOCATE` | ✅ | three matched arms of 30, stale accounts excluded |
| `HYGIENE` | ✅ | CRM contradictions as proposals with evidence and a preventive rule |
| `VERDICT` | ✅ | PSI, week-over-week overlap, concentration, flags in the top K |
| `PRESCRIBE` | ✅ | findings → prioritised actions with an owner |
| `HITL` | ✅ | the one place the graph can cause a write |
| `EMIT` | ✅ | what the rep, the manager and Salesforce each get |
| `READOUT` | ⛔ | needs 90-day outcomes; the arms are assigned and recorded so it can run later |

## The three ideas worth arguing about

**1. The model is one voice of three, never the decision.** `RECONCILE` compares the
score, our own logged effort, and (once recorded) what the prospect said. Agreement teaches
nothing. **Disagreement is the new data** — 24 accounts the model ranks high that nobody
has contacted, 9 the rep keeps working that it ranks low, 22 absorbing effort with nothing
to show. That is the right job for an instrument shown to be noise-level: not to decide,
but to disagree in places worth checking.

**2. Conversation completes the vendor, it does not replace it.** Vendor *coverage*
predicts conversion (8.22% vs 3.94%, p = 0.003). The vendor *score* does not (quintiles
8.3/7.0/9.7/7.0/9.1, Spearman p = 0.42). So the vendor tells you who is visible, not who
wants to buy. `CONVERSATION_INTENT` splits the base into four quadrants and treats each
differently: **103** accounts where both a vendor record and a call exist (the only way to
find out whether the vendor is any good — nobody at Cordilla can answer that today),
**67** where the vendor is blind but a call already happened (the gap can be filled now,
with no new outreach), **81** with a vendor claim never contrasted against anything, and
**49** blind — of which only **10** are genuinely cold. And **41% of all logged contacts
(197 of 481) happened in accounts the vendor never covered**: the signal is already being
generated and thrown away.

**3. Every finding carries its fix.** `VERDICT` and `HYGIENE` do not emit text, they emit
typed findings — `what · evidence · severity · owner · action · cost · expect` — and
`PRESCRIBE` turns them into a ranked list by owner (`crm` / `vendor` / `pipeline` /
`model` / `process`). The manager approves **actions**, not a report. Every hygiene
proposal includes the rule that stops the defect recurring, because a one-off cleanup is
worth much less. The current run surfaces ten, one of them blocking.

## Configuring the agents

Nothing needs configuring to run this: with no keys and no server it uses `template` mode,
which renders each agent's exact prompt plus a worked example of the return. The packet
judges that the same as a live call, and it has the advantage that a reviewer can read the
prompts.

`config.toml` is what you fill in to go live. Two paths are wired, and **the split between
them is a compliance decision, not a preference**:

```toml
[backends.cloud]                          # hosted — best writing quality
kind = "anthropic"
model = "claude-sonnet-5"
api_key_env = "ANTHROPIC_API_KEY"

[backends.local]                          # self-hosted — one adapter covers all of them
kind = "openai_compat"
base_url = "http://localhost:11434/v1"    # Ollama · vLLM :8000 · LM Studio :1234 · LocalAI
model = "qwen3:14b"
json_mode = "auto"
disable_thinking = true

[routing]
conversation_intent   = "local"   # PII — transcripts never leave the network
hygiene_batch         = "local"   # account ids in bulk
run_verdict           = "cloud"   # aggregates only
experiment_card       = "cloud"
disagreement_question = "cloud"
```

**Why one adapter covers every local option:** Ollama, vLLM, LM Studio and LocalAI all
expose the same OpenAI-compatible `/v1/chat/completions` surface. Moving from a laptop to
a GPU box is a `base_url` change, not a code change. Ollama caps at ~4 concurrent
requests and is right for development; vLLM scales with concurrency and is what you would
run in production.

**Why `conversation_intent` is pinned local.** It reads call transcripts. Those are
personal data under GDPR, and are covered by two-party-consent statutes in CA, FL and IL.
Sending them to a hosted API adds a processor to the record, a DPA, and for EU accounts an
international transfer — for the one task that also has the highest volume (every call,
forever) and the lowest writing-quality requirement, since it emits JSON rather than prose.
So extraction stays in the building and drafting goes to the better writer. `route()`
**refuses** to send a `pii`-classified agent to a hosted backend even if the config says
to, and falls back to template with a warning.

    python serving/pipeline.py --check-llm     # probe backends and agent routing

### What the end-to-end demo run actually produced

Running `--demo` exercises the three nodes that cannot otherwise run. What came back is
more useful than a green checkmark:

**The extraction agent, measured against known ground truth** (20 transcripts generated
*from* a known intent level, `qwen3:14b`, 497s for all 20 at 3 workers):

| | |
|---|---|
| `next_step_exact` | **1.00** |
| `intent_level_within_one` | 0.80 |
| `hot_vs_cold_correct` | 0.80 |
| `intent_level_exact` | **0.50** |
| `speaker_role_exact` | **0.05** |
| mean self-reported confidence | 0.62 |

The pattern is consistent and it is the design input: **what is extracted is reliable,
what is inferred is not.** Quote, objections and agreed next step come back clean; the
intent level is a coin flip at the exact grade and the speaker role is worse than random.
So the pipeline raises it as a finding — *"use what is extracted; treat the level as a
hypothesis until READOUT has measured it"* — in the same table as every other defect.
Model size is one line in the routing table, and which size suffices is now a question
that can be answered by re-running `extract_intents.py`, not by preference.

**`CALIBRATE_VENDOR` produced the table nobody at Cordilla can produce today**: on the 12
accounts where both a vendor score and a call exist, vendor and conversation agree 58% of
the time, with 3 accounts the vendor calls hot that the conversation reads cold. On
synthetic data that number means nothing — the *method* is the deliverable, and it costs
nothing once calls are recorded.

**`RECONCILE` settled 4 disagreements with no human involved.** One is the cell that
matters: `ACC-01282`, model score 4.0% (bottom quartile), 3 logged contacts, and the call
says *"We signed off on the budget last week and we need this live before the fiscal year
closes."* The model is wrong, the rep was right, and the system can now prove it rather
than ask.

**`READOUT` produced exactly the null it was built to produce.** Outcomes simulated at the
brief's 3% field rate with **no true difference between arms**: exploit 6.7%, control 3.3%,
explore 3.3% — a 3.3-point spread out of pure noise, every confidence interval overlapping
every other. That is the honest shape of one cycle, and the pipeline files it as a finding:
*one cycle of 30 per arm cannot resolve a realistic difference; commit to two quarters and
say so before the first readout rather than after.*

### What testing this against a real local model showed

Running `conversation_intent` against `qwen3:14b` on Ollama surfaced three things worth
writing down, because they are the difference between a design that would work and one
that does:

| | |
|---|---|
| **`max_tokens` must be generous** | Reasoning models spend tokens thinking before answering. At 1024 the scratchpad consumed the whole budget and the reply came back as an **empty string** — not an error, which is the worst kind of failure. |
| **The strict schema is doing real work** | With `response_format: json_schema`, the 14B model returned every required field. With `json_object` or nothing, it invented its own — `quote` instead of `evidence_quote`, required fields missing. Constrained decoding is what makes a small local model honour a contract. |
| **A 14B model gets the structure right and the judgement wrong** | Full live run, 75s, schema-valid. It pulled the exact quote — *"we've got budget approved for a workflow tool this fiscal year"* — and both objections, correctly. Then labelled the account **E, near-no-intent**, and the VP of Operations as a *user* rather than a decision maker. Structure perfect, both judgement calls wrong. |

That last one matters more than the other two, and it does not get hidden: **the same
standard this audit applied to the inherited model applies to our own agent.** An intent
level from an unvalidated extractor is an unvalidated instrument, whoever built it.

Three things follow, and they are in the design rather than in a caveat:

- The **fields that are extracted** (quote, objections, next step) are reliable at 14B;
  the **level that is inferred** is not. So the quote is what a human reads, and the level
  is what `READOUT` measures against real outcomes before anyone acts on it alone.
- `confidence` is in the contract for this reason, and the 0.75 it returned here was
  *over*-confident — which is itself a calibration target.
- Model size is a tunable, not a constant. 14B is what was on the machine; the routing
  table changes one line to point at a 27B/35B, and the sensible operating point is chosen
  by measuring against outcomes, not by preference. The pipeline is built so that question
  is answerable.

A 14B model on CPU takes 1–3 minutes per transcript. Fine for a nightly batch, useless for
anything interactive — another reason the design is a weekly cycle rather than a live
assistant.

## Where the AI is, and where it deliberately is not

`llm.py` holds five agents. Each is a typed object — `purpose · reads · returns ·
sensitivity · system · template · schema` — not a loose prompt string, and the extracting
one is validated against its schema before anything downstream sees it.

| call | drafts | for |
|---|---|---|
| `experiment_card` | the week's hypotheses and what would kill each | the manager |
| `disagreement_question` | one question under 40 words | the rep |
| `hygiene_batch` | the evidence, the fix, and the preventive rule | the manager |
| `run_verdict` | one paragraph on whether this run is trustworthy | the manager |
| `conversation_intent` | intent level A–F grounded in a verbatim prospect quote, objections, next step | the system |

**Failure is visible, never invented.** If a backend is unreachable, times out, or returns
something off contract, the agent retries and then falls back to template mode **with the
reason printed in place of the output**. It does not guess and it does not silently skip —
a pipeline that quietly produces a plausible answer when its model is down is the failure
mode this whole exercise is about.

**The LLM never decides.** Allocation is rules, approval is the manager, and the only
write path goes through `HITL`. That is deliberate: the documented failure mode of agentic
sales systems is the quiet one — a stage updated that nobody approved — so the graph has
exactly one place it can cause a change, not ten.

## Outputs

`out/rep_worklist.csv` — the assigned accounts, with flags and **no score**.
`out/disagreements.csv` — where the voices disagree, which is where the learning is.
`out/actions.csv` — the ten prescriptions with owner, cost and expected effect.
`out/manager_brief.md` — the verdict, the experiment card, the actions, and what is *not*
running today.
`out/run.json` — the whole state, including every bypass and what unblocks it.

## Preconditions I am not hand-waving

Call recording requires per-call disclosure and transcript-only storage: two-party-consent
states (CA, FL, IL) carry criminal and civil penalties, GDPR reaches 4% of global revenue,
and TCPA runs $500–1,500 per call with no cap. That is a precondition of the design, not a
detail to sort out later. And `sales_contacts_90d` — the one feature with credible signal —
has an unresolved window question that `HYGIENE` raises as **blocking**: if the contact
window overlaps the 90-day outcome window rather than preceding it, that signal is leakage
and nothing built on it is real. One question to the data owner.
