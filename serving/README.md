# serving/ — the pipeline

The operating manual, for whoever runs the weekly cycle or reviews it: what runs today, the arms and
cohorts, the agent configuration, the outputs, how the improvement becomes a number, the rollout
phases, the lines of improvement not yet taken, and the one proposed extension.

```bash
python serving/pipeline.py              # 14 of 15 nodes; READOUT waits for day 90
python serving/pipeline.py --demo       # ALL 15, on simulated day-90 outcomes
python serving/pipeline.py --approve    # simulate the SDR manager signing off
python serving/pipeline.py --check-llm  # probe the configured backends and agent routing
python serving/pipeline.py --map        # just the node map
```

**Two modes, deliberately.** Without `--demo` the pipeline runs on the two provided CSVs
and **declares** what it cannot do: 14 nodes run and 1 is bypassed, each
recording what would unblock it. With `--demo` it runs all 15 end to end on clearly
labelled simulated day-90 outcomes — because a design you cannot execute is hard
to judge, and harder to poke holes in. Nothing from the demo is presented as a finding
about Cordilla; everything derived from it is marked `SIMULATED`.

Runs in about four seconds on the pinned dependencies. No extra packages: `anthropic` is
imported only inside the live-call branch, and the one markdown table is written by hand
rather than pulling in `tabulate`.

## What this is

The audit (`audit/README.md`) found the inherited model's ranking indistinguishable from noise and
its strongest feature to be Cordilla's own contact count. So this graph does not rank on it. It ranks
on rules validated against held-out outcomes, keeps the model as one voice where it disagrees with the
team's own effort, and produces the data Cordilla has never had — a control and, at day 90, a readout.
Neither of the two ruled-out shapes appears: there is no per-account brief, and the output is not a
priority tier — `BUDGET` compares *policies* against a coin-flipped control, which can be wrong and
says when it is.

```
INGEST → VALIDATE → SCORE → CLEAN → RANK → PROVE → RECONCILE → VALUE → BUDGET → ┬ HYGIENE
                                                                                 └ VERDICT
                                                          → PRESCRIBE → ⏸ HITL → EMIT
                                                          ··· 90 days ··· → READOUT ⛔

  proposed, not wired: the conversation layer (extensions/conversation_layer/)
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
| `CLEAN` | ✅ | **the purity agent** (a rules node, not an LLM call): row flags + a variable scorecard on the older labelled rows (every column alone AUC 0.50–0.56) → which columns RANK may use; the rest are reported and given no weight |
| `RANK` | ✅ | every account → intent segment × contact band → action: **first-call** (untouched trial/vendor) · **continue** (1–4 contacts, trial > vendor > none) · **ask** (5+) · **skip** (web/MQL-only — calling never helped) · neutral. Emits `ranked.csv` |
| `PROVE` | ✅ | **uplift by segment** — conversion with 1–4 contacts minus conversion with none, per intent segment (train/test/all, `audit/uplift.json`) · held-out recall · the model as the brief's footnote: memory 31%, out-of-fold 6.7% |
| `RECONCILE` | ✅ | where the model and the team's own effort disagree — 55 accounts; the rep is asked. A third voice, the prospect's words, is **proposed, not wired** (`extensions/conversation_layer/`) |
| `VALUE` | ✅ | the price of an hour (24.6 contacts per conversion), the metric contract, and the bets with their dates |
| `BUDGET` | ✅ | first the coin flip: **a third of the batch goes to the rep as control before any rule runs** (93 of 300 today; the rep works it as usual). Then the cut at the budget K on the rest (207): arms **continue 45 · first-call 15 · control (the whole third)**; cohorts **ask 19 · observe 9 · skip 50 · idle 69** tracked, not called. First-call splits the untouched trials at random — 9 called, 9 observed today — so day 90 measures uplift without selection bias. **The model's top 30 → what happens to each**, every run |
| `HYGIENE` | ✅ | CRM contradictions as proposals with evidence and a preventive rule |
| `VERDICT` | ✅ | is this run trustworthy: PSI (population stability index — feature drift against training), week-over-week overlap of the top 30, score concentration, flags in the top K |
| `PRESCRIBE` | ✅ | findings → prioritised actions with an owner |
| `HITL` | ✅ | human in the loop — the manager signs; the one place the graph can cause a write |
| `EMIT` | ✅ | what the rep, the manager and Salesforce each get |
| `READOUT` | ⛔ | **uplift per segment, unbiased** (first-call vs observe) · settles the bets · scores the conversation layer against reality, once wired · updates the allocation (`_learn`); needs 90-day outcomes |

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
Sending them to a hosted API adds a processor to the record, a DPA (data-processing agreement), and for EU accounts an
international transfer — for the one task that also has the highest volume (every call,
forever) and the lowest writing-quality requirement, since it emits JSON rather than prose.
So extraction stays in the building and drafting goes to the better writer. `route()`
**refuses** to send a `pii`-classified agent to a hosted backend even if the config says
to, and falls back to template with a warning.

    python serving/pipeline.py --check-llm     # probe backends and agent routing


_`conversation_intent` — the conversation layer's extraction agent — stays defined and PII-routed here,
and nothing in the pipeline calls it. Its measurement (v1 → v2.2, three revisions each decided by a
number, and what a real local model showed) is in `extensions/conversation_layer/README.md`._

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
| `conversation_intent` | intent level A–F grounded in a verbatim prospect quote, objections, next step | the system — **the conversation layer, proposed, not wired** |

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

- `out/manager_brief.md` — the weekly page, in reading order: **the scorecard** (the graph against
  three baselines, historical and day-90 columns) · verdict · what changed · the model's top 30 and
  what happens to each · where the metric stands · real outcomes by policy · **how this becomes a
  number** · the experiment · actions · what is dark · *appendix: the prompts*.
- `out/cases.md` — named accounts, real data: the model's top 30 this system will not call as-is ·
  the untouched trials (half called, half observed) · the accounts the model buries that `continue`
  calls first · the skip and ask cohorts, with the hours they hold.
- `out/ranked.csv` — **all 300, by action**: position · action · segment · evidence (uplift of the first
  call, or the rate in conversation, from the older rows) · arm · flags. This is *where the hours go*.
- `out/rep_worklist.csv` — the accounts to work, with an `action` (`call` or `ask`), segment, flags, a
  `question` on the ask rows, **no score and no arm** (a rep who knows which are "the system's" works
  them harder, and the rate rises for a reason the policy did not earn). `observe`, `skip`, `idle` and
  the control third are absent: nobody from here calls them.
- `out/disagreements.csv` — where the voices disagree, which is where the learning is.
- `out/actions.csv` — the eleven prescriptions with owner, cost and expected effect.
- `out/metrics.md` — the metric contract: what an hour costs, the north star and why it is
  not readable yet, the weekly bets with their settlement dates, the guardrails and the kill
  switch. `READOUT` appends the settlement to this same file, so a claim and its outcome live
  in one document.
- `out/cycles.jsonl` — the memory: one line per cycle (arms, outcomes, settled bets; the conversation
  layer's tallies once it is wired). Written by `READOUT`, so today only in `--demo`.
- `out/next_cycle.json` — what READOUT told the next BUDGET, and why. Same origin: `--demo` only today.
- `out/run.json` — the whole state, including every bypass and what unblocks it.

## How the improvement is measured — from experiments to a number

Two kinds of quantity appear in every output. **Observational**: real outcomes, but the reps chose whom
to call — the +10 on untouched trials, the scorecard's 12.2% vs 8.3%, the hours held. **Causal**:
assignment was randomised — first-call vs observe, and the system's two thirds against the control third.
Only the second kind becomes *the number*. The coin flip in `BUDGET` is what makes it possible: two
thirds of the batch go to the system and one third to the rep **before any rule looks at any row**, so
the two are exchangeable and "system vs control" is a comparison of policies, every account counted in
the third it was assigned to, whatever happened after (intention-to-treat; ITT below).

**The ladder, by maturity**

| rung | what | unit · formula | interval | readable at |
|---|---|---|---|---|
| **this week** | hours held (`ask`) or not spent (`skip`) | contacts × 12 min; on the 300 today **38 rep-hours** held or not spent | none — arithmetic on the row | now |
| **day 90 · first causal reading** | first call vs no call on untouched trials (today 9 called / 9 observed) | uplift = k_c/n_c − k_o/n_o, points; two-proportion interval | ±23 pts at 9 vs 9 — uninformative | **138 per group** (5%→15%, 80% power); ~11 weeks of intake at this scale, weeks on the book |
| **day 90 · the policy** | the system's two thirds vs the control third, intention-to-treat (today 207 vs 93) | **I = (p_sys − p_ctl) × N_sys** — incremental conversions; Var = N²·[p_s(1−p_s)/n_s + p_c(1−p_c)/n_c] | wide at one cycle; cumulative across cycles | interval excludes zero |
| **quarter 2 · the north star, in hours** | conversions per 100 rep-hours, cumulative | 100 × k / contacts logged **after assignment** × 5 | Wilson interval on k (a proportion interval that holds at small counts) | ~2,500 per side at a 3% base |

**Aggregating.** Sum increments, not rates — a segment counts in proportion to how many accounts the
system sent there. A cell whose control has fewer than ~10 accounts gets no per-cell estimate; pool it
across cells (Mantel–Haenszel, a weighted pooled estimate) and print *unreadable, n=__*; never fill the gap with a historical rate — that is the
upper bound sneaking back in. **No dollars:** the nine columns hold no deal size, and a dollar figure
is read as a point. Say *"I incremental conversions, between lo and hi, for the same rep-hours"*; the
VP multiplies by their own ticket and the interval survives. If finance later supplies a median
closed-won value, monetise the **lower bound** only.

**The sentence, when it reads:** *"Over N accounts assigned between [date] and [date], the system
produced I more conversions than the reps' own picks would have — between lo and hi — for the same
rep-hours, and it stopped spending H hours where calling has never converted."* H is real in week 1
and decays by design (the 789-contact stock is spent once); N, I, lo, hi are first printed at day 90
as *does not read yet*. Until the interval excludes zero the sentence is spoken with the interval and
without the point.

**Failure modes, and what guards each**

| misreading | why wrong | guard |
|---|---|---|
| week-1 hours as value | a saving, not a conversion; it decays | printed under *held*, with the bet and its date beneath |
| the +10 as the effect | reps chose whom to call — an upper bound | never printed without those words; replaced by the randomised line the day it reads |
| stopping at one cycle | at ~300 per cycle a null simulation produced +4.3 pts [+1.6, +7.1] — a false positive, flagged in `--demo` output | readout dates fixed in advance; `N_MIN_TO_MOVE = 99`; nothing read before the pre-registered n |
| reps know the arm | extra effort on "the system's" accounts | **no `arm` column in the worklist**; contacts per assigned account by arm as a parity guardrail |
| a rep calls an `observe` account | dilutes the difference toward zero | intention-to-treat (observe stays observe); contacts logged on observe counted; per-protocol (by what was actually done) printed beside ITT if above ~10% |
| peeking weekly and stopping when it looks good | inflates false positives | the comparison list, the correction and the interim-look schedule written into `metrics.md` **before** outcomes exist, and validated against the `--demo` null |

**Scaling from the 300 to the book.** The 300 are a sample of tens of thousands. If ~8% of the book are
untouched trials (as in the sample — *estimate*), randomising them 50/50 passes 138 per group in about
a week of assignment and reads at day 90 with a half-width near ±3 pts. Scale collapses the
accumulation, not the outcome window. Four things change: capacity replaces count (rep-hours bind, so
the eligible cell is randomised in full and the uncalled remainder is re-randomised, not left as a
tail); `observe` grows, since it costs nothing and the interval is set by the smaller group; blocking
by rep and segment; and a leading indicator — a next step agreed within 14 days — may be added, under
the same proxy-validity rule as the hours headline (retired if it stops tracking the north star).

## Rolling it out — phases, and what stops each

| phase | when | what happens | stops the next phase if |
|---|---|---|---|
| **0 · Sign** | week 0 | the manager approves the actions; **the blocking question** (does `sales_contacts_90d` precede the outcome window?) goes to the data owner; the comparison list and interim-look schedule are written down before any outcome exists | the contact window **overlaps** the outcome window — then the one signal in this data is leakage and §1 of the proposal is rewritten first |
| **1 · First cycles** | weeks 1–4 | weekly run · coin flip · continue 45 / first-call 15 inside the system's two thirds · untouched trials split half/half · `ask` gets a question · `skip` is never called | rep acceptance of the worklist under 65% for two weeks → the format changes before the arms continue |
| **2 · Accumulation** | weeks 5–13 | first-call vs observe accumulates per segment · `ask` answers return accounts to `continue` or to rest | ask answer rate under 50% → the question changes |
| **3 · First settlement** | day 90 · 2026-10-30 | `READOUT` on real outcomes: the system's two thirds vs the control third (ITT), first-call vs observe by segment, stale vs fresh, the bet marked OPEN or settled, `cycles.jsonl` gets its first real line | a `skip` segment converts above base — the rule was wrong for that segment |
| **4 · The loop turns** | weeks 13–26 | allocation moves only when intervals separate and every arm has n ≥ 99; the weekly headline is checked against the north star and retired in the same report if it stops tracking | the system's two thirds sits below the control third with separated intervals → **kill switch** |
| **5 · It reads** | quarter 2, or weeks on the book | the sentence, with its interval | — |

Two things never change automatically: the model is not retrained, and nothing reaches Salesforce
without the `HITL` signature. Automation means the evidence accumulates and the rules read it.

## Additional lines of improvement

Ranked by expected value per unit of cost. Horizon 1 = the two CSVs only; 2 = one source Cordilla
plausibly already has; 3 = after day 90. Several obvious ideas were tried and lost today (an
effort-normalised ranking key; adding MQL > 0 to a rule; the model as ranker, addition or tiebreaker —
`RESEARCH-LOG.md` 17–23); they are not re-proposed.

| # | line | horizon | addresses | validated by | drop if |
|---|---|---|---|---|---|
| 1 | **Timestamped contact log** — recompute `sales_contacts_90d` in the 90 days before and after each snapshot; the definition that reproduces the column settles H1; then dose per account, not across accounts | 2 | **H1 blocking**, H2, H3 | the recomputed column matches under exactly one window; the +10 reproduces on timestamped rows | it reproduces under neither — provenance unknown |
| 2 | **Pre-registered readout** — the comparison list, multiplicity correction and interim-look boundary written into `metrics.md` before outcomes exist | 1 | conclusions 1, 2, 9 | 200 runs against the `--demo` null hold the nominal false-positive rate | the manager will not sign the list before outcomes |
| 3 | **Book-wide uncalled cohorts** — `observe`, `skip`, `neutral` cost no hours, so run them on the whole book | 2 | H4, H7, H9, north-star power | the 300's uncalled rate reproduces on the book; each cohort read only at n ≥ 99 | the book's uncalled base rate is far from the sample's |
| 4 | **Leading indicator** — meeting booked / opportunity created ≤ 30 days after a call | 2→3 | the 90-day loop | PPV (of those flagged, the share that convert) and lead time on the older 799, checked on the newest 300, then inside the arms under the proxy-validity gate | PPV under ~3× base, or the sign flips between splits |
| 5 | **Vendor coverage list + attribution NULL contract** — why does coverage predict; is 0 web "unmeasured"? | 2 | H5, H9, conclusion 6 | coverage predicts within size and web bands on train, replicates on test | coverage is a function of columns already held |
| 6 | **Product telemetry** for the trial pool — logins, seats, last-active, before `snapshot_date` only | 2 | H8 | usage trend vs conversion on train, sign on test | 0-user and live trials stay equal once telemetry is complete |
| 7 | **Rep identity per contact** — do some reps convert untouched trials and others not? | 2→3 | H3 (the upper bound) | rep effect vs a permutation null; then inside the randomised first-call arm | rep variance ≤ null, or n per rep < 99 |
| 8 | **Deal size** — revenue@K beside recall@K | 2 | the price of an hour | amount vs pre-call columns stable on both halves; bootstrap intervals | three deals carry most revenue |
| 9 | **Randomised stopping rule** at the 3rd contact inside `continue` — who gets a 4th call, with the same hours | 3 | H3 dose (16 / 18 / 15 / 7%), the hand-set 5+ for `ask` | pre-registered; ~138 per group | acceptance < 65% |
| 10 | **Uncut uplift axes** — `account_type` and trial × vendor, one more axis in `uplift.py` | 1 | H6, H3 | sign stable on train / test / all | unstable at n ≈ 60–70 per cell — expected |

Considered and rejected: the model's residual as a feature detector (its one out-of-sample bit is
vendor missingness, already `continue`'s second tier); industry or firmographic priors (weighted zero
by `CLEAN`, range 5.5–7.6%); within-tier reorderings (five tiebreakers tried, all lost).

## Proposed extension — the conversation layer

Designed, measured on synthetic transcripts, and kept out of the graph until real call transcripts
exist for accounts with a known outcome. It would work the margin — the eight held-out buyers no column
separates — and be judged like every other mechanism: recall on the margin with it against without, at
day 90. Precondition: recording with per-call disclosure on the 67 fill-gap accounts, which already
receive calls. Design, measured contract and how to wire it back: `extensions/conversation_layer/`.

## Preconditions I am not hand-waving

Call recording requires per-call disclosure and transcript-only storage: two-party-consent
states (CA, FL, IL) carry criminal and civil penalties, GDPR reaches 4% of global revenue,
and TCPA (the US telemarketing statute) runs $500–1,500 per call with no cap. That is a precondition of the design, not a
detail to sort out later. And `sales_contacts_90d` — the one feature with credible signal —
has an unresolved window question that `HYGIENE` raises as **blocking**: if the contact
window overlaps the 90-day outcome window rather than preceding it, that signal is leakage
and nothing built on it is real. One question to the data owner.
