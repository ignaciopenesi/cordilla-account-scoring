# serving/ — the pipeline

```bash
python serving/pipeline.py              # 14 of 15 nodes; READOUT waits for day 90
python serving/pipeline.py --demo       # ALL 15, on synthetic transcripts + simulated outcomes
python serving/pipeline.py --approve    # simulate the SDR manager signing off
python serving/pipeline.py --check-llm  # probe the configured backends and agent routing
python serving/pipeline.py --map        # just the node map
```

**Two modes, deliberately.** Without `--demo` the pipeline runs on the two provided CSVs
and **declares** what it cannot do: 14 nodes run and 1 is bypassed, each
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
output is not a priority tier or a routing rule — `BUDGET` compares *policies* against a
control, which is a different object: it can be wrong, and it tells you when it is.

```
INGEST → VALIDATE → SCORE → CLEAN → RANK → PROVE → RECONCILE → VALUE → BUDGET → ┬ HYGIENE
                                                                                 └ VERDICT
                                                          → PRESCRIBE → ⏸ HITL → EMIT
                                                          ··· 90 days ··· → READOUT ⛔

  proposed, not wired: the conversation layer (proposal/conversation_layer/)
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
| `CLEAN` | ✅ | **the purity agent**: row flags + a variable scorecard on the older labelled rows (every column alone AUC 0.50–0.56) → which columns RANK may use; the rest are reported and given no weight |
| `RANK` | ✅ | every account → intent segment × contact band → action: **first-call** (untouched trial/vendor) · **continue** (1–4 contacts, trial > vendor > none) · **ask** (5+) · **skip** (web/MQL-only — calling never helped) · neutral. Emits `ranked.csv` |
| `PROVE` | ✅ | **uplift by segment** (train/test/all, `audit/uplift.json`) · held-out recall · the model as the brief's footnote: memory 31%, out-of-fold 6.7% |
| `RECONCILE` | ✅ | where the model and the team's own effort disagree — 55 accounts; the rep is asked. A third voice, the prospect's words, is **proposed, not wired** (`proposal/conversation_layer/`) |
| `VALUE` | ✅ | the price of an hour (24.6 contacts per conversion), the metric contract, and the bets with their dates |
| `BUDGET` | ✅ | cut at K: arms **continue 45 · first-call 15 · control 30**; cohorts **ask · observe · skip** tracked, not called. First-call splits untouched trials at random — half called, half observed — so day 90 measures uplift without selection bias. **The model's top 30 → what happens to each**, every run |
| `HYGIENE` | ✅ | CRM contradictions as proposals with evidence and a preventive rule |
| `VERDICT` | ✅ | PSI, week-over-week overlap, concentration, flags in the top K |
| `PRESCRIBE` | ✅ | findings → prioritised actions with an owner |
| `HITL` | ✅ | the one place the graph can cause a write |
| `EMIT` | ✅ | what the rep, the manager and Salesforce each get |
| `READOUT` | ⛔ | **uplift per segment, unbiased** (first-call vs observe) · settles the bets · scores the agent against reality · updates the allocation (`_learn`); needs 90-day outcomes |

## Why it is built this way

The argument — the model as one voice, the conversation layer as a proposal, the metric as two numbers with a structural hierarchy, every finding carrying its fix — is made once, in `PROPOSAL.md`, with the evidence in `audit/README.md`. This file is the operating manual.

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


_The extraction agent's measurement — v1 → v2.2, three revisions each decided by a number, and
what testing it against a real local model showed — moved to `proposal/conversation_layer/README.md`
when the layer left the graph. The routing and backend configuration above is unchanged: the
`conversation_intent` agent stays defined and PII-routed, and nothing in the pipeline calls it._

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
| `conversation_intent` | intent level A–F grounded in a verbatim prospect quote, objections, next step | the system | **proposed, not wired** |

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

`out/manager_brief.md` — the weekly page, in reading order: **the scorecard** (the graph against
three baselines, historical and day-90 columns) · verdict · what changed · the model's top 30 and
what happens to each · where the metric stands · real outcomes by policy · the experiment ·
actions · what is dark · *appendix: the prompts*.
`out/cases.md` — named accounts, real data: the model's top 30 this system will not call as-is ·
the untouched trials (half called, half observed) · the accounts the model buries that `continue`
calls first · the skip and ask cohorts, with the hours they hold.
`out/ranked.csv` — **all 300, by action**: position · action · segment · evidence (uplift of the first
call, or the rate in conversation, from the older rows) · arm · flags. This is *where the hours go*.
`out/rep_worklist.csv` — the assigned accounts, with an `action` (`call` or `ask`), segment, flags, a
`question` on the ask rows, and **no score**. `observe` and `skip` are deliberately absent:
nobody calls them.
`out/disagreements.csv` — where the voices disagree, which is where the learning is.
`out/actions.csv` — the twelve prescriptions with owner, cost and expected effect.
`out/metrics.md` — the metric contract: what an hour costs, the north star and why it is
not readable yet, the weekly bets with their settlement dates, the guardrails and the kill
switch. `READOUT` appends the settlement to this same file, so a claim and its outcome live
in one document.
`out/cycles.jsonl` — the memory: one line per cycle (arms, outcomes, settled bets, agent tallies).
`out/next_cycle.json` — what READOUT told the next BUDGET, and why.
`out/run.json` — the whole state, including every bypass and what unblocks it.

## Preconditions I am not hand-waving

Call recording requires per-call disclosure and transcript-only storage: two-party-consent
states (CA, FL, IL) carry criminal and civil penalties, GDPR reaches 4% of global revenue,
and TCPA runs $500–1,500 per call with no cap. That is a precondition of the design, not a
detail to sort out later. And `sales_contacts_90d` — the one feature with credible signal —
has an unresolved window question that `HYGIENE` raises as **blocking**: if the contact
window overlaps the 90-day outcome window rather than preceding it, that signal is leakage
and nothing built on it is real. One question to the data owner.
