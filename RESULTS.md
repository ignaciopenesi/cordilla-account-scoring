# Results — what each step yields, and what is verified

Two tiers of evidence, kept apart throughout:

- **REAL** — the two CSVs (300 to score, 1,200 labelled) and the pickle. Every number in §A.
- **SYNTHETIC** — 20 call transcripts generated from 12 template sentences at known intent
  levels, so the extractor can be measured. The accounts they attach to are real; the
  prospect's words are not. Everything in §B and §C is conditional on them.

Reference date 2026-08-01. `python serving/pipeline.py` reproduces §A in ~4 s.

---

> **Names, 2026-09-11 evening:** the arms were renamed for what the rep does — `continue` → **`continue`**, `first-call` → **`first-call`** — and two cohorts were added, **`observe`** (the randomised-out half of untouched trials) and **`skip`** (web-only / MQL-only). Sections that describe tests run before the rename — the metric section's mix table, the prediction test, the 23 converters, the agent's account-by-account table, and everything under *Tests that shaped the design* — keep the names of the time; their numbers stand. §A, the scorecard and §D are current.

## Where an hour changes most — uplift by segment

The business question is not *who converts* but *where does the next hour of calling change the
outcome most*. For each intent segment: conversion with 1–4 logged contacts minus conversion with
none. Estimated on the **older 799 labelled rows**, checked on the **newest 300**, and on all
1,099 (`audit/uplift.py`). **Bias, stated once:** reps chose whom to call, and they call accounts
that already look better — every number here is an **upper bound** on a call's true effect. A
segment at or below zero *despite* that bias is one where calling does not help; that can be said
today.

| segment | uncalled | called 1–4 | **uplift (all)** | 95% CI | train | test | per hour | verdict |
|---|---|---|---|---|---|---|---|---|
| **trial** | 5.0% | 15.2% | **+10.2** | [+2, +18] | +5.0 | +23.5 | +22.3 | **positive on every cut — first call is the top action** |
| **vendor** | 5.7% | 8.2% | **+2.5** | [-2, +7] | +0.7 | +7.3 | +5.4 | positive on every cut |
| **none** | 5.9% | 6.1% | **+0.2** | [-9, +10] | +2.3 | -7.1 | +0.5 | unstable (small n) — neutral |
| **mql** | 0.0% | 0.0% | **+0.0** | [+0, +0] | +0.0 | +0.0 | +0.0 | **≤ 0 on every cut — skip** |
| **web** | 6.9% | 0.0% | **-6.9** | [-13, -0] | -9.1 | +0.0 | -15.7 | **≤ 0 on every cut — skip** |

**Dose, trial segment:** 0 calls 5% → **1 call 16%** → 2: 18% → 3: 15% → 4: 7%. The first call
does the work. **How the +10 gets measured for real:** `BUDGET` splits the untouched trial accounts
at random — half are called (`first-call`), half are not (`observe`) — and `READOUT` reads called
vs observed at day 90, per segment. Detecting 5% → 15% needs ~138 per group; there are 25 untouched
trials in the 300, so ~12 per group per cycle — a quarter at this scale, weeks on the full book.
That is the price of knowing, said to the manager as such.

## The metric to optimise — recall at the budget

**The question the VP actually has:** *of the accounts that were going to buy this quarter, how
many did your list put in front of a rep?* That is **recall@K**: K is the weekly call budget
(hours ÷ minutes per call); recall is the share of the window's buyers that appear in the K.

Three things about it, said once:

- **Not accuracy.** At a 7% positive rate, "nobody converts" scores 93% accuracy. Useless.
- **At a fixed K, recall and precision rank policies identically** — same numerator, both
  denominators fixed. So the scorecard's number does not change form. What changes is the framing:
  *of the 23 buyers, we found 12* is the sentence a manager can act on; *20% of our calls convert* is not.
- **Reported as a curve** — recall@30, @60, @90 — because the budget is a lever, alongside **hours per
  buyer found** (K × 12 min ÷ buyers found) and the **reachable ceiling** (the share of buyers *any*
  data rule can reach at any K: 91% here, at K = 203).

**What it says to do, on the held-out 300 (23 buyers):**

| list of 60 | buyers found | recall@60 | hours per buyer |
|---|---|---|---|
| continue 40 · first-call 20 — the old default | 9 | 39% | 1.3 h |
| **continue 50 · first-call 10 — the new default** | **12** | **52%** | **1.0 h** |
| continue 60 · first-call 0 | 12 | 52% | 1.0 h |
| continue 40 · ask 20 | 11 | 48% | 1.1 h |
| model, out-of-fold | 8 | 35% | 1.5 h |

Moving ten explore slots to exploit found three more buyers; the last ten cost nothing either way,
because continue's slots 51–60 held no buyer in this window. So continue 50 · first-call 10 · control 30.

**Why explore stays at ten and not zero — the trap in optimising recall on history.** Every buyer
history knows about converted *under the historical policy*: reps called who they called. Of the
23, twenty had been contacted; three had not, and those three converted with **no call at all**.
A recall-optimised policy on history will therefore always say *do not call the untouched* — not
because calling them is worthless, but because **history contains no calls to them and so cannot
score the act**. The same mechanism makes the model *worse than random* on untouched accounts (AUC
0.45): it learned that no contact means no conversion, because that is what the record shows.
Explore's ten are not competing on historical recall; they are the price of a day-90 answer to a
question history cannot ask. Across cuts, that price ranged from **0 points** (the held-out 300) to
**4.5 points** (all 1,099 rows at K = 90, where continue's slots 76–90 held four buyers).

**"Replace explore with a better branch" — there is none to build from these columns.** On the 435
never-contacted accounts in history (23 converted, 5.3%, uncalled):

| ranker of the untouched pool | AUC | top-30 converted |
|---|---|---|
| **web touchpoints — what explore uses** | **0.61** | **10.0%** |
| vendor score | 0.57 | 10.0% |
| employees | 0.53 | 0% |
| MQL count | 0.49 | 3.3% |
| **the model, out-of-fold** | **0.45** | 3.3% |
| trial started | no separation (5.0% vs 5.4%) | |
| random | 0.50 | 5.3% |

Web is the only column that ranks this pool at all, and explore already ranks by it. The better
branch for the buyers the rules miss is not a different explore — it is **deeper continue** (done:
50 slots, three tiers) and, for the eight buyers indistinguishable on every column, **the
conversation**.

## The scorecard — the metric of the whole graph

**Of the list a policy says to call, what share converts.** One number, three baselines, two
evidence levels: historical (today, real outcomes on the 1,099 labelled rows — observational)
and prospective (day 90, arms against control — causal; empty until `READOUT` runs, then fills
on its own). Printed at the top of `manager_brief.md` and `metrics.md` every run.

| | the list it says to call | converts — historical | converts — day 90 | rep-hours it refuses to spend |
|---|---|---|---|---|
| model alone — the dashboard the VP asked for | top 90 by score | **6.7%** [3%, 14%] · finds 8% · *from memory: 31.1%* | not yet | 0 — calls everything it ranks |
| random — no system | 90 at random | **7.3%** [3%, 11%] | not yet | 0 |
| the team today — rep's own picks | the 664 accounts it chose to work | **8.3%** [6%, 11%] | control arm | 0 |
| **THE GRAPH — its worklist** | continue 45 + first-call 15 · ask, skip, observe tracked | **12.2%** [7%, 21%] · finds 14% of the 78 buyers | not yet | **51 h / quarter** (ask 27 + skip 25) |
| the graph — confident picks only | continue alone (trial > vendor > none) | **15.6%** [9%, 24%] · finds 18% | not yet | — |

The graph beats every baseline on the historical column — 1.5× the team, 1.8× the model
honestly scored — and is the only row that declines to spend hours. The intervals overlap:
this is direction on real outcomes, not proof; proof is the second column. **If the graph does
not beat the first three rows on both columns, it is retired.** That sentence is in the file.

## The prediction test — 300 accounts none of the methods saw

`audit/heldout_comparison.py`. The 1,099 labelled rows with a closed window, sorted by date; the
**300 most recent** (2026-01-08 → 2026-05-03, 23 converted, 7.7%) are
held out; the 799 before them are all any method may know. Each method builds its list of K
from the 300 and we count who converted. **No model is fitted** — the model's prediction for a test
row is its out-of-fold score (a clone that never saw the row, from the audit). The pickle scoring the
same rows from memory sits in the first row for contrast.

**Precision** = of the K you said to call, the share that converted. **Recall** = of everyone who
converted in the 300, the share your list found. Accuracy is meaningless at 7.7% positives.

**K = 30**

| who builds the list | converted | precision | 95% CI | recall | contacts sunk |
|---|---|---|---|---|---|
| model — the pickle scoring rows it was trained on (memory) | 10 | 33.3% | [19%, 51%] | 43% | 107 |
| **model — out-of-fold (prediction)** | 3 | **10.0%** | [3%, 26%] | 13% | 116 |
| **continue alone (1–4 contacts, trial first)** | 7 | **23.3%** | [12%, 41%] | 30% | 71 |
| explore alone (0 contacts + signal, by web) | 1 | 3.3% | [1%, 17%] | 4% | 0 |
| **THE GRAPH — exploit 2/3 + explore 1/3, ask excluded** | 5 | **16.7%** | [7%, 34%] | 22% | 57 |
| exploit ∪ model picks (half each) — does the model add anything? | 5 | 16.7% | [7%, 34%] | 22% | 105 |
| ask cohort, if called anyway (5+ contacts) | 4 | 17.4% | [7%, 37%] | 17% | 133 |
| random (mean of 200 draws) | 2.3 | 7.8% | 5–95%: [0%, 17%] | 10% | 50 |
| the team today — every account it chose to work | 20 | 10.9% | [7%, 16%] | 87% | 497 |
| the graph WITH the conversation agent | — | — | needs call transcripts on accounts with a known outcome — none exist; ROLLOUT phase 3 | — | — |

**K = 60** — the graph's actual recommendation (continue 40 + first-call 20)

| who builds the list | converted | precision | 95% CI | recall | contacts sunk |
|---|---|---|---|---|---|
| model — the pickle scoring rows it was trained on (memory) | 15 | 25.0% | [16%, 37%] | 65% | 194 |
| **model — out-of-fold (prediction)** | 8 | **13.3%** | [7%, 24%] | 35% | 193 |
| **continue alone (1–4 contacts, trial first)** | 11 | **18.3%** | [11%, 30%] | 48% | 170 |
| explore alone (0 contacts + signal, by web) | 1 | 1.7% | [0%, 9%] | 4% | 0 |
| **THE GRAPH — exploit 2/3 + explore 1/3, ask excluded** | 9 | **15.0%** | [8%, 26%] | 39% | 99 |
| exploit ∪ model picks (half each) — does the model add anything? | 10 | 16.7% | [9%, 28%] | 43% | 189 |
| ask cohort, if called anyway (5+ contacts) | 4 | 17.4% | [7%, 37%] | 17% | 133 |
| random (mean of 200 draws) | 4.6 | 7.6% | 5–95%: [3%, 13%] | 20% | 99 |
| the team today — every account it chose to work | 20 | 10.9% | [7%, 16%] | 87% | 497 |
| the graph WITH the conversation agent | — | — | needs call transcripts on accounts with a known outcome — none exist; ROLLOUT phase 3 | — | — |

### The 23 converters, one by one — which mechanism reaches each

| account | contacts | trial | vendor record | MQL | web | model rank /300 | reached by |
|---|---|---|---|---|---|---|---|
| `ACC-00560` | 5 | yes | yes | 2 | 0 | #4 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00054` | 5 | — | yes | 2 | 0 | #27 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00984` | 5 | — | yes | 1 | 5 | #37 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00731` | 5 | — | yes | 1 | 6 | #18 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-01259` | 4 | yes | yes | 1 | 0 | #33 | continue tier 'trial', position 4 — in the top 40 |
| `ACC-00807` | 4 | — | yes | 0 | 0 | #68 | continue tier 'vendor record', position 41 — below the cut |
| `ACC-01231` | 4 | — | yes | 0 | 4 | #71 | continue tier 'vendor record', position 43 — below the cut |
| `ACC-00064` | 3 | yes | yes | 0 | 0 | #36 | continue tier 'trial', position 5 — in the top 40 |
| `ACC-00214` | 3 | yes | — | 0 | 3 | #249 | continue tier 'trial', position 24 — in the top 40 |
| `ACC-00372` | 3 | — | yes | 3 | 0 | #231 | continue tier 'vendor record', position 54 — below the cut |
| `ACC-00139` | 3 | — | yes | 0 | 7 | #119 | continue tier 'vendor record', position 49 — below the cut |
| `ACC-01072` | 2 | — | yes | 2 | 8 | #98 | continue tier 'vendor record', position 83 — below the cut |
| `ACC-00848` | 2 | — | yes | 1 | 4 | #228 | continue tier 'vendor record', position 79 — below the cut |
| `ACC-01143` | 2 | yes | yes | 2 | 0 | #59 | continue tier 'trial', position 17 — in the top 40 |
| `ACC-01468` | 2 | yes | — | 2 | 0 | #99 | continue tier 'trial', position 29 — in the top 40 |
| `ACC-00103` | 2 | yes | yes | 1 | 3 | #136 | continue tier 'trial', position 12 — in the top 40 |
| `ACC-00975` | 1 | — | yes | 0 | 6 | #167 | continue tier 'vendor record', position 101 — below the cut |
| `ACC-00235` | 1 | yes | yes | 0 | 2 | #41 | continue tier 'trial', position 19 — in the top 40 |
| `ACC-00981` | 1 | — | yes | 2 | 0 | #152 | continue tier 'vendor record', position 103 — below the cut |
| `ACC-01357` | 1 | yes | yes | 5 | 2 | #87 | continue tier 'trial', position 22 — in the top 40 |
| `ACC-00607` | 0 | — | — | 0 | 0 | #294 | 0 contacts, no signal — nothing reaches it |
| `ACC-01313` | 0 | — | yes | 0 | 9 | #76 | explore, position 5 |
| `ACC-01499` | 0 | — | yes | 1 | 0 | #288 | explore, position 81 |

| mechanism | converters | of 23 | what it means |
|---|---|---|---|
| **continue, top 40** | **8** | 35% | **every one has a trial.** In the 1–4-contact pool, trial converts 23.5%, no trial 6.3% — the trial does continue's work |
| **continue pool, below the cut** | **8** | 35% | **none has a trial.** On contacts, MQL, web and the model's own score they are indistinguishable from the 118 non-converters beside them (Mann-Whitney p = 0.59 / 0.95 / 0.79 / 0.56; the model ranks them at median 51 of 126 — random). One column separates them: **all 8 have a vendor record, vs 56%** |
| ask (5+ contacts) | 4 | 17% | the model ranks them #4, #18, #27, #37 — it loves them, for the contacts. Recoverable if the rep answers *live deal* |
| first-call, top 20 | 1 | 4% | `ACC-01313`, 9 web touches, never called — explore finds it at position 5 |
| first-call, deep | 1 | 4% | position 81 of 82 — no ranking reaches it |
| no signal at all | 1 | 4% | 0 contacts, 0 MQL, 0 web, no vendor — nothing in the data sees it |

**What this says about where the value is.** Data rules reach about half the converters: the trial
tier (8) plus what `ask` recovers when the rep answers (up to 4). The **8 below the cut are the
conversation's territory** — nothing in the columns tells them apart, and that is precisely the
case the agent exists for; untestable today, declared. Two are unreachable by any mechanism.

**The third tier, and how it was found — said plainly because it matters.** The vendor-record
signal on those 8 was spotted *in the test set*. Validating it on cuts that contain the test set
would be circular, so the check was the early 60% of history, which does not touch the 300: in the
1–4-contact, no-trial pool, **vendor record 8.3% vs none 2.7%** (Fisher p = 0.07 — borderline
alone). What makes it more than borderline is the prior: the audit had found, before any of this,
that vendor *coverage* predicts conversion (8.22% vs 3.94%, p = 0.003) while the vendor *score* does
not. Three sources, one direction. So exploit now fills **trial → vendor record → contact count**.
On the held-out 300 that lifts continue alone from 23.3% to **26.7%** at K=30 and 18.3% to
**20.0%** at K=60 (recall 52%); the graph to **20.0%** / 15.0%. The model, out-of-fold:
10.0% / 13.3%.

**The near-dead bucket.** Accounts with 1–4 contacts, no trial and no vendor record convert at
**1.6%** across all 1,099 rows (3 of 190) — below the never-touched rate. In the 300 to score there
are 46 of them, holding 106 contacts (21 rep-hours). The third tier puts them last; with 40 exploit
slots they are not called.

### What it shows, and what it does not

**Confirmed — the model adds nothing beyond a hand-written rule.** Out-of-fold, the model's list
converts at 10–13%, barely above random (7.6%) and no better than the team's own picks (10.9%).
Continue — 1–4 contacts, trial first, then vendor record — converts at **27% / 20%**, roughly 2× the
model, with fewer contacts sunk. Replacing half of continue's picks with the model's best picks **removes conversions**
(7 → 5 at K=30). The model's memory number (33%) is the dashboard's lie, in the same table.

**Refuted, as a historical claim — "explore should raise the metric".** Explore's picks converted
1 of 30 and 1 of 60. The graph with explore (15.0%, recall 39%) sits *below* continue alone
(20.0%, recall 52%) on both metrics. On this cut exploring a third of the list cost three points of
precision and nine of recall; on an earlier cut it cost zero. The honest range is 0–3 points.

**But history cannot value explore, by construction.** In the test 300, accounts nobody called
convert at **2.6%** (3 of 117); first-call's pool — untouched *with* a signal — at 2.4% (2 of 82).
Accounts with 1–4 contacts: 10.0%. With 5+: 17.4%. Conversion follows contact in this data. That
correlation is either *calls cause conversions* or *reps call the accounts that were going to
convert* — and a held-out test on history cannot tell them apart, because **history contains no
calls to the untouched accounts**. Explore's 1.7% is the answer to *what happens if nobody calls
them*. The explore arm exists to answer the other question. Reading its historical row as its value
is the audit's confounding error run in reverse — and the same logic applies to the agent, whose
row here says *needs transcripts on accounts with outcomes*.

**So the scorecard says two things.** What history can judge: **exploit ≫ model ≈ team ≈ random**,
and the model adds nothing on top of exploit. What only the arms can judge: whether calling an
untouched account with a signal, or an account whose prospect said *ready*, converts better than
leaving it alone. The graph's historical number (15.0%) still beats every baseline; its *confident*
number (continue alone, 18.3%) beats them by more; and the gap between those two is the price of
finding out what history cannot say.

## A · On the real data, node by node — 15 nodes, 14 run today

| node | what it yields on the 300 | verified number |
|---|---|---|
| **INGEST** | the inputs | 300 accounts · 1,200 labelled rows · 78 conversions (6.50%) |
| **VALIDATE** | what the gate catches | **102 of 300** scored on a snapshot >180 days old (218 over 90) · **101 of 1,200** training labels set before their window closed, and those rows carry 33% more MQLs (p_BH = 0.027) |
| **SCORE** | the model's arithmetic | Σp = **19.66** expected conversions (6.55%) vs a field rate of 1–3% · #30 scores 0.10684, #31 0.10629 — the cut is a coin |
| **CLEAN** | the purity agent | row flags (no vendor **116** · stale **102** · never touched **130** · over-invested **29**) + a **variable scorecard on the 799 older rows**: every column alone AUC 0.50–0.56; RANK may use `sales_contacts`, `trial_started`, `intent_score` *presence* — the vendor's score value, MQL, web alone, `account_type`, `industry`, size and `trial_active_users` are reported and given no weight |
| **RANK** | where the next hour changes most | every account → intent segment × contact band → action. On the 300: **first-call 88** (trial 25, vendor 63) · **continue 105** · **ask 23** · neutral 10 · **skip 74** (web/MQL-only, 124 contacts sunk) |
| **PROVE** | the evidence, every run | the uplift table (train/test/all, verdict) · held-out recall · and the model as the brief's footnote: memory 31% vs out-of-fold 6.7% |
| **RECONCILE** | where the two voices disagree | **24** model-high-nobody-called · **22** heavy-effort-no-result · **9** rep-insists-model-low — the rep is asked. The prospect's voice is proposed, not wired |
| **VALUE** (economics) | the price of an hour | **24.6 contacts per conversion** (4.9 rep-hours) · **52 accounts hold 260 of 481 contacts (54%)** · 789 contacts of historical effort on accounts that never converted (41%) · the yield curve says *call more* as a rate and *never call twice* as a cost — **not optimisable from this data** |
| **BUDGET** | the cut | arms **continue 45 · first-call 15 · control 30** · cohorts **ask 23 · observe 13 · skip 74** · first-call = 12 untouched trials called + 13 observed (the unbiased test) + 3 untouched vendor · continue: trial 18 → vendor 27 → none 0 · **0 over-invested** |
| **HYGIENE** | CRM defects with a rule each | **86 of 101** scoring "Suspects" have an MQL, trial or contact (341/402 in training; conversion identical across types, χ² p = 0.84) · 19 trials with 0 active users · 103 zero-web accounts indistinguishable from unmeasured |
| **VERDICT** | is this run trustworthy | PSI max **0.058** (stable) · Σp overstates the field 2–6× · top-30 overlap with previous run 30/30 (same data) |
| **PRESCRIBE** | findings → owners | **12 findings**: 1 blocking · 8 high · 3 medium — owners pipeline 3 · process 3 · crm 2 · model 2 · vendor 2 |
| **HITL** | the signature | pending — nothing written |
| **EMIT** | the outputs | **`ranked.csv`** (all 300: position · action · segment · evidence · arm) · brief (scorecard, the model's 30 → what happens to each, uplift) · worklist (90 to call + 23 to ask, no score) · disagreements · actions · metrics · cases |
| **READOUT** | day 90 | bypassed — no outcomes yet; when it runs: **uplift per segment, unbiased** (first-call vs observe), the bet, the loop |

### The head-to-head — the model's 30 vs. this system, on real data

The model's answer to *who do I call* is its top 30. Here is what happens to each of them:

| the model's top 30 | count | why — readable on the row |
|---|---|---|
| **ask, don't call** | **11** | 5+ contacts, no result, no conversation on file — the rep gets one question |
| pool / control | 6 | not drawn this cycle |
| **continue / first-call — called as-is** | **9** | 4 of them flagged stale (>180 d) — working hypothesis: still actionable |
| first-call | 4 | never contacted, carries a signal — called, as a *hypothesis* |

**Of the 30 the model says to call, 9 are called as-is.** The 11 it ranks high after 5+
fruitless contacts are exactly where the audit's circularity lives. Staleness is **flagged,
not blocked**: the rep sees *snapshot 290 days* on the row, works the account, and `READOUT`
compares stale vs fresh conversion inside each arm. Under the previous exploit rule
(`ORDER BY contacts DESC`) **18 of our own 30 carried our own over-invested flag**. Fixed.

**What each policy sends to the phone, on the 300 (no outcomes):**

| list | n | stale (flagged) | exhausted (5+) | never touched | contacts already sunk | hours in exhausted accounts |
|---|---|---|---|---|---|---|
| MODEL top-60 | 60 | 24 | **20** | 16 | 168 | **23 h** |
| GRAPH continue + first-call | 60 | 18 | **0** | 30 | 78 | **0 h** |

### On real outcomes — each policy's list of 90, and how many converted

1099 labelled training rows with a closed 90-day window · base 7.1%.
**Observational**: every policy is judged on accounts someone already chose to work this way; the
comparison is fair, the levels are not causal. Printed by `BASELINES` on every run.

| who builds the list of 90 | converted | rate | 95% CI | contacts already sunk |
|---|---|---|---|---|
| model — in-sample (what a dashboard shows) | 28 | **31.1%** | [22%, 41%] | 295 |
| **model — out-of-fold (what it actually knows)** | 6 | **6.7%** | [3%, 14%] | 304 |
| graph continue (1-4 contacts, trial first) | 14 | **15.6%** | [9%, 24%] | 234 |
| graph first-call (0 contacts + signal, by web) | 8 | **8.9%** | [5%, 17%] | 0 |
| **graph worklist (continue 45 + first-call 45)** | 11 | **12.2%** | [7%, 21%] | 150 |
| old exploit (ORDER BY contacts, all) | 12 | **13.3%** | [8%, 22%] | 486 |
| ask cohort, if called anyway (5+ contacts) | 12 | **14.6%** | [9%, 24%] | 454 |
| random (mean of 200 draws) | 6.6 | **7.3%** | 5–95%: [3%, 11%] | 146 |

**The model from memory: 31.1%. The model on rows it never saw: 6.7%. Random: 7.3%.** The
first number is what a dashboard would show. The gap between the first two is the brief's
folklore — *promising in testing, lost credibility in the field* — measured.

## Tests that shaped the design

### Can the rate go higher? The rules tried, all of them

Seven candidate rules for the exploit arm, designed before looking at outcomes, evaluated on the
full labelled set and on a **temporal holdout** (the most recent 40% of snapshots, not used to pick):

| rule | full set, K=90 | temporal holdout, K=30 | verdict |
|---|---|---|---|
| current: 1–4 contacts, most first | 11.1% | 13.3% | reference |
| A · + MQL > 0 | 6.7% | 10.0% | worse — MQL count is not a useful filter here |
| **B′ · + trial started (any usage)** | **15.6%** | **16.7%** | **better on every cut, ~35% fewer contacts sunk** |
| C · + vendor record | 11.1% | 13.3% | no change |
| D · explore ranked by MQL instead of web | 5.6% | 3.3% | worse — web ranking stands |
| E · explore + live trial only | 3.7% | 5.6% | worse |
| F · simple additive score | 8.9% | 13.3% | no better |
| G · + MQL > 0 + vendor | 10.0% | 10.0% | no better |

### Why not continue alone? The cost of exploring, measured

Continue alone scores highest today (15.6%). Three reasons it is not the design, and a number
for each:

| exploit / explore mix | full set | temporal holdout | never-touched accounts it calls |
|---|---|---|---|
| **90 / 0 — continue alone** | 15.6% | 14.4% | **0** |
| 72 / 18 — explore at the 20% floor | 12.2% | 14.4% | 18 |
| **60 / 30 — the new default** | 13.3% | **14.4%** | 30 |
| 45 / 45 — the old default | 12.2% | 11.1% | 45 |

1. **On the holdout, exploring a third of the list costs nothing.** 14.4% at 90/0, 72/18 and
   60/30 alike. Only 50/50 paid (11.1%). So the default moved to 2:1 — continue 40 · first-call 20 ·
   control 30 — and the loop's 20% floor keeps explore from ever reaching zero.
2. **Continue alone starves.** Its universe is *accounts someone already called* — 141 of the 300.
   At 40 a cycle it drains in three or four cycles, and nothing refills it, because refilling it
   is what explore does. Continue alone is the model's mistake in a new coat: it can only look
   where someone already looked.
3. **The 130 never-touched stay untouched forever** — including 17 accounts with a live trial
   and zero calls. Explore reaches 3 of those 17 today; continue alone reaches none, by definition.
   (On history, 0-contact accounts with a live trial convert at only 3.7% — so first-call's
   web-ranking stands and those 17 are a hypothesis for a later variant, not a fix today.)

Tie-breaking alone moves the 60/30 number between 12.2% and 13.3% on the full set (11 vs 12
conversions). That is the resolution we are working at; the holdout is the tiebreaker.

B′ was motivated before the grid by HYGIENE's finding that 0-user trials convert as well as
live ones (15.8% vs 13.1% at 1–4 contacts). It also held on the early 60% alone (11.7% vs
10.0%). With 14 vs 10 conversions the intervals overlap — it is the consistent direction across
three cuts, not any one number, that earns it the first tier of exploit. Nothing else moved.

### Named cases on real data — no transcript involved

**The model's top picks are the team's sunk costs.**

| rank | account | score | contacts | what the row says |
|---|---|---|---|---|
| **#1** | `ACC-01491` | 20.9% | **5** | Retail, 188 emp · snapshot **290 days** old · flags *stale, over-invested* · 5 contacts, 1 MQL, a trial — and no conversion |
| **#3** | `ACC-01064` | 18.7% | **5** | Retail, 57 emp · *over-invested* · same shape |
| #39 | `ACC-01415` | 9.8% | **9** | the most-contacted account in the batch · no vendor record · 437 days stale |

The top-10 averages **3.6 contacts against 1.6** for the batch; 6 of 10 carry ≥4. The model
ranks these first *because* of the contacts — its strongest feature — and the contacts are
there because someone already decided these accounts were worth it. That is the circularity
the audit proved statistically (§3.5), here as the #1 row of the ranking.

**The model's high scores nobody acted on.**

| rank | account | score | contacts | what the row says |
|---|---|---|---|---|
| #9 | `ACC-00657` | 14.4% | **0** | Financial Services, 562 emp · 4 MQLs, 8 web touches · **never called** · 305 days stale |
| #12 | `ACC-00966` | 13.4% | **0** | Retail · 4 MQLs, 8 web touches · never called · 207 days stale |

24 such accounts. Every one is also stale: the information that makes them look good is
older than the window it claims to measure.

**Where the rep disagrees with the model.**

| rank | account | score | contacts | what the row says |
|---|---|---|---|---|
| #286 | `ACC-01282` | 4.0% | **3** | Professional Services, 121 emp · 3 MQLs · **no vendor record** · the rep keeps calling a bottom-5% account |
| #296 | `ACC-00033` | 3.9% | **3** | Professional Services, 437 emp · no vendor record · same |

9 such accounts. Both examples have no vendor record — and the audit showed the model
learned the *gap* in vendor coverage, not intent. The rep may know something the columns do
not. Today nobody asks.

---

## Proposal — the conversation layer (designed, measured on synthetic transcripts, **not in the pipeline** since 2026-09-11; see `proposal/conversation_layer/`)

### B · The agent, step by step — on 20 synthetic transcripts

`conversation_intent` runs six ordered steps (the prompt fixes the order). Measured against
the known intent level each transcript was generated from, on `qwen3:14b`, locally.

| step | field | what it yields | accuracy |
|---|---|---|---|
| 1 | `ready_because` | budget already allocated, or a definite buy/go-live date — or `neither` | 8 `budget_approved` · 12 `neither` |
| 2 | **`ready_to_act`** | the boolean the pipeline routes on; must agree with step 1 (invariant) | **1.00** · 0 missed · 0 false alarms |
| 3 | `evidence_quote` | the prospect's exact sentence | **20/20 found verbatim in the transcript** |
| 4 | `next_step_agreed` | a specific follow-up, or not | **1.00** · 10 of 20 had one |
| 5 | `objections` | obstacles named, kept separate from readiness | 1.6 per call |
| 6 | `intent_level` A–F | context, not routing | **0.80 exact · 1.00 within one level** · hot/cold 0.95 |
| — | `confidence` | self-report | mean 0.975 · **0 of 20** in the 0.4–0.8 human band |

**What the four level errors are.** All four leave `ready_to_act` correct, so none changes a
route. Three are **E read as D**: *"I'm not the right person, you'd want whoever owns ops"*
and *"we decided to build internally two years ago"* graded as passive interest rather than
wrong-person/wrong-time. One is D read as C. The agent is soft on the E boundary; today that
has no operational effect (E and D are both released under the same rule), and it is the
first thing to fix when real transcripts arrive.

**What was never tested.** Every ready transcript in the ground truth states a *budget*. There
is no timeline-only case, so step 1's second trigger has **no measurement**. Two accounts
state both (*"live before the fiscal year closes in November"*) and the agent returned
`budget_approved`, not `both` — a harmless under-read, but the enum value has never fired.

**What the 1.00 actually rests on.** 20 transcripts, **12 distinct core sentences** — pairs
share their key line. The measurement is on 12 scenarios, not 20 conversations. It is a
contract check, not a field trial; the field trial is the bets in `metrics.md`.

### One transcript, all six steps — `ACC-01282`

138 words. Generated as level A. The prospect (VP Operations) says: *"We signed off on the
budget last week and we need this live before the fiscal year closes in November. I'm ready
to talk contracts."*

| step | output |
|---|---|
| 1 | `ready_because = budget_approved` |
| 2 | `ready_to_act = True` — invariant holds |
| 3 | `"We signed off on the budget last week and we need this live before the fiscal year closes in November."` — verbatim |
| 4 | `next_step_agreed = True` → *"Schedule a working session with the ops lead in the next couple of weeks"* |
| 5 | `["We've been told yes before and it didn't hold up"]` — a real line from the transcript, correctly kept out of readiness |
| 6 | `intent_level = A` — matches |
| — | `confidence = 1.00` |

This is the account the model ranks **#286 of 300**.

---

### C · What the agent would add over the rules — account by account (synthetic)

The same 20 accounts, run twice: **rules only** (no LLM), then **rules + the extractor**.
Everything in §A — the 12 stale, the 7 asked, the 3 survivors — is a rule on a column and
needs no agent. This table is what the agent changes on top of that.

| account | model rank | contacts | rules only | with the agent | the prospect said |
|---|---|---|---|---|---|
| `ACC-00414` | #78 | 4 | **exploit — called** | **holdout** | *"We're not interested."* |
| `ACC-00806` | #111 | 4 | **exploit — called** | **holdout** | *"We just renewed with our current vendor for three years."* |
| `ACC-00915` | #45 | 6 | ask | **holdout** | *"You can, but I wouldn't expect much movement."* |
| `ACC-00935` | #35 | 5 | pool (stale) | **holdout** | *"Nothing's driving this right now."* |
| `ACC-00270` | #60 | 5 | ask | **exploit** | *"Building the business case"* — working session booked |
| `ACC-00730` | #40 | 1 | pool | **exploit** | *"Let's find time in the next couple of weeks."* |
| `ACC-01128` | #52 | 1 | pool | **exploit** | *"We signed off on the budget last week."* |
| `ACC-00109` | #157 | 1 | pool (stale, 618 d) | **exploit** | *"Board approved the spend."* |
| `ACC-00275` | #171 | 1 | pool | **exploit** | *"Budget approved for this fiscal year."* |
| `ACC-00561` | #208 | 2 | pool (stale, 437 d) | **exploit** | *"There's money allocated."* |
| `ACC-01145` | #215 | 3 | pool (stale, 304 d) | **exploit** | *"There's money allocated."* |
| `ACC-00602` | #248 | 2 | pool | **exploit** | *"Board approved the spend. Production by Q4."* |
| `ACC-01282` | #286 | 3 | pool | **exploit** | *"Signed off on the budget last week… live before November."* |

**13 of 20 move on information the rules did not have** (2 more move because the control
draw reshuffles). Grouped:

| what the agent did | accounts | what it means in hours |
|---|---|---|
| **stopped 2 calls the rules would have made** | `00414`, `00806` — 4 contacts each, prospect said no | 8 contacts the rules were about to spend on accounts that declined |
| **answered 2 `ask` questions** | `00915` → rest · `00270` → call | the over-invested cohort resolves itself when the prospect has spoken |
| **surfaced 8 accounts nobody would have called** | 7 said READY, 1 booked a meeting — ranks #40 to #286 | the model had four of them below #200 |
| **overrode the stale rule 3 times** | `00109`, `00561`, `01145` — CRM rows 304–618 days old, prospect said READY | a conversation last week is fresher than any column |

One bug this table exposed and fixed: those three READY accounts were being blocked by the
staleness rule. A stale CRM snapshot is a reason to distrust the *columns*, not the
*prospect*. `engaged` now comes from all rows.

**The plain statement.** On the real 300 without transcripts, the LLM agents add **no
information** — every verdict in §A is a rule. With transcripts, the extractor changes where
13 of 20 accounts go, and every change is a sentence the prospect said, quoted verbatim
(20/20 grounded, §B). Whether those changes were *right* is the bet in `metrics.md`, settled
2026-10-30.

### C′ · What the synthetic layer adds in aggregate — conditional on §B

With the 20 transcripts wired in (`--demo`), the same real accounts move:

| result | count | depends on |
|---|---|---|
| rescued (model ≤ Q1, prospect READY) → `continue` | **2** (`ACC-01282`, `ACC-00602`) | the synthetic quote |
| released (prospect NO, ≥4 contacts, no next step) → `holdout` | **4** · 19 contacts · **3.8 rep-hours** | the synthetic quote |
| extrapolated to the 170 accounts with a call | ≈32 rep-hours / cycle | that the other 150 behave like these 20 |
| score inversion: mean score of those who said NO **6.9%** vs YES **5.5%** | on 20 | the synthetic quotes — but the *mechanism* is §A's #1 row |
| bets filed → settled at day 90 | 3 → `UNDERPOWERED 0/4`, `UNDERPOWERED 0/2`, `OPEN` | n |

A fifth account (`ACC-00270`, *"building the business case"*, working session booked) was
released by an earlier rule and is **not** any more: an agreed next step keeps an account in
play. The hours number went down when the rule got better.

---

## D · Verified, or not

| claim | status |
|---|---|
| 24.6 contacts per conversion; 54% of effort in 52 accounts | **verified, real** |
| the model's #1 and #3 are 5-contact, no-result accounts | **verified, real** |
| of the model's top 30, 9 are called as-is; 11 asked first | **verified, real** |
| model from memory 31% vs out-of-fold 6.7% vs random 7.3% on labelled rows | **verified, real outcomes** (observational) |
| continue with a trial tier converts 15.6% vs 11.1% | **verified on three cuts** — direction, intervals overlap |
| on 300 held-out accounts: continue 20%–27%, model out-of-fold 10–13%, model adds nothing to continue | **verified, real outcomes, no fit** |
| continue 50 · first-call 10 finds 12 of 23 buyers at K=60, same as continue 60; 40/20 found 9 | **verified, held-out** — the reason for the new default |
| no column ranks the untouched pool better than web (AUC 0.61); the model is below random there (0.45) | **verified, all 1,099** — 'a better first-call' cannot be built from these columns |
| of the 23 converters: 8 reached by the trial tier, 8 below the cut and indistinguishable on every column but vendor coverage, 4 in ask, 3 untouched | **verified** — the map of where each mechanism's value is |
| vendor record as continue's third tier | **supported**: audit prior (p = 0.003) + clean early cut 8.3% vs 2.7% (p = 0.07); spotted in the test set, so the test set does not count as validation |
| first-call raises the historical metric | **refuted on this cut** (1/60) — and history cannot value first-call: untouched accounts convert 2.6% *when untouched*; the arm measures the other case |
| 'Suspect' is mislabelled | **hypothesis, checked**: Suspects carry *more* contacts than Prospects (1.69 vs 1.54), same MQLs, same trials, Mann-Whitney p = 0.20; only 15% truly untouched vs 16% of Prospects. They are worked like Prospects. |
| stale accounts are still actionable | **hypothesis, stated** — flagged not blocked; READOUT tests it |
| 24 high-scored accounts nobody called, all stale | **verified, real** |
| 41% of contacts on accounts the vendor never covered | **verified, real** |
| 86 of 101 "Suspects" show activity | **verified, real** |
| hours-per-conversion is not estimable from this data | **verified, real** (two readings, one table) |
| the extractor quotes verbatim, never invents | **verified** — 20/20 grounding, synthetic text |
| `ready_to_act` 1.00 | **measured** on 12 scenarios of my own ground truth — not a field result |
| 2 rescued, 4 released, 3.8 rep-hours | **conditional** on synthetic quotes |
| the score is inverted against prospects | **conditional** on 20; the mechanism is real |
| any conversion lift | **not measured** — and cannot be before ~2,500/arm |
| trial's first call is the highest-uplift action (+10, upper bound) | **verified on three cuts as rank and sign**; magnitude [+2, +18], unbiased value at day 90 via first-call vs observe |
| web-only and MQL-only: calling never helped | **verified** — ≤ 0 on every cut despite selection bias → `skip` |
| `sales_contacts_90d` precedes the outcome window | **unknown** — everything above assumes it |
