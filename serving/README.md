# serving/ — the pipeline

```bash
python serving/pipeline.py              # dry run: scores, allocates, proposes. Writes nothing outside out/
python serving/pipeline.py --approve    # simulate the SDR manager signing off
python serving/pipeline.py --llm live   # make the real LLM calls (needs ANTHROPIC_API_KEY)
python serving/pipeline.py --map        # just the node map
```

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

## Where the AI is, and where it deliberately is not

`llm.py` holds five prompts, each with a typed contract — named inputs, a stated return
shape. Default mode renders the prompt plus a worked example (the packet judges that the
same as a live call, and it has the advantage that you can read the prompt); `--llm live`
calls the API. `_call()` is the single place a network request would fire.

| call | drafts | for |
|---|---|---|
| `experiment_card` | the week's hypotheses and what would kill each | the manager |
| `disagreement_question` | one question under 40 words | the rep |
| `hygiene_batch` | the evidence, the fix, and the preventive rule | the manager |
| `run_verdict` | one paragraph on whether this run is trustworthy | the manager |
| `conversation_intent` | intent level A–F grounded in a verbatim prospect quote, objections, next step | the system |

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
