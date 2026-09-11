# Research log

Kept as I go. Timestamps are local (UTC-3). Entries are appended, never rewritten —
where I was wrong later, the correction is a new entry, not an edit of the old one.

Exercise received 2026-09-10 ~21:30 local. 24h hard deadline → 2026-09-11 ~21:30.
Suggested time-box ~4h.

**AI tooling used:** Claude (chat) for the first exploratory pass, then Claude Code
(Opus 5) inside VS Code for everything in this repo. All on my own personal account.
Every session that shaped a decision is logged below with what I asked and what I did
with the answer.

---

## Entry 0 — 2026-09-10 ~21:00 · Exploratory pass, before opening the repo

**Where I started.** The VP's ask ("build us a dashboard so reps stop guessing") is a
solution, not a problem. So the first question isn't technical: *who decides what, and
what would tell us it's working?* I parked that and went to the data, because I can't
frame the decision without knowing what the instrument can and can't say.

**What I did.** A long exploratory session with Claude (chat), working over
`training_data.csv`, `accounts_to_score.csv` and `model.pkl`. I deliberately ran it as a
*debate* rather than a Q&A: I had it argue the case from six conflicting positions (an
auditor, the VP of Sales, an SDR, a data engineer, a governance/trust lens, and an AI
product lens), each one required to attack the others with numbers. The point was to
avoid the failure mode where the model agrees with whatever frame I hand it.

**Output.** A ~270-line working document (kept out of this repo — it's scratch, in
Spanish, and half of it didn't survive verification) with roughly 80 concrete numeric
claims about the model and the data.

**What I got out of it, in one line each:**
- The model *orders* acceptably and *quantifies* badly. Those are two different products.
- Three separate contaminations: right-censored labels, median imputation of the single
  most important feature, and a feature that measures our own team's behaviour.
- The brief's own framing contradicts the data in at least two places.

**On prompts.** I did not save the exact wording from that chat session, and I am not
going to reconstruct quotes I don't have. What I can state honestly about its shape: the
opening prompt handed over the three files and asked for six named stakeholder positions
that had to argue with numbers computed from the data, not with opinions; the follow-ups
that mattered pushed for a calibration table by decile and for how much each uncovered
account's score moved when its missing intent was set to a low and a high value. Every
prompt from the Claude Code sessions that followed — where the actual decisions were made
— is recorded verbatim or near-verbatim in Entries 1–6 below.

**Dead end from this session:** my first instinct was to ask "is the model any good?"
and I got back a generic model-evaluation checklist — AUC, precision/recall, class
imbalance, the usual. Correct and useless. It described what an audit *could* look like
instead of auditing anything. The packet warns about exactly this. I dropped it and
re-asked against the actual files, forcing every claim to carry a number computed from
the data.

---

## Entry 1 — 2026-09-10 ~21:40 · Repo setup, and not trusting my own first pass

**Setup.** Committed the starter scaffold untouched as commit 1, so every later diff is
visibly my own work. `.venv` on Python 3.12 with the pinned versions (scikit-learn 1.5.2
matters — the pickle was written by it).

**Decision: verify before building.** I was about to start writing `audit/` off the back
of Entry 0. I didn't, for one reason: I have to defend those ~80 numbers live, on my own,
in front of a panel. A number I got from a chat session and never recomputed is a number
I can't defend. Being able to *explain and modify the result myself* is stated as part of
what's being evaluated, and I read "explain" as including "I re-derived it."

**What I ran.** A verification pass that splits the claims into eight blocks
(model internals, calibration/lift, censoring, imputation, `sales_contacts`, taxonomy,
freshness/drift, scoring-set serving numbers), recomputes each block from the raw files
with independent code, and then re-computes *from scratch, with a second independent
script* every claim that didn't confirm on the first pass. Plus an adversarial pass whose
only job is to find what the analysis never checked and what a panel would attack.

Everything it reports goes into `audit/` only after I've read the script that produced it.

**Hypothesis going in (recorded now so I can be wrong in public):** the numbers I most
expect to move are (a) the 6.2× lift in the top 30, because it's computed in-sample *with
the censored rows still in*, and (b) the "341 Suspects with activity" figure, which is
larger than the 300-row scoring file it seemed to be describing.

---

## Entry 2 — 2026-09-10 ~22:10 · The verification came back and the case inverted

**Headline: 136 of 153 claims from Entry 0 reproduce exactly. The one that doesn't is the
one the whole narrative rested on.**

### What broke

Entry 0's thesis was *"the model orders acceptably and quantifies badly."* The first half
is false, and I can now show it two ways.

**1. The permutation null.** I fit the same architecture to *randomly permuted labels*, 200
times, and scored it in-sample exactly the way the original evaluation must have:

| | in-sample AUC |
|---|---|
| the shipped model | 0.7590 |
| same architecture, **random labels**, 200 fits | mean 0.7619, median 0.7619, sd 0.020, max 0.824 |

Empirical p = 0.575. **The headline AUC sits below the median of what this architecture
manufactures out of coin flips.** Top-30 lift on shuffled labels averages 10.6 positives;
the real model gets 12 (p = 0.345).

**2. Honest out-of-fold.** 10×5-fold on a clone of the identical architecture:
AUC **0.573 ± 0.024**, Brier **0.0613 — worse than printing 6.5% on every row**, top-30
lift **0.51×** (one positive), top-60 0.77×, top-120 0.90×. All below random.

And the comparison that settles it: `ORDER BY sales_contacts_90d DESC` — zero parameters,
one line of SQL — captures 4 / 10 / 15 positives at K = 30 / 60 / 120 against the model's
out-of-fold 1 / 3 / 7.

### The move that licenses this, because the packet says "don't retrain it"

`clone(model).fit(X, y)` over the 1200 rows **in file order** reproduces the pickle
**bit-for-bit** (max |Δp| = 0.0 across all 1200; shuffling row order moves predictions by
up to 0.075, because `subsample=0.7` is order-dependent).

That single check does two jobs. It proves the model was fit on exactly this file with no
holdout — no longer an inference. And it establishes that **cloning the architecture for
diagnostics is not retraining the shipped model**: the pickle is never modified, never
replaced, and is still the thing being audited. Calibrating an instrument against a
reference is not swapping the instrument. I expect this to be the panel's first objection
and I want the answer in the proposal, not improvised in the room.

### Why this is the exercise and not a technicality

The brief says an earlier effort *"looked promising in testing"* and *"quietly lost
credibility once the scores stopped matching what reps were seeing."* That is this,
mechanically: "promising in testing" is an in-sample number; "stopped matching the field"
is 0.573. The folklore isn't background colour, it's the finding, and it was sitting inside
the pickle the whole time.

Entry 0 found censoring, median imputation and circularity — all three are real, all three
verified — and framed them as the cause. They are not. **Dropping all 101 censored rows
moves out-of-fold AUC from 0.575 to 0.559 — it gets worse.** The 0.759 → 0.573 gap is
overfitting, full stop.

### ⚠️ The override the packet asks for — this is mine

> *"tell us about one place where you corrected or overrode it, somewhere it gave you
> something wrong or generic, and what you changed."*

**Two, and they're different kinds.**

**(a) The frame.** The chat session in Entry 0 handed me a confident, well-evidenced,
internally consistent narrative — "it orders well, it quantifies badly, here are three
contaminations" — and I built my whole plan on it. It never questioned whether 0.759 was
measured on data the model had already seen. Neither did I, for about an hour. What I
changed: I stopped extending the analysis and ran a null-model check instead. The narrative
didn't survive it. Note the failure mode — the output wasn't sloppy, it was *plausible*.
Being coherent is not the same as being measured, and this one was coherent enough that
I nearly shipped a proposal arguing that a coin flip ranks accounts acceptably.

**(b) A verification agent, in the other direction.** In decomposing `intent_score`, one
verification pass reported that *destroying the observed intent values improves the model*
(0.5785 shuffled vs 0.5705 real). I didn't take it — a claim that strong should not rest on
an unpaired comparison. I rewrote it as a paired design, same folds, 25 repeats
(`audit/` script). The values contribute **−0.0011 ± 0.0044, t = −0.25** — indistinguishable
from zero, but **not** an improvement. The agent's substantive point held; its specific
claim was noise it had over-read. Corrected to "the values carry nothing," which is what the
data supports, rather than "removing them helps," which it doesn't.

### The finding that changes what I build

`intent_score` — the model's nominally most important feature (GBM importance 0.271) —
contributes **only through its missingness pattern**. Paired, 25 repeats, identical folds:

| | OOF AUC | Δ | t |
|---|---|---|---|
| real intent (values + NaN pattern) | 0.5686 | | |
| **values shuffled**, NaN pattern intact | 0.5697 | values contribute **−0.0011 ± 0.0044** | **−0.25** |
| values intact, **NaN pattern reshuffled** | 0.5600 | | |
| column removed | 0.5413 | missingness contributes **+0.0284 ± 0.0043** | **+6.56** |

Replacing the whole column with a bare `intent_known` boolean scores 0.5740 — as good or
better than the real thing. In the 718 rows where intent *is* observed, conversion by
quintile is 8.3 / 7.0 / 9.7 / 7.0 / 9.1 %, Spearman p = 0.424. Flat. But `intent_known`:
8.22% vs 3.94%, Fisher p = 0.0028.

Mechanism: only 2 real rows carry intent = 25.3, and 482 imputed rows land exactly there.
The model places 31 splits on intent, **5 of them inside (24.0, 26.6]** — the bracket that
isolates the imputation spike. Median imputation accidentally built a missingness indicator,
and that indicator is the only thing the model learned from the column.

**Consequence I have to accept:** this kills the serving idea I liked most. A
value-of-information loop that asks reps to go find intent for the 116 accounts missing it
is measuring the model's sensitivity to an input that carries no information. ACC-00492's
13.4-point swing is 13 points of fitted noise. Entry 0 also recommended *adding a
missingness indicator* as the cheap fix — it's already in there. The correct fix is the
inverse: drop the values, keep the flag.

### The bigger structural finding

The only two variables with real signal are `sales_contacts_90d` (p = 0.0013) and
`intent_known` (p = 0.0028) — and **both measure what Cordilla already did to the account,
not what the account is.** The vendor covers accounts that already left a footprint; reps
called the ones that already smelled right. Remove both: **OOF AUC 0.434, below chance.**

So the conclusion isn't "this model is contaminated by one circular feature." It's that
**these nine columns contain no account-intrinsic signal at all.** Which makes the
recommendation much larger than "freeze `sales_contacts`."

### The one question that decides whether any of it is real

`sales_contacts_90d` is a 90-day count; the label is "converted **within** 90 days."
Nothing in the files says whether the contact window *precedes* the snapshot or *overlaps*
the outcome window. If it overlaps, the only significant feature in the dataset is outright
leakage rather than circularity. The empirical shape fits either reading
(P(contacts ≥ 4 | y=1) = 0.282 vs 0.150). One question to the data owner settles it, and
I'd rather have that question in the proposal than another chart.

### Corrections to Entry 0, for the record

Five claims refuted, the load-bearing ones being:
- "5 contacts → ~6% conversion" is actually **13.56% (8/59)**. 5.56% is the value at **six**
  contacts (n=18) — an off-by-one. This matters: the labels are **not** flat at 5, so
  "the model invented a step the data doesn't show" is wrong. The step is in the data, and
  it survives every observable adjustment (adjusted OR 2.63, p = 0.0049). What remains true
  is only that cause and effect are unidentifiable without an experiment.
- "all 9 rep-insists/model-low accounts have missing intent" → **8 of 9** (ACC-00453 has 29.1).
- "341 Suspects with activity" is a **training-set** figure (341/402); the scoring set has **86/101**.
- "three features carry the model" → two plus a weaker third (`web_touchpoints` costs 0.030 AUC, not 0.057).
- "the censored rows don't differ" → they have **33% more MQLs** (p = 0.004, survives
  Bonferroni). Which strengthens the censoring argument rather than weakening it.

Plus the fragile survivors I'll state as directional, not established: "web 0 beats web 1-3"
is Fisher p = 0.158; "trial 10.8% vs 6.3%" doesn't survive Bonferroni across the section's
6 tests; PSI of age is ~0.9 not 0.893 (binning-dependent, 0.664–1.058 across schemes);
the 180-day "stale" threshold is my own invention and 90 days — the actual feature window —
gives 23 of the top 30, not 12.

**And the one-line version of all of it: there are 78 positives in the entire dataset.**

### What I'm not going to claim

The 0.9 PSI on snapshot age is **not drift**. `account_id` runs 1…1500 with no gaps and no
overlap between the two files, and P(row landed in the scoring file | age) is 44.3% / 34.5%
/ 11.0% / 9.7% across age bands. The scoring batch was deliberately drawn recency-biased.
Calling that "the population has shifted" is a claim the panel can disprove by opening the
CSVs.

**Next: decide what actually ships, given that the model doesn't.**

---

## Entry 3 — 2026-09-10 ~23:30 · Building the audit, and three things I got wrong while building it

**Form: notebook, not scripts.** Two reasons. The audit's argument is cumulative — §2.2
only lands because §0.4 established provenance first — and a notebook makes the order
visible. And it renders on GitHub with outputs and figures intact, so a reviewer sees the
evidence without installing anything. The cost is that a notebook is easier to skim than
to interrogate, so every section ends with an explicit verdict rather than leaving the
reader to infer one.

**Structure.** 0 provenance → 1 what is in the box → 2 reported vs. real performance →
3 every variable one at a time → 4 stability and serving robustness → 5 allocation impact
→ 6 consolidated verdict. 102 cells, 11 figures, runs end to end in about three minutes.

### What section 3 added that I did not have before

Entry 2 had the headline. Going feature by feature produced three things it didn't.

**Nothing survives multiple-testing correction.** Nine features, nine tests, 78 positives.
The strongest is `sales_contacts_90d` at raw p = 0.0075, which lands at p_BH = 0.068.
`trial_started` at 0.024 → 0.108. Everything else is at p > 0.4.

I want to be careful how I say this, because the tempting version is wrong. "Fails a
corrected test" is **not** "no effect" — it is "this dataset is too small to establish
one." A real but modest effect looks exactly like this. So the claim I'll defend is that
`sales_contacts` is the only column with a credible claim to signal, and that even it is
not established by these 1200 rows alone.

**Importance tracks cardinality.** Spearman(GBM importance, number of distinct values in
the column) = **+0.78, p = 0.041**; against univariate AUC it is flat and
non-significant. The clean demonstration is the substitution test: put a **pure uniform
noise column** in `intent_score`'s slot, matched only on range and missingness rate, and
it earns **75%** of the real column's importance across 20 refits. A continuous column
gives 40 depth-2 trees more places to cut, so it accumulates impurity reduction whether
or not it means anything.

This is the finding I'd lead with for a non-technical audience, because it needs no
statistics: *the model's "most important feature" is important because it has a lot of
decimal places.*

**Where the imputation spike shows up in the trees.** The model places 31 splits on
`intent_score`, and **7 of them fall inside (24.0, 26.6]** — thresholds at 24.25, 24.3 and
26.6. Only two real accounts in the file carry intent = 25.3; 482 imputed rows land there.
Those seven splits exist to separate "the vendor had no record" from everyone else. That
is the mechanism behind Entry 2's decomposition, and it is much more convincing than the
AUC deltas on their own.

### Three corrections I made to my own work

**1. A methodology error I caught in my own code.** My first out-of-fold implementation
averaged the prediction vectors from 10 repeated CV runs and then computed one AUC:
**0.582**. That is a 10-model ensemble, and ensembling is not what would ship. Scoring
each repeat separately and averaging the metrics gives **0.573 ± 0.024**. Both numbers
support the same conclusion, but the first is a number a panel could take apart, and I
would rather not hand them one. The notebook prints both and says which is honest.

**2. I stated a direction backwards.** I had written that dropping the 101 censored rows
moves out-of-fold AUC *down*. It moves it **up**, 0.573 → 0.575. The substantive point is
unchanged and if anything cleaner: label repair moves the number by two thousandths,
inside a ±0.024 spread, so censoring is not what is wrong with this model. But "it gets
worse" was wrong and I had written it because it made a tidier story.

**3. Numbers in prose drifting from numbers in output.** Rebuilding and re-executing the
notebook several times left several markdown claims stale — Mantel-Haenszel odds ratios
I'd written as 2.4–2.6 that recompute to 2.18–2.30, a Fisher p of 0.16 that is 0.119, five
intent splits in the imputation bracket that are actually seven. I now re-read every
markdown number against its cell's output after each execution. Tedious, and exactly the
kind of thing that destroys credibility when a panel is reading along.

### Still open, and I'd rather flag it than paper over it

The blocking question from Entry 2 has not moved: **does `sales_contacts_90d` count the 90
days before the snapshot, or the same 90 days in which conversion is measured?** If the
windows overlap, the only significant feature in the dataset is leakage. I cannot resolve
it from the files, and it is the first thing I would ask the data owner.

**Next: an adversarial pass over the notebook before I build anything on top of it.**

---

## Entry 4 — 2026-09-11 ~00:40 · I had the audit attacked, and it found three real holes

Before building anything on top of the notebook I ran an adversarial pass over it: five
reviewers, one lens each — text-vs-number consistency, statistical method, ML validity, a
hostile panel, and what a thorough auditor would have checked and I hadn't. Each was told
to run its own code and that filing nothing was an acceptable answer.

It ran out of budget partway through, so the independent second opinions never ran.
**I verified every claim myself before changing anything** — which turned out to matter,
because the findings ranged from "correct and important" to "correct but stated too
strongly."

### What it found that was real, in order of how much it hurt

**1. I never validated forward in time, on a file that spans two years of snapshots.**
This is the one that should have been obvious. Random K-fold lets each fold learn from
rows dated *after* the rows it scores; deployment never does that. Refitting quarter by
quarter — train on everything before a cut-off, score the next quarter:

| scored quarter | n | positives | AUC |
|---|---|---|---|
| 2025Q3 | 226 | 18 | 0.485 |
| 2025Q4 | 232 | 16 | **0.398** |
| 2026Q1 | 264 | 20 | 0.565 |
| 2026Q2 | 157 | 5 | 0.520 |
| **pooled** | **879** | **59** | **0.474** |

**Below chance.** And `ORDER BY sales_contacts_90d DESC` on those same rows scores
**0.608** — 13 points of AUC ahead, and the only one of the two above chance at all.

This is now the strongest result in the audit, and it is a better explanation of the
brief's folklore than anything I had: a model that looks fine under a shuffled split and
inverts under a temporal one is precisely a model that looks good in testing and stops
matching the field two quarters after launch.

**2. "The ceiling is not in the algorithm" was false, and falsifiable in a minute.**
I had written that retraining would just produce another model with the same ceiling. A
panelist with a laptop breaks that: a two-parameter logistic on
`[sales_contacts >= 4, intent_known]` — exactly the recoding §3.4 argues for — scores
**0.595 against the shipped GBM's 0.568** on identical folds, paired t = +4.70, with a
third of the split-to-split variance.

A better model *does* help. It helps by discarding seven of the nine columns, and what
survives still isn't a property of the account. That version is both true and stronger
than what I had, but I only got there because someone tried to break the sentence.

**3. My allocation section was close to vacuous.** I reported that the top 30 fails the
4/5ths ratio on industry, size and `account_type`. A *random* list of 30 out of 300 fails
it too — 100% of the time on industry, 89% on `account_type`. Quoting it unqualified is a
one-line kill: *"I'll shuffle the list and it fails your test."* Null-calibrated against
2000 random lists: company size is at the 2nd percentile and intent coverage at the 2nd —
real. Industry is at the 19th — weaker than I implied. `account_type` is at the 58th —
**not a finding, and I withdrew it.**

### And one bug in my own experiment

Variant C of the intent decomposition (values kept, missingness pattern reassigned) filled
the 482 true gaps with the constant 25.3 *before* reshuffling, so 286 originally-missing
rows stayed visible sitting on the imputation spike and the trees could still read the
original pattern off it. That is why C sat at 0.560, suspiciously above D. Filling from
the observed distribution instead drops C to **0.546**, and the C−D contrast to
+0.005 ± 0.004 (t = 1.41) — non-significant, which is what the section claims. The
conclusion was right; one of the four arms supporting it was leaking.

### Stale numbers, again

Five more markdown claims that disagreed with the output printed directly above them:
`trial_started` 10.8%/6.3% (actually **9.9% / 5.7%**, n = 223 not 204), trial-with-zero-users
12% at n = 66 (**11.0%, n = 73**), MQL χ² 0.37 (**0.45**) and its 5+ cell at 12% (**10.7%**),
industry spread 5.8–8.8% (**5.5–7.6%**), Spearman +0.79/+0.78 where the chart says **+0.77**.

Every one of them came from the Entry 0 chat document rather than from my own cells. That
is the whole failure mode of this exercise in miniature: I verified the *big* claims from
that session and let the small ones through by habit. In a notebook whose entire thesis is
"the number you were shown is not the number," a stale number in the prose is not a typo,
it is the argument failing on itself.

### What I did not accept

"Systematically lower engagement on other channels" for uncovered accounts — I had written
it and it is not supported: every channel comparison returns p ≥ 0.25, and on web
touchpoints and MQLs the uncovered accounts are marginally *higher*. The honest version is
narrower and more interesting: coverage predicts the outcome (p = 0.0028) through a
mechanism **nothing in these nine columns can explain.** Rewrote it that way, and softened
the "already left a visible footprint" story in §3.12 that depended on it.

### Where the audit now stands

113 cells, 11 figures, runs end to end in about four minutes. The verdict did not move —
don't ship the scores — but three of the reasons are different and better than they were
yesterday, and two claims I would have defended in the room turned out to be indefensible.

**Still open, and still the first thing I would ask:** does `sales_contacts_90d` count the
90 days *before* the snapshot, or the same 90 days in which conversion is measured?

**Next: the serving step, and the proposal.**

---

## Entry 5 — 2026-09-11 ~08:20 · Re-reading the rules before building anything else

Stopped to re-read the packet against what the notebook actually does, because one rule
appears four times and I wanted to be sure I was on the right side of it.

> *"Don't retrain it."* · *"Retrain, tune, or improve the model — you don't need to do
> this. Auditing it is the ask, not rebuilding it."* · *"Your job is not to build a model."*

**What the notebook does.** `model.pkl` in the repo is byte-identical to the one in the
zip (SHA-256 `fc2cd6aa…` on both); the only commit that touches `model/` or `data/` is the
scaffold. So the shipped model was never retrained, tuned, replaced or overwritten.

What the notebook *does* do is call `.fit()` on fourteen **new** objects, none of them the
pickle. They fall into three tiers, and they are not equally defensible:

| tier | what | verdict |
|---|---|---|
| A · diagnostics | clones fit on **permuted labels** (the null), on a **noise column** (the cardinality test), or to **prove provenance** (does a clone reproduce the pickle?) | Not retraining under any reading. The clone is thrown away; the pickle is the object under audit. |
| B · generalisation | clones fit inside CV folds, forward-in-time by quarter, on bootstrap resamples | The only way to estimate held-out performance for a model shipped without a holdout. Grey, defensible, and I argued it explicitly in §0.4. |
| C · a different model | a 2-variable `LogisticRegression` as a "contender" (§2.6c) | **This is building a model**, whatever the motive. A strict panelist can say so in one sentence. |

**Decision: remove C.** Two reasons. The rule is unusually explicit and I don't need to
spend credibility defending a cell that does not change the verdict. And the result it
produced — that a better-specified model on the two surviving columns beats the GBM — is
perfectly good **as a stated hypothesis**, which is what it now is in §6. If the panel
asks "so would a simpler model do better?", the answer is *"probably, and it's exactly what
you asked me not to do — but I can tell you which two columns I'd build it on, and why
only those."* That is a better position than defending a cell.

The two-sentence answer for tiers A and B, written down so I don't improvise it:

> *The pickle in the repo is byte-for-byte the one you sent — here is the hash — and
> `serving/` uses only it. What I did was estimate how **that** model behaves on data it
> has not seen, which requires fitting copies of its architecture inside each fold and
> discarding them. That is not retraining the model; it is the only way to measure it
> honestly when it shipped without a holdout.*

Entry 4 records the logistic result as a finding. I am leaving Entry 4 as written — this
log is kept as I go, not rewritten — and recording the removal here.

---

## Entry 6 — 2026-09-11 ~08:30–09:05 · Objective first, then the shape of what to build

### The objective, before any solution

The VP's ask — *"a dashboard so reps stop guessing"* — is a symptom. What I am actually
optimising, written down so the proposal can be held to it:

> **Primary:** more conversions per rep-hour on non-customer accounts, measured against a
> control group.
> **Secondary — the one the packet actually evaluates:** the organisation can tell, at any
> point, whether the tool is helping or is noise everyone trusts by default, *before* reps
> stop believing it. That is how the last one died.
> **Guardrails:** no concentration of hours on segments with no evidence of higher
> conversion; no feedback loop where never-touched accounts stay invisible; nothing enters
> Salesforce without a flag and a date.

Metric: conversions within 90 days per logged contact, by allocation arm, matched on
segment and size. Rep-hours are not in the data; `sales_contacts_90d` is the proxy and I
say so.

### What the audit leaves to build on

The destructive half of the audit is done. The constructive half, from the same numbers:
`sales_contacts >= 4` doubles conversion and scores 0.608 forward in time — an honest
one-line rule; `intent_known` is a free, vendor-independent flag; **130 of the 300
accounts have never been contacted**, 25 of them with a live trial; 29 accounts absorb 35%
of all contacts; 34% of effort goes to accounts described by data over six months old.
None of those are predictions. They are facts about where the hours went.

And the structural finding reframes the whole problem: **the data measures Cordilla, not
the account.** The only account-intrinsic signal there could be — what the prospect
actually said — is not in any column. It lives in the call.

### What I asked, and what came back

I ran a research pass before committing to a design. The prompts, in order:

- *"agentic lead scoring feedback loop sales rep labels self-improving model"* → mostly
  vendor content. Useful consensus: without outcome feedback a scoring model drifts inside
  ~6 months; rep trust is the adoption bottleneck.
- *"contextual bandit lead prioritization explore exploit"* → the **Stitch Fix** bandits
  write-up, which is the closest real analogue: a "best tactic" chosen by test, scaled to
  everyone, then found to be wrong for sub-segments and stale over time. Their fix was
  **epsilon-greedy 90/10** — 10% randomised — precisely so they'd have unbiased data to
  retrain on. Lesson I took: you cannot skip the randomisation phase to get to a
  contextual model.
- *"LangGraph HITL production case study"* → the interrupt/resume pattern: a node pauses,
  the human decision enters as state, the graph continues. *"Human judgment as a
  state-modifying checkpoint."* Also several 2026 LangGraph sales-pipeline guides.
- *"why lead scoring models fail feedback loop circularity"* → unanimous: they score
  activity not intent; no closed loop; unexplained individual errors kill adoption within
  ~2 months. Fixes: co-define with sales, **transparent score breakdown**, rejection reason
  codes, **sales acceptance rate** as the monthly metric (65–75% healthy).
- *"Dialpad Ai sales features"* → Call Purpose, Custom Moments, Ai Scorecards, sentiment,
  Ai CSAT at 87%. The intent-from-conversation layer is a shipping product, and it is
  theirs.
- *"agentic AI enterprise failure modes 2026"* → Gartner: >40% of agentic projects
  cancelled by 2027 (cost, unclear value, weak controls). Microsoft's taxonomy: memory
  poisoning, flow manipulation, inter-agent trust escalation, HITL bypass. Automation
  bias — advisory agents anchor human judgment.
- *"call recording consent B2B GDPR"* → two-party states (CA/FL/IL), GDPR up to 4% of
  revenue, TCPA $500–1,500 per call. Standard mitigation: disclose on every call, Privacy
  Mode (transcript without stored audio), consent logged in CRM.

**Where I did not take the research at face value:** the evidence that conversation-derived
intent predicts conversion is almost entirely vendor-published (Gong Labs, Dialpad). I
found no independent study comparing conversation features against CRM activity features
with a measured lift. So in the design it is **the central hypothesis the experiment
tests**, not an assumption. And the most-cited academic B2B lead-scoring paper reports
AUC 0.989 under random 70/30 CV with feedback "recently integrated" — the exact error the
audit found in the pickle, so I am not leaning on it either.

### The design that came out

A stateful graph — a typed dict passed node to node, each node one function, one human
approval point before anything writes to Salesforce, the LLM writing only what a human
has to read. Thirteen nodes:

`INGEST → VALIDATE → SCORE → {BASELINES, FLAGS, CONVERSATION INTENT} → RECONCILE →
{ALLOCATE, HYGIENE, VERDICT} → ⏸ HITL → EMIT → (day 90) READOUT`

The three decisions inside it that I would defend as *taste* rather than engineering:

1. **The model is one voice of three in `RECONCILE`, never the decision.** Score, rep
   effort, and conversation intent are compared per account; **where they disagree is the
   new data.** That is the right role for an instrument you have shown to be noise-level.
2. **`ALLOCATE` is three matched arms — exploit / explore / rep's own choice — not a
   ranked list.** It is the Stitch Fix randomisation, and it is what produces the control
   group Cordilla has never had. Not a tier, not routing: a comparison of policies.
3. **`CONVERSATION INTENT` replaces "ask the rep".** The rep already said what they know —
   on the call. An agent extracts intent level, objections, next step from the transcript.
   The manual question survives only as fallback for accounts with no recorded call.

Hygiene lives in two places, deliberately: `VALIDATE` is the gate (nulls, ranges, unseen
categories, label window, staleness — automatic, touches nothing in the CRM) and
`HYGIENE` is the corrector (341/86 mislabeled Suspects, 101 censored labels, the
zero-vs-unmeasured contract, the blocking `sales_contacts` window question — proposals
only, approved by a human). Every one of the fifteen data-construction defects the audit
found has a node.

### The risk I am carrying, named

*"Not a bigger build."* A thirteen-node graph with a conversation-intelligence layer is
a bigger build, and Gartner says 40% of these get cancelled. Two mitigations, both from
the packet itself: the code implements the ten nodes today's data supports and runs in one
command; `CONVERSATION INTENT` is a designed node with a documented plug — the same
standard the packet applies to the LLM call. And the proposal frames the deliverable as
*the first run of the system*, not the system.

**Next: proposal, then `serving/`.**

---

## Entry 7 — 2026-09-11 ~09:20 · The material I would stand behind in the room

This is the entry the packet asks for last: not the presentation, the raw material for it
— the text, the numbers, the hypotheses and the assumptions I would actually use. It
consolidates everything above. If `serving/` changes any of it, a later entry says so.

### The story in three sentences

1. The model you inherited looks good for the same reason the last one did: it was
   measured on the data it memorised. Measured honestly, its ranking is noise — and
   scored forward in time, it is below chance.
2. That is not a modelling failure. None of the nine columns describes the account; the
   only two with any signal describe what Cordilla already did to it. No model on this
   data can do more than rerank the accounts you already worked.
3. So the thing to ship is not a better score. It is a system that produces the three
   things this data has never had — a control group, the rep's knowledge, and the
   prospect's own words — while it runs, with the model as one voice among three and a
   human signature before anything reaches Salesforce.

### The numbers I would put on slides

| slide | number | the sentence under it |
|---|---|---|
| The pickle was fit on everything | max \|Δp\| = **0.0** across 1,200 rows | "A clone fit on all rows in file order reproduces it bit for bit. There was no holdout." |
| The headline is noise | in-sample AUC **0.759** · random-label median **0.762** · p = 0.575 | "Fit this architecture to coin flips and it scores the same." |
| Honest performance | out-of-fold **0.573 ± 0.024** · Brier **worse than a constant** · top-30 lift **0.67×** | "Below random where a call list has to win." |
| Forward in time | **0.474** pooled (879 rows, 59 positives) · one quarter at **0.398** | "In the only regime production sees, it inverts. That is the folklore, mechanically." |
| The one-line rival | `ORDER BY sales_contacts` → **0.608** on the same rows | "A sort beats it by 13 points of AUC and is the only one of the two above chance." |
| Importance is cardinality | Spearman(importance, distinct values) **+0.77**, p = 0.04 · noise column earns **75%** | "The 'most important feature' is important because it has a lot of decimal places." |
| Intent: only the gap | values **−0.001 ± 0.004** (t = −0.25) · missingness **+0.028 ± 0.004** (t = 6.6) | "Median imputation built a missingness flag by accident — 7 of 31 splits sit on the spike — and learned nothing else." |
| The structural finding | remove `sales_contacts` and `intent_known` → **0.434** | "Neither describes the account. Remove both and it scores below chance." |
| The list is the seed | seed alone replaces **9 of 30** · #30 vs #31: 0.10684 vs 0.10629 | "A rep who sees accounts vanish week to week stops believing — and they would be right." |
| Where the hours go | **130** never contacted (25 with a live trial) · **29** accounts absorb **35%** of contacts · **34%** of effort on data >6 months old | "This is not a prediction. It is where the time went." |
| What it promises | Σp = **19.7** conversions in 300 (6.55%) vs a field rate of **1–3%** | "Two to six times what the business actually sees, before any performance question." |
| Data defects, fixable | **101** censored labels · **341/402** training "Suspects" with activity · **86/101** in scoring | "Three Salesforce tickets. None of them needs a model." |

### The hypotheses I am making — stated as hypotheses

- **H1 (central).** Intent extracted from recorded sales calls predicts conversion better
  than any CRM column. *Evidence today: vendor-published only. Tested by the arms.*
- **H2.** Never-contacted accounts with a signal (trial, vendor record, MQL) convert at or
  above the base rate. *Evidence today: none — they have no outcomes. Tested by the
  explore arm.*
- **H3.** The step at ≥4 contacts is at least partly causal. *Evidence: OR 2.2, robust to
  every observable adjustment; direction unidentifiable without randomised assignment.*
- **H4.** A two-variable model on the surviving columns would modestly beat the GBM.
  *Not fitted — the brief rules it out. Stated, not shown.*
- **H5.** The true field rate is nearer the brief's 1–3% than training's 6.5%. *Only a
  control group settles it.*

### The assumptions I am making — and would say out loud

- **A1.** 2026-08-01 is "today" for every age calculation.
- **A2.** `sales_contacts_90d` is the available proxy for rep hours. A contact is not an
  hour, but it is what the data has.
- **A3 — BLOCKING.** The `sales_contacts_90d` window *precedes* the snapshot rather than
  overlapping the 90-day outcome window. Nothing in the files says. If it overlaps, the
  only significant feature is leakage and nothing in the model was ever real. One
  question to the data owner; I would not build on that column before it is answered.
- **A4.** 180 days is my "stale" threshold. The window-consistent figure is 90 (218 of 300
  accounts); I report both and use 180 as the conservative line.
- **A5.** Thirty accounts per arm is operationally feasible and the first readout will be
  noisy. It accumulates.
- **A6.** Call recording with per-call disclosure and transcript-only storage is legally
  feasible in Cordilla's jurisdictions. Two-party-consent states and GDPR make this a
  precondition, not a detail.
- **A7.** The 0.9 PSI on snapshot age is recency-biased sampling by design (ids 1…1500, no
  gaps, P(in scoring file | age) falls from 44% to 10%), not population drift.

### The hardest questions, and what I would answer

**"You were told not to retrain it."**
The pickle in the repo is byte-for-byte the one you sent — here is the hash — and
`serving/` uses only it. What I did was estimate how *that* model behaves on data it has
not seen, which requires fitting copies of its architecture inside each fold and
discarding them. That is not retraining the model; it is the only way to measure it
honestly when it shipped without a holdout. The one place I fit a *different* model, I
removed, and it is in the log as a decision.

**"We paid for this. What do we do Monday?"**
Three lists of thirty, matched on segment and size: one sorted by `sales_contacts`, one
of never-contacted accounts with a signal, one the rep picks. Each account carries one
line of flags. Nothing waits on a new model. In ninety days you have the first number
this company has ever had against a control.

**"Half your findings are 'not significant with 78 positives'. So you can't tell us
anything?"**
Correct — and that *is* the finding. This dataset cannot establish what it is being
asked to establish. The system I am proposing is the one that produces the data that can.
Pretending otherwise is how the last model got shipped.

**"The intent vendor's contract is up. Renew?"**
Not for the scores. Their values contribute −0.001 AUC; the only thing the column ever
gave the model is whether a record existed. Keep a boolean for that, drop the score, and
put the money toward recording the conversation, which is the one account-intrinsic
signal available.

**"A sort by one column beats your model. Why build anything?"**
Because the sort is circular — it ranks the accounts you already called — and the data
cannot say whether calling causes conversion or reps just call the right ones. The arms
are what separate those. The sort is a fine exploit arm; it is not a strategy.

**"How is this different from what the last person said?"**
They shipped a score and never measured it. I am shipping a measurement and never a score.

### What I would not claim, because the data does not support it

- That the model *orders* accounts. The 0.759 is at the median of the noise distribution.
- That censoring or imputation caused the failure. Dropping the 101 censored rows moves
  out-of-fold AUC by +0.002. The gap is overfitting.
- That the 0.9 PSI is drift. It is sampling, and a panelist can prove it from the ids.
- That uncovered accounts show lower engagement on other channels. Every comparison
  returns p ≥ 0.25; two run the other way. Coverage predicts the outcome through a
  mechanism nothing in the file explains.
- That the model "invented" the step at five contacts. The step is in the labels; the
  5.6% I once quoted was the value at *six*.
- That conversation intent predicts conversion. It is H1, and the evidence is vendors'.
- That allocation is biased by `account_type`. Against random lists it sits at the 58th
  percentile. I withdrew it.
- That a better model would not help. I don't know; I was told not to find out.

### The one question that decides everything

*Does `sales_contacts_90d` count the ninety days before the snapshot, or the same ninety
days in which conversion is measured?* If it overlaps, the single significant feature in
the dataset is leakage, and there was never anything predictive here at all. I would ask
it before the presentation if I could. I would ask it in the room if I can't.

---

## Entry 8 — 2026-09-11 ~09:30–10:15 · Building serving/, and three corrections to my own design

Before writing code I re-read what the packet actually asks for here, because it is the
one deliverable where I was at risk of over-building:

> *"A **rough, real** script… It needs to be real and **it needs to run**."* · *"A clearly
> designed template with an obvious, documented spot where a real call would plug in… is
> **judged the same as a live call**."* · *"**Write production-grade code in serving/** —
> you don't need to."* · *"**Not a bigger build.**"*

So: the bar on *code* is low and the bar on *design* is high. That resolved the tension I
had been carrying — a 15-node graph is a bigger build if you construct all of it, and it
is a legitimate design if you construct what today's data supports and **declare the
rest**. Bypassed nodes print what they would produce and what unblocks them, and that
declaration is itself the traceability the fourth section asks for.

Result: 11 nodes run, 2 partial, 2 bypassed. `python serving/pipeline.py` takes four
seconds and writes five artifacts. No new dependencies — `anthropic` is imported inside
the live-call branch only, and I wrote the one markdown table by hand rather than pull in
`tabulate`.

### Three corrections to what I had designed yesterday

**1. I was going to throw away the intent vendor. That was wrong, and the data says so.**
I had concluded "drop the values, keep the flag" and drifted from there into treating the
vendor as useless. Separating the two questions properly:

| | result |
|---|---|
| Does **coverage** predict? | 8.22% vs 3.94%, Fisher **p = 0.003** — yes |
| Does the **score** predict? | quintiles 8.3 / 7.0 / 9.7 / 7.0 / 9.1, Spearman **p = 0.42** — no |

**The vendor tells you who is visible, not who wants to buy.** That is not a broken
vendor, it is a vendor being read as something it isn't. So `CONVERSATION_INTENT` now
*completes* it rather than replacing it, and splits the 300 into four quadrants that each
get different treatment:

| quadrant | n | what it enables |
|---|---|---|
| vendor record **+** a call happened | **103** | contrast the vendor against what the prospect said — the only way to find out if it is any good, and nobody at Cordilla can do that today |
| no vendor record **+** a call happened | **67** | fill the gap **now**, with no new outreach |
| vendor record, no call | **81** | a claim never contrasted against anything |
| neither | **49** | blind — but only **10** are genuinely cold |

And the number that made me rewrite the node: **197 of 481 logged contacts (41%) are with
accounts the vendor never covered.** Those conversations already happen. The signal is
being generated and discarded. That reframes the proposal from *"record calls and in 90
days we'll see"* to *"the team is already producing what's missing and nobody captures it."*

**2. My `VERDICT` node reported errors and stopped there.** It said "this run is
indistinguishable from noise (p = 0.57)" and that was the whole output. A report without
an action is exactly what the organisation already has, and it is how the last model died
quietly. So every detector now emits a **typed finding** —
`what · evidence · severity · owner · action · cost · expect` — and a new `PRESCRIBE` node
ranks them by owner (`crm` / `vendor` / `pipeline` / `model` / `process`). The manager
approves **actions**, not a document. Ten this run; one marked blocking.

Every hygiene proposal now also carries **the rule that stops the defect recurring** — a
validation rule so an account with activity cannot be saved as a Suspect, a labeling rule
so a label is NULL rather than 0 before its window closes. A one-off cleanup is worth much
less than the rule, and I had been proposing cleanups.

**3. `CALIBRATE_VENDOR` did not exist in yesterday's design.** It fell out of the
quadrants: on the 103 accounts where both a vendor record and a call exist, the vendor's
claim is contrastable. That produces something Cordilla cannot produce today — evidence
for the renewal conversation — and it costs nothing beyond the recording capability that
was already proposed.

### What I deliberately did not build

Not LangGraph. It is outside the pinned dependencies, the panel is evaluating design
rather than framework choice, and a typed dict with functions and one interrupt point *is*
the same graph — readable in five minutes and extensible live, which matters more here
than importing an orchestration library.

Not a scheduler, retries, or persistence beyond one JSON file. "A rough script that runs
is enough", and adding those would be the bigger build the packet warns against.

Not an LLM call by default. `--llm template` renders the exact prompt and a worked example
of the return; `--llm live` calls the API. The packet judges these the same, and the
template has the advantage that a reviewer can read the prompt without a key.

### The bug I hit and what it says

`llm.draft(kind=...)` collided with a `{kind}` placeholder inside one of the prompt
templates — the payload key shadowed the function's own parameter. Renamed it
`disagreement_kind`. Small, but it is the kind of thing that would have failed silently
if the template had happened to have a default.

### What still is not real, stated plainly

`CONVERSATION_INTENT` extraction, `CALIBRATE_VENDOR`, and `READOUT` do not run — no
transcripts, no 90-day outcomes. Their contracts are written, their inputs are named, and
the parts that *are* computable today (the quadrants, the contrastable set, the arm
assignments) do run. **If the panel wants to see the system work end to end, that is the
honest answer: it cannot yet, and here is precisely what is missing and what it costs.**

---

## Entry 9 — 2026-09-11 ~10:30–11:15 · Making the agent layer real, and what a local model taught me

Two paths configured, and I tested one of them properly rather than describing it.

### The design

`llm.py` now holds five **agents** rather than five prompt strings. Each is typed:
`purpose · reads · returns · sensitivity · system · template · schema`. The extracting one
is validated against its schema before anything downstream sees it.

Two backends. `anthropic` for hosted, and **one** `openai_compat` adapter that covers
Ollama, vLLM, LM Studio and LocalAI — they all expose the same `/v1/chat/completions`
surface, so moving from a laptop to a GPU box is a `base_url` change. Both speak through
`urllib` from the standard library, so the pipeline still has zero dependencies beyond the
pinned four.

**The routing split is a compliance argument, not a preference.** `conversation_intent`
reads call transcripts — personal data under GDPR, covered by two-party-consent statutes
in CA/FL/IL. Sending them to a hosted API adds a processor to the record, a DPA, and for
EU accounts an international transfer, for the task with the highest volume (every call,
forever) and the lowest writing-quality requirement (it emits JSON). So extraction stays
local and drafting goes to the better writer. `route()` **refuses** to send a `pii` agent
to a hosted backend even if the config says to, and falls back to template with a warning.

### What testing it against `qwen3:14b` on Ollama actually taught me

I would have shipped three wrong assumptions if I had only written the design.

**1. An empty string is a failure mode, and it is the worst one.** My first live call
returned `""` — not an error, not a refusal. Cause: `max_tokens = 1024`, and Qwen3 spends
tokens on a reasoning scratchpad before answering. The budget was consumed before it said
anything. Raised to 4096, added `disable_thinking`, and — more importantly — made the
backend **raise** on an empty completion after trying every JSON mode, rather than pass an
empty string down the pipe.

**2. The strict schema is doing real work, and I nearly made it optional.** Same
transcript, three request shapes:

| request | result |
|---|---|
| `response_format: json_schema` (strict) | 433 chars, **every required field present** |
| `response_format: json_object` | invented `quote` instead of `evidence_quote`; required fields missing |
| no `response_format` | identical failure |

Constrained decoding is what makes a 14B local model honour a contract. I had written
`json_schema = true` as a nice-to-have; it is the thing that makes the local path viable
at all. It is now a cascade (`auto`: schema → object → plain, falling through on an empty
reply) because servers disagree about what they support and some return `""` instead of a
400.

**3. The model got the structure right and the judgement wrong — and that is the finding.**
Full live run, 75 seconds, schema-valid output:

```json
{ "intent_level": "E",
  "evidence_quote": "we've got budget approved for a workflow tool this fiscal year",
  "objections": ["We're just deciding between you and two others",
                 "the incumbent, we already pay them for the ticketing piece…"],
  "next_step_agreed": true, "speaker_role": "user",
  "call_purpose": "negotiation", "confidence": 0.75 }
```

The quote is exact. Both objections are right. `next_step_agreed` is right. And then it
labelled an account that literally says *"we've got budget approved"* as **E — near-no-
intent** — and demoted the VP of Operations to *user* rather than decision maker. Two
extraction jobs right, two judgement calls wrong, at 0.75 confidence, which is itself
over-confident.

That is not a reason to abandon the approach — and the split is informative. **What is
extracted is reliable; what is inferred is not.** So the quote is what a human reads, and
the level is what gets measured before anyone acts on it alone. It is also a reason to
apply to my own agent exactly the standard this audit applied to the inherited model:
**an intent level from an unvalidated extractor is an unvalidated instrument, whoever
built it.** Model size is a tunable here, not a constant — 14B is what was on the machine,
the routing table is one line, and which size is enough is a question the pipeline is
built to answer by measurement. So `confidence` is part of the
contract, the levels are what `READOUT` measures against real outcomes, and until that
measurement exists the extraction is a hypothesis. The irony is not lost on me — I spent a
day proving a model was trusted without being measured, and the first thing my own
pipeline does is produce a number that has not been measured either. The difference is
that this one says so and has a readout scheduled.

Practical consequence for the proposal: a 14B model on CPU takes 1–3 minutes per
transcript. That is fine for a nightly batch and useless for anything interactive, which
is another reason the design is a weekly cycle rather than a live assistant.

### The parser, and why it is deliberately tolerant

Local models wrap JSON in `<think>` blocks, code fences, or a sentence of preamble. None
of that is the model being wrong, so `_extract_json` strips reasoning tags, pulls out
fenced blocks, and otherwise walks the string brace-by-brace to find the balanced object.
Then a minimal contract check — required fields present, enum values legal. Not a full
JSON-Schema implementation; enough to catch prose, a missing field, or an invented level.

### Failure stays visible

Every agent falls back to template mode **with the reason printed where the output would
have been**: `[backend 'local' failed after retries — TimeoutError: timed out]`. It does
not guess and it does not silently skip. That is deliberate: a pipeline that quietly
produces a plausible answer when its model is down is the exact failure this whole exercise
is about. I saw it work twice today, on the empty-string bug and on a timeout.

`python serving/pipeline.py --check-llm` probes the configured backends and the agent
routing without running anything.

---

## Entry 10 — 2026-09-11 ~11:45 · Aligning the proposal with what actually runs, and being strict about which numbers are real

Rewrote `PROPOSAL.md` against the pipeline as built rather than as planned. The discipline
that mattered was separating three kinds of number, because after building a demo it is
very easy to quote a synthetic figure in a document that reads as findings.

**Real — from the two provided CSVs and the pickle.** Everything in §2. And in §3: the
four intent quadrants (103 / 67 / 81 / 49), the 197-of-481 contacts in uncovered accounts,
130 never contacted with 25 carrying a live trial, the 24 / 22 / 9 disagreements, 86 of 101
scoring Suspects with activity, the three arms of 30 balanced across industry, Σp = 19.66,
and the ten findings the normal run emits. These are what the proposal argues from.

**Real measurement, synthetic input.** The extractor's scores — next-step 1.00,
within-one 0.80, hot-vs-cold 0.80, exact level 0.50, speaker role 0.05. `qwen3:14b` really
produced those, but against transcripts I generated. So it measures the model's capability
in a controlled setting, not its accuracy on Cordilla's calls. Stated that way in §4.

**Synthetic — demo only.** The vendor-agreement table (58% on 12 accounts), the simulated
readout (6.7 / 3.3 / 3.3), and `ACC-01282`. **None of these are in the proposal as
findings.** The readout's *shape* is cited — one cycle at a realistic rate with no true
difference still produces a 3.3-point spread — because that is a property of the design,
not a result about Cordilla. The 58% is in `serving/README.md` with the caveat attached,
where it belongs: the method is the deliverable, the number is not.

A cheap check while doing this: two different quantities both come out as 103 in the
scoring set (accounts with `web_touchpoints == 0`, and accounts with both a vendor record
and a logged call). I assumed a bug and recomputed. Coincidence.

**On length.** 1,274 words against a stated ~800–1,200. Five compression passes; two of
them made it *longer*, which is a good lesson in editing by search-and-replace. What did
not get cut: any number, any caveat, or the blocking question. What did: adjectives, and a
paragraph in §4 that was making the same point twice.

**What the proposal does not claim**, and this is the line I was most careful about: it
does not say the conversation layer works. It says vendor coverage predicts and the vendor
score does not (both real, both measured), that 41% of the team's contacts already happen
where the vendor is blind (real), and that whether intent extracted from those calls
predicts conversion is **H1 — the hypothesis the arms exist to test**. If that reads as
less confident than a proposal usually does, that is deliberate. The last model at Cordilla
was confident.

---

## Entry 11 — 2026-09-11 ~11:00–12:15 · Measuring the agent, improving it three times, and then measuring VALUE instead of accuracy

### Three contract revisions, each decided by a number

The v1 extractor scored 50% on exact intent level and 5% on speaker role. Rather than
reach for a bigger model, I read the error pattern and changed the questions.

| | v1 | v2 | v2.1 | **v2.2** |
|---|---|---|---|---|
| **`ready_to_act`** (routed on) | — | 1.00 | 0.90 | **1.00** |
| ↳ missed / false alarms | — | 0/0 | 0/2 | **0/0** |
| `next_step_agreed` | 1.00 | 0.55 | 1.00 | **1.00** |
| `intent_level` exact | 0.50 | 0.60 | 0.45 | **0.80** |
| within one level | 0.80 | 0.90 | 0.80 | **1.00** |
| hot vs cold | 0.80 | 0.75 | 0.75 | **0.95** |
| `speaker_role` | 0.05 | *deleted* | — | — |

**v1→v2.** The six-level grade scored 50% exact, but collapsing the *same* answers to a
binary scored 95%. A rep's decision is binary, so `ready_to_act` became primary and the
grade became context. `speaker_role` deleted — 5% is worse than guessing, and a transcript
rarely states a title. The CRM has it.

**v2→v2.1.** `ready_to_act` hit 1.00 and `next_step_agreed` collapsed to 0.55, **all nine
errors false negatives**. Cause: v2's prompt listed five numbered work steps and
`next_step_agreed` was in none of them, so the model stopped looking for it. *Changing a
prompt silently broke a field I never mentioned.* Two replies also contradicted themselves
— `ready_because: budget_stated` with `ready_to_act: false` — which a typed schema cannot
catch. Agents now declare **invariants**: cross-field rules checked after schema
validation, retried on violation.

**v2.1→v2.2.** The invariant turned those contradictions into two false alarms, both
`timeline_stated`: *"sometime next year maybe, not this quarter"* and *"I can take it to my
VP next month"*. The model read any mention of time as a timeline. The fix was in the
definition, not the model — budget must already be allocated; a date must be for buying or
going live, not an internal errand, and not hedged. Everything improved, **including the
six-level grade, 0.45 → 0.80, which nobody touched.**

The lesson is about the contract. Same 14B model, same 20 transcripts, 50% → 100% on the
field that matters, three cycles, ~20 minutes of compute.

### Confidence: calibrated on the question it can answer

v2.2 confidence is 0.85–1.00, mean 0.97. Against `ready_to_act` that is honest — it says
0.97 and scores 1.00. Against the six-level grade it is not: same 0.97, scores 0.80.
**The model knows the binary question is easy; it does not know the six-way one is hard.**
So confidence is trusted for the field we route on and ignored for the field we don't.

The 0.4–0.8 gate stays in `RECONCILE` even though v2.2 puts zero accounts in it. In v1
that band scored 25% on hot-vs-cold — worse than chance — while both tails scored 86–100%.
It costs nothing and it is what would catch the next regression.

### Then I stopped measuring accuracy and measured value

100% accuracy is worth nothing if the agent never contradicts what the team was going to
do anyway. So `VALUE` counts only decisions **changed**:

| | accounts | contacts | what it buys |
|---|---|---|---|
| **RESCUED** model said skip, prospect said buy | 2 | 5 | opportunities the ranking would have dropped |
| **RELEASED** effort in, prospect said no | 5 | **24** | 24 contacts redirectable this quarter |
| CONFIRMED everyone agrees | 6 | 11 | **nothing** |

7 of 20 decisions changed (35%); 24 of the quarter's 481 contacts freed (5.0%). And the
**CONFIRMED row is reported at zero on purpose** — six correct extractions that change no
decision. Counting them as benefit is exactly the inflated metric this audit found in the
inherited model.

Both value legs are stated as conditionals, because both are unproven: *if* `ready_to_act`
predicts conversion (H1), each rescued account is a dropped opportunity; *if* the freed
contacts are re-spent, that is 5% of outreach moved off dead accounts. `READOUT` at day 90
settles both.

### The finding I did not expect

On accounts with a transcript, the model's mean score is **6.9% for those that said no** and
**5.5% for those that said yes**. It has them inverted — and the cause is contact count
(3.2 vs 2.0), its strongest feature. `ACC-00806` received four contacts, the prospect said
*"we just renewed for three years, please take us off your list"*, and the model scores it
6.4% — above the median.

That is audit §3.5's circularity, which I could only argue statistically, **operating
visibly on named accounts**: effort already spent on a dead account raises its rank, which
justifies more effort. The conversation is what breaks the loop, and that is a better
argument for the whole design than anything in the proposal. Now a finding the pipeline
raises on its own.

⚠️ Synthetic transcripts. The counts are demo; the mechanism is audit §3.5, which is not.

---
