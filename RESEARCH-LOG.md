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

**TODO(ignacio): paste the 3-4 actual prompts from this session that shaped a decision.**
The packet asks for specific prompts, not a summary. Pull them from the chat history —
particularly the one that set up the six-lens debate, and whichever follow-up made it
produce the calibration-by-decile table.

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

**TODO(ignacio): result of that check goes in Entry 2.**

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
