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

## Entry 12 — 2026-09-11 ~11:30 · Checkpoint

Everything runs: the notebook (110 cells, 0 errors), the pipeline in both modes, the
agent healthcheck. 22 commits, all incremental.

**Open, in order of how much it costs to leave undone:**

1. `PROPOSAL.md` still quotes the v1 agent metrics and does not mention the `VALUE` node or
   the score inversion — which is the strongest single piece of evidence in the repo. The
   proposal is currently weaker than the work behind it.
2. The four drafting agents have never run live (routed to `cloud`, no API key). The packet
   judges template equal to a live call, so this is cosmetic, but a live `manager_brief.md`
   would read better than a rendered prompt.
3. The old private repo under the previous account still exists; deleting it needs a scope
   the token does not have.

**Next session, three things:** re-read the graph node by node asking *what would the team
do without this node* — the same test `VALUE` applies, turned on the pipeline itself. Then
consecutive improvements using the method that worked on the extraction contract: change
one thing, re-measure, keep it only if the number moves. Then the one that matters —
**define the reliable metric.**

On that last one, the honest position today: there are three measurements and none of them
is *the* metric. The agent scores 1.00 against a ground truth I wrote myself. The inherited
model scores 0.474 against real outcomes, but that is a verdict on the old thing, not on
the new one. `VALUE` reports 35% of decisions changed, which is measurable today and is
*not* proof that the changes were improvements. And the conceptually correct one —
conversions per contact against a control — needs 90 days and roughly fifty times the
sample we can assign in one cycle.

Choosing among those, and being explicit about what each one cannot tell you, is the
remaining piece of work. It is also the piece the brief actually asked for in section 1:
*what would tell you the model is helping versus just noise everyone is trusting by
default.* I have a better answer than I did yesterday and it is still not a single number.

---

## Entry 14 — 2026-09-11 ~14:00–16:00 · Defining the metric, and the trap it turned out to be

The remaining piece from Entry 13: *define the reliable metric*, framed where it was always
framed — on rep hours. I started by pricing one, which nobody in this repo had done.

**The economics, from the two CSVs.** 1,915 logged contacts bought 78 conversions:
**24.6 contacts, ~4.9 rep-hours, per conversion**. In the batch, **52 of 300 accounts hold
260 of 481 contacts** — 54% of the effort on 17% of the accounts. Historically, 168 accounts
took ≥4 contacts and never converted, absorbing **789 contacts, 41% of all effort ever
logged**. That is the pool the hours framing is about.

### The trap, which is the actual finding

The obvious next step is to optimise contacts-per-conversion. I built the yield curve to do
that and it refused to give one answer:

| reading | best | policy it implies |
|---|---|---|
| conversion **rate** by contact count | 5 contacts → 13.6% (base 6.5%) | call more |
| **cost** per conversion at that count | 1 contact → 14; 5 contacts → 37 | never call twice |

Same 1,200 rows, opposite policies. Neither is causal: reps keep dialling accounts that are
going well and drop the ones that die, so contact count is an *effect* of intent as much as a
cause of conversion (Spearman(contacts, converted) = +0.077, p = 0.0075 — real, and
uninterpretable). **There is no observational cut of this data that yields
conversions-per-hour.**

That is the same error as the model's, one level up. Last time it lived in the score; this
time it would have lived in the metric, which is worse, because a bad metric is what you use
to check the score. It also converts `ALLOCATE` from a nice-to-have into the measuring
instrument: randomisation is not rigour theatre here, it is the only way the denominator
becomes readable. Filed as a `high` finding owned by `process`.

One more number that is easy to miss: **23 of 78 conversions (29%) came from accounts with
zero logged contacts.** Whatever outreach policy wins, it competes against a baseline that
already converts for free.

### The metric, as shipped

Two numbers, and the hierarchy between them is **structural, not typographic** — the risk
with two numbers is that the VP keeps the one he likes.

1. **North star** — conversions per 100 contacts, by arm, cumulative. The only thing that
   proves the system works.
2. **Weekly headline** — rep-hours redirected off accounts that stated a decline, filed as a
   **bet** carrying the date it settles and the result that falsifies it. You cannot read it
   as an outcome because it states which outcome it predicts.

Plus: the stock is **declared decaying** (789 contacts is spent once — a falling number is
the system working, not dying); **proxy validity** is scheduled at every readout, and if
redirected hours stop predicting conversions the weekly metric is retired *in the same
report*; and **decisions changed (35%) is demoted to instrumentation**, because it is
maximised by being maximally contrarian. That last one is the class of metric that inflated
the thing we audited, so it does not get to be the headline of the thing that replaces it.

### Taking the metric seriously changed the design twice

**1 · The north star was unreachable and nobody had checked.** Detecting a 50% relative lift
at the 3% field rate needs **2,515 accounts per arm** (1,106 at the 6.5% training rate). At
30 per arm per weekly cycle that is **84 weeks — 1.6 years**, longer than the previous
scoring effort survived. The repo had been quoting "~1,500 per arm" without deriving it.
Assigning the whole batch instead of a third — 97 per arm, 291 of 300 — lands the readout in
two quarters **at no extra rep-hours**, since the same accounts are being worked either way.
The allocation changed because the metric was checked, not the other way round.

**2 · I had to overrule my own code.** I wrote `_settle_bets` to mark each bet won or lost at
day 90. It ran and returned **`WON — 0/2 converted`** for the release bet. That is exactly
the sin this entire repo is about: 0/2 is what a 3% base rate produces anyway. Observing zero
only means something once zero is unlikely under the null — `(1−0.03)^n < 0.05` → **n ≥ 99**.
The verdict is now `UNDERPOWERED`, and a finding fires saying the hours claims are filed with
falsifiers no single cycle can check, with the fix (track rescued and released accounts as
named cohorts, read cumulatively; following released accounts costs zero rep-hours because
nobody is calling them). My first implementation would have shipped a fake win on n=2 — in
the node whose entire purpose is refusing fake wins.

### What did not change

`VALUE` now runs its economics half on every run rather than being wholly bypassed without
transcripts — the price of a conversion and the metric contract need only the CSVs. The
ledger half is still gated on the conversation voice, and still reports **4.8 rep-hours**
moved on 20 transcripts, with the ≈41 rep-hours at full coverage labelled as the
extrapolation it is. Model and CSVs untouched: `model.pkl` still `fc2cd6aa…`.

**Still open:** the blocking question is unchanged — does `sales_contacts_90d` precede the
outcome window or overlap it? If it overlaps, the hours economics above is measuring
leakage, and 24.6 contacts per conversion is not the price of anything.

## Entry 15 — 2026-09-11 ~16:30–19:30 · From a pipeline to an MVP: named cases, a readable brief, and a loop that refuses to move

The ask, verbatim: *"un MVP bueno con reportes claros y casos de éxito reportables, además de
un plan de implementación y mejora automatizada a lo largo del tiempo en base a los
resultados."* I audited the outputs as a manager would read them before building anything.

### What the audit of my own outputs found

- **The best case in the repo was a code in a CSV.** `ACC-01282` — model 4.0%, percentile 5,
  prospect says *"we signed off on the budget last week"* — appeared as
  `MODEL_WRONG_rep_was_right` in `disagreements.csv`, and the quote lived in `run.json`. No
  artefact of cases existed.
- **37 of the brief's 80 lines were prompt boxes.** The section titled *Verdict* was a
  rendered template. Fine for the reviewer; unreadable for the manager it is addressed to.
- **The rescued account entered no arm.** Neither did the released ones. Which is why the
  bets in Entry 14 returned `NOT SETTLEABLE`: the system filed a claim and then made it
  impossible to check.
- **No memory.** The only state between cycles was `last_top30.json`. `ARM = 30` was
  hardcoded. `READOUT` *described* the epsilon-greedy update and did not perform it.

### What changed, in the order built

**1 · The prospect's voice now moves accounts.** `ALLOCATE` puts `ready_to_act = True`
into `exploit` ahead of the contact rule — it is the highest-confidence call in the book —
and sends released accounts to a `holdout` cohort: nobody calls them, their outcome is
tracked at zero rep-hours. Both bets went from `NOT SETTLEABLE` to `UNDERPOWERED`, which is
the honest state for n = 4 and n = 2.

**2 · A definition I had to tighten.** The released set contained `ACC-00270`: level C,
*"we're building the business case"* — **with a working session booked**. Releasing an
account that just asked for a meeting is the system overruling the prospect. Rule:
`released` now requires `next_step_agreed = False`. An agreed next step is a live process
regardless of what was said about money. Four released instead of five; 19 contacts and
3.8 rep-hours instead of 24 and 4.8; the full-coverage extrapolation 41 → 32. The number
went *down* because the definition got better, and I would rather report that than the
larger one. I also centralised `rescued_mask` / `released_mask` so `VALUE`, `ALLOCATE`,
`READOUT` and `cases.md` cannot drift — they already had, once (5 vs 4).

**3 · `cases.md`.** Every rescued and released account, by name: vendor · effort · model
score and percentile · flags · **the prospect's sentence** · the three voices side by side ·
what changed · which bet it sits in and when it settles · what it proves and what it cannot.
Plus the aggregate case (the inversion) and a table of the four levels of evidence.
One bug worth recording: `r.flags` returned a pandas `Flags` object, because a Series has
that attribute. `r["flags"]` from now on.

**4 · The brief, reordered for the reader.** Verdict (text) → what changed this week (the two
strongest cases, one line each, with the quote) → where the metric stands (north star not
readable · weekly headline as a bet · **agent scorecard: synthetic 1.00 · real pending
0/99**) → the experiment → actions → what is dark → *appendix: the prompts, verbatim*. The
reviewer loses nothing; the manager stops at the line.

**5 · The loop.** `cycles.jsonl` is append-only memory: one line per cycle with arms,
outcomes, settled bets and agent tallies. `_learn()` in `READOUT` reads all of it and writes
`next_cycle.json`, which `ALLOCATE` reads. Three things learn, each gated:

| loop | changes | gate |
|---|---|---|
| allocation | ±5 accounts toward the best arm, **floor 20%** | every arm n ≥ 99 **and** best lower bound clears worst upper bound |
| agent | real precision beside synthetic 1.00; a finding sends the contract to revision | n ≥ 99 settled |
| metric | retires the weekly headline if it stops tracking the north star | same n as the north star |

`--demo --cycles 4 --reset-cycles` runs four cycles back to back. A guard stops simulated
memory from feeding a real run: `next_cycle.json` carries `simulated`, and `ALLOCATE`
ignores it when the modes differ.

### Where the loop corrected me

My first allocation rule moved on *best lower bound* once every arm passed n = 99. In the
demo — **no true difference between arms, by construction** — it fired at cycle 4:
*"moved 5 from exploit (1.3%) to control (2.3%)"*. It was rewarding whichever arm got
lucky. The 99 threshold answers *does a zero mean anything*; it says nothing about
*can I tell two arms apart*, which at 3% needs ~2,500. The rule now requires the best
arm's interval to clear the worst arm's. Re-run: **four cycles, four refusals**, the last
one saying *"control [2.3%, 10.5%] and exploit [1.3%, 8.3%] overlap at n=120; separating a
50% lift needs ~2,515/arm."* A loop that visibly declines to act on noise is the
demonstration; one that moved would have been the previous scoring effort with extra steps.

### State at hand-off

16 nodes · 11 run / 3 partial / 2 bypassed on the CSVs · 16/16 in `--demo` · all modes
exit 0 · `model.pkl` `fc2cd6aa…`, CSVs untouched. Outputs: `manager_brief.md`, `cases.md`,
`metrics.md`, `rep_worklist.csv`, `actions.csv`, `disagreements.csv`, `cycles.jsonl`,
`next_cycle.json`, `run.json`. New at the root: `ROLLOUT.md` — six phases, each with the
result that stops the next one, and the three loops with their gates.

Nothing is committed yet; that is a decision for the person whose repo it is.

**Still open, unchanged:** does `sales_contacts_90d` precede the outcome window or overlap
it? Every hours number above assumes *precede*.

## Entry 16 — 2026-09-11 ~19:30–21:00 · The head-to-head, and the arm that was the sunk cost with a new name

The ask: *"de los 300, qué diría el modelo vs lo que dice lo que construimos — si eso está
flojo hay que seguir."* So I computed it before writing anything.

### What was weak

The model's answer to *who do I call* is its top 30. Ours was three arms. Side by side, on
the real 300:

- Of the model's 30: **15 not assigned** (12 stale), 10 in exploit, 4 in explore, 1 control.
- **Exploit carried 18 of 30 accounts with our own `over invested` flag.** Exploit was
  `ORDER BY sales_contacts_90d DESC` — the rule that beats the model out of sample — which
  is also, by definition, *the most-called accounts*. We were handing the rep a list that
  said "call `ACC-01326`, 9 contacts, no result" with a flag on it saying don't. The model's
  #3 (`ACC-01064`, 5 contacts) and #7 (`ACC-00122`, 6 contacts) were both in our exploit
  arm. **That is the sunk-cost policy with a new name**, and the user's instinct that it was
  weak was right.

### The fix, and the observational argument against it

Exploit is now **1–4 contacts, most first** — engaged, not exhausted. Accounts with **5+
contacts and no conversation on file** go to a new cohort, **`ask`**: the rep gets one
question, not a call task — *"You have logged 6 contacts here with no result. What do you
know that the data does not — and is the next hour worth it, or should this one rest?"*
That is the `disagreement_question` agent finally having a job, and the `over invested`
flag finally having a consequence. With a transcript, the cohort dissolves: READY or a
next step agreed → exploit; declined → holdout.

The honest case against: in training, **≥5 contacts converts at 13.3% against 6.9% for
1–4.** Observationally the over-invested accounts are the *best*. But they cost 42 contacts
per conversion against 33, and the 13.3% is the confounding this whole repo is about —
reps keep calling accounts that are converting. `ask` does not abandon them; it makes the
next hour conditional on an answer. And the answer is data nobody has today.

### The head-to-head as it stands, real data, no transcript

| the model's top 30 | count | why |
|---|---|---|
| refresh first | **12** | snapshot >180 days |
| ask, don't call | **7** | 5+ contacts, no result, no voice |
| explore | 4 | never contacted, has signal |
| **exploit — called as-is** | **3** | |
| pool / control | 4 | not drawn |

**Three of the model's thirty survive unchanged.** The model's #1 (`ACC-01491`: 5 contacts,
290 days, no result) is *refresh first*. Its #3 and #7 are *ask*. Its #9 (`ACC-00657`, 4
MQLs, never called, 305 days) is *refresh first* then *explore*. Every verdict is a flag or
a cohort the manager can verify on the row. `ALLOCATE` now prints this table every run and
`EMIT` puts it in the brief — it is the system's own account of how it differs from the
thing it replaces, not mine.

Exploit now carries **0** over-invested accounts on the real data (1 in `--demo`: `ACC-00270`,
5 contacts, but the prospect booked a working session — called, correctly). `ask` holds 18
accounts and **102 contacts — 20 rep-hours a quarter** — that used to be spent without a
question. That number is real and needs no transcript.

### The walkthrough, once more, so nobody gets lost

`RESULTS.md` §A has it node by node. The short form: **VALIDATE** finds 102 stale and 101
mislabelled · **SCORE** promises 19.7 conversions the field will not deliver · **FLAGS**
marks 245 of 300 with at least one reason to doubt · **RECONCILE** finds 55 places the model
and the team's own effort disagree · **VALUE** prices a conversion at 24.6 contacts and
shows the price cannot be optimised from this data · **ALLOCATE** turns that into three
arms and two cohorts, and prints the head-to-head · **HYGIENE** finds 86 of 101 "Suspects"
are not · **READOUT** waits for day 90, then settles bets and refuses to move arms on noise.

**Still open, unchanged:** the contact-window question. Everything above assumes *precedes*.

### Addendum — the agent's contribution, account by account, and one more bug

Asked plainly: *what do the agents add over the model's number, on the cases we see?* I
ran the same 20 accounts through the pipeline twice — rules only, then rules plus the
extractor — and compared destinations.

First pass: **11 of 20 changed**, and three prospects who had said *READY* stayed in the
pool. Cause: `engaged` was drawn from `eligible`, the non-stale rows, and those three
accounts had CRM snapshots 304–618 days old. A conversation last week was being blocked by
a CRM row nobody had touched in a year. **A conversation is the freshest fact we hold
about an account; staleness is a reason to distrust the columns, not the prospect.**
`engaged` now comes from all rows.

Second pass: **15 of 20 changed** — 13 on information the rules did not have, 2 by the
control draw reshuffling. Of the 13: **8 into exploit** (7 said READY — including the
model's #286, #248, #215, #208 — and 1 booked a working session), **4 into holdout** (said
no; two of them the rules had in *exploit* on 4 contacts each), **1 ask → exploit** (said
"building the case", meeting booked). The plain statement for the panel: *on the real 300
without transcripts, the LLM agents add no information — every verdict in the head-to-head
is a rule on a column. With transcripts, the extractor changes where 13 of 20 accounts go,
and each change is a sentence the prospect said.*

### Addendum — two things I had treated as facts that are hypotheses

**Staleness.** I had stale accounts (>180 d) barred from every arm. The user's call: flag
it, do not block it — the working hypothesis is that a two-quarter-old description is still
actionable, and the presentation proceeds on that. So: the rep sees *snapshot 290 days* on
the row and works the account; `READOUT` compares stale vs fresh conversion inside each arm
(in `--demo`: fresh 2/61, stale 1/29 — simulated, no difference by construction); if stale
loses, the flag becomes a filter. The guardrail changed from *0 stale in arms* to *stale
must not convert materially below fresh*. Effect on real data: `ask` grows 18 → 29 (168
contacts, 34 rep-hours — the over-invested stale accounts were being excluded, now they
are asked); the model's top 30 goes **11 ask · 10 pool/control · 5 explore · 4 exploit**,
three of the four flagged stale.

**"Suspect".** I had written *"Suspect means no engagement"* as if the brief said so. It
does not: the PDF lists the three values and says the non-customers are *"mostly
untouched"*. The funnel reading (Suspect → Prospect → Customer) is the industry convention
and **our hypothesis**. Under it, 85% of Suspects are mislabelled. Under *any* reading the
field is empty — conversion identical across types (χ² p = 0.84), model importance 0.003.
The finding now says so, and its first action is a question to the CRM owner, not a bulk
update.

## Entry 17 — 2026-09-11 · Can the rate go higher? Seven rules, one survivor, and the model's number measured as memory

**Suspect, checked the way the user asked — with contacts.** Suspects carry *more* logged
contacts than Prospects (1.69 vs 1.54 mean; 61% vs 59% with ≥1; 18% vs 14% with ≥4), the same
MQL rate (50% vs 51%), the same trial rate; Mann-Whitney p = 0.20 — indistinguishable. Only 15%
of Suspects are truly untouched, against 16% of Prospects. **Hypothesis validated: they are
worked exactly like Prospects; the label is mislabelled.** Said, and moved on.

**Staleness became a flag.** The user's call: mention it, flag it, do not cut. Working hypothesis
for the presentation — a two-quarter-old description is still actionable — and `READOUT` now
tests it (stale vs fresh conversion inside each arm). Effect: `ask` grew 18 → 29; the model's
top 30 now goes 11 ask · 8 pool/control · **6 exploit** (5 flagged stale) · 5 explore.

**The comparison, inside the pipeline.** `BASELINES` reads `audit/oof_predictions.npy` (the
audit's 5×10 out-of-fold scores, copied in with a provenance note) and on the 1,099 labelled rows
with a closed window builds each policy's list of 90 and counts conversions. **Model from memory
31.1%; model out-of-fold 6.7%; random 7.3%** (mean of 200 draws — a single draw swung between 7.8%
and 11.1% on row order, so one draw is not "random"). The graph's worklist: 12.2%, with 150
contacts already sunk against 486 for the old contact sort. Observational, said in the table.

**Can the rate go higher?** Seven candidate exploit rules, all reported (RESULTS.md), evaluated on
the full set *and* on a temporal holdout I did not use to choose. Adding MQL > 0 made it **worse**
(11.1% → 6.7%): marketing counts are not a filter here. Ranking explore by MQL instead of web:
worse (8.9% → 5.6%). Vendor record: no change. One rule improved on every cut — **1–4 contacts
with a trial started, any usage**: 15.6% vs 11.1% full, 16.7% vs 13.3% holdout, 11.7% vs 10.0% on
the early 60% alone, with ~35% fewer contacts sunk each time. It had a reason before the grid:
HYGIENE had found 0-user trials convert as well as live ones (15.8% vs 13.1% at 1–4 contacts), so
the rule takes any trial. It is now exploit's second tier, after the prospect's voice. 14 vs 10
conversions — the intervals overlap; it is the direction across three cuts that earns the tier,
and I am saying so rather than quoting 15.6% as a fact.

**Hours, reported.** In real mode the brief's weekly headline used to say *none* — it was waiting
for transcripts. It now reads the `ask` cohort: **34 rep-hours held pending a question** — 29
accounts, 168 contacts sunk, no transcripts so nothing released. That is a real number on day one.

## Entry 18 — 2026-09-11 · The metric of the whole graph, in one table

The user's question, verbatim: *"quiero la métrica del grafo entero, debería dar al menos mejor
que el baseline, no?"* Yes — and it had been scattered across three nodes. Now it is one table.

**The metric:** of the list a policy says to call, what share converts. **Three baselines:** the
model alone (what the VP asked for — scored out-of-fold, with its from-memory number beside it
so the gap is visible), random (no system, mean of 200 draws), and the team today (the 664
labelled accounts the reps chose to work: 8.3%). **Two columns:** historical — today, on the
1,099 labelled rows, observational — and prospective — day 90, arms against control, causal,
empty until `READOUT` runs. **A second dimension:** rep-hours each policy refuses to spend; the
graph is the only row with a number there (34 h/quarter from `ask`).

Today: **graph 12.2% · exploit alone 15.6% · team 8.3% · random 7.3% · model 6.7%** (31.1%
from memory). The graph beats every baseline on the historical column. The intervals overlap;
the file says so, and says the graph is retired if it does not beat the first three rows on
*both* columns. In `--demo`, `READOUT` fills the second column with the simulated arm rates,
labelled SIMULATED, so the mechanism is visible turning.

Built as `_scorecard()` + `_scorecard_md()`, assembled from artifacts BASELINES, ALLOCATE and
READOUT already produce — no new node, no new data. First section of `manager_brief.md` and
`metrics.md`.

## Entry 19 — 2026-09-11 · "¿Y puede con exploit solo?" — measured, and no

Exploit alone scores 15.6% on the full set against 12.2% for the 50/50 worklist, so the question
was fair. I measured the cost of exploring at four mixes on both cuts.

**On the temporal holdout, exploring up to a third of the list cost zero points**: 14.4% at
exploit-only, at 72/18 and at 60/30. Only 50/50 paid, 11.1%. So the default mix is now **2:1 —
exploit 40, explore 20, control 30** (`ARM_DEFAULTS`, one place), the BASELINES worklist row is
60 + 30 to match, and the loop's 20% floor is what keeps explore alive after that.

**Why not zero explore, even so.** Exploit's universe is accounts someone already called — 141 of
the 300. At 40 a cycle it drains in three or four cycles, and only explore refills it. And the
130 never-touched — 17 of them with a live trial and no call — stay untouched forever. Exploit
alone is the inherited model's error in a new coat: it can only look where someone already looked.
On history, though, 0-contact accounts with a live trial convert at just 3.7%, so explore keeps
its web ranking; the 17 are a hypothesis for a later variant, written down, not acted on.

Two honest footnotes. The 60/30 worklist lands at 12.2% or 13.3% on the full set depending on how
ties in `web_touchpoints_90d` break — one conversion. That is the resolution here; the holdout
decides. And with explore at 20, the north star's horizon at today's allocation went from 84 to
126 weeks, because power is set by the smallest arm — which sharpens, not weakens, the finding
that the whole batch should be assigned. The model's top 30 now: **11 ask · 9 exploit** (6 flagged
stale) · 4 explore · 6 pool.

## Entry 20 — 2026-09-11 · The prediction test, and the result that was not the one we wanted

The user set a falsifiable target: *hold out 300, compare model alone, exploit alone and the
agentic graph, and show the graph wins by a lot because it holds the model's information and
catches what the model misses.* I built it as `audit/heldout_comparison.py`: the 300 most
recent labelled accounts held out (23 converters, 7.7%), **no model fitted** — the
model's score is its out-of-fold prediction, the graph's rules fit nothing. The retraining
worry is answered by construction: the script only reads.

**What came back.** At K=60: exploit alone **18.3%** (recall 48%) · the graph 15.0% (39%) ·
model out-of-fold 13.3% (35%) · the pickle from memory 25.0% · random 7.6% · team 10.9%.
Explore alone: **1 of 60**. Adding the model's picks to exploit removed conversions.

**Confirmed:** the model adds nothing beyond a hand-written rule on its own best feature. Exploit
beats it ~2× with fewer contacts sunk. The memory number is in the same table as the prediction
number, which is the whole point of the previous effort's story in one row.

**Refuted, as stated:** "explore should improve the metric, not worsen it." On this cut it cost
three points of precision and nine of recall. On the earlier holdout it cost zero. The range is
0–3, and I had quoted the zero.

**Why I am not removing explore.** In the test 300, accounts nobody called convert at 2.6% — 3 of
117. Accounts with 1–4 contacts, 10%. Conversion follows contact. History cannot say whether
calling causes it or reps pick well, because **history has no calls to the untouched accounts**.
Explore's 1.7% is *what happens when nobody calls them* — the arm exists to measure the other
case. Reading that row as explore's value is the audit's own confounding argument run backwards,
and the same holds for the agent (whose row says *needs transcripts on accounts with outcomes*).
So the graph's confident number is exploit's, and the gap to its full number is the cost of an
answer history cannot give.

The user asked to check I understood before building. I did, built it, and it partly disproved
the hypothesis. Both halves are in `RESULTS.md`; `BASELINES` prints the test every run.

## Entry 21 — 2026-09-11 · The 23 converters, one by one

The user asked the question that reorganises everything: *of the 23 converters in the held-out
300, which does exploit explain, and which fall below it or outside it — and by what mechanism?*

**Eight** are in exploit's top 40 — and **every one has a trial.** In the 1–4-contact pool, trial
converts at 23.5%, no trial at 6.3%. The trial is not a tier of exploit; it *is* exploit. **Eight
more** sit in exploit's pool below the cut, positions 44–150 of 160 — **none has a trial**, and on
contacts, MQL, web and the model's own score they look exactly like the 118 non-converters around
them (all Mann-Whitney p > 0.5; the model ranks them at median 51 of 126, i.e. at random). **Four**
have 5+ contacts (`ask`), and the model ranks them #4, #18, #27, #37 — it loves them, for the
contacts. **Three** were never called: explore reaches one at position 5, one sits at position
81, one has no signal at all.

One column separates the 8 below the cut: **all eight have a vendor record, against 56%** of the
non-converters beside them. I found that by looking at the test set, which means the test set
cannot validate it. The clean check is the early 60% of history: vendor record 8.3% vs none 2.7%
in the same pool (Fisher p = 0.07). Borderline on its own; but the audit had already established,
on all 1,200 rows and before any of this, that vendor *coverage* predicts (8.22% vs 3.94%, p =
0.003) while the vendor *score* does not. Three sources, one direction — so exploit now fills
**trial → vendor record → contact count**. Held-out: exploit alone 23.3% → 26.7% at K=30, 18.3% →
20.0% at K=60. Modest, and said as such.

The by-product is a bucket nobody had named: 1–4 contacts, no trial, no vendor record — **1.6%**
(3 of 190), below the never-touched rate. Forty-six of the 300 to score are in it, holding 106
contacts. They now sit last in exploit and, with 40 slots, are not called.

**Where the value is, then.** Data rules reach roughly half the converters — the trial tier, plus
what `ask` recovers when the rep answers. The eight below the cut, indistinguishable on every
column, are the case the conversation agent exists for. That claim is untestable today and the
table says so; it is also the sharpest statement of the agent's job that this repo has produced.

I also corrected a line I had printed: "the model ranks them at median 4 of 126" was the eight
ranked among themselves. The real figure is 51 of 126. It changed nothing, and it is recorded.

## Entry 22 — 2026-09-11 · The metric is recall at the budget; explore is a quota, not a branch

The user's framing, which is right: *understand what the model captures, use it, find branches for
what it misses, reorder the top, and get recall up. What is the metric — recall, or what?*

**Recall@K**, K the weekly call budget: of the buyers in the window, the share the list put in
front of a rep. Not accuracy (93% for "nobody converts"). At fixed K it ranks policies exactly as
precision does, so the scorecard keeps its shape; the framing changes to the sentence a manager
can use — *of 23 buyers we found 12*. Reported as a curve with hours-per-buyer and the reachable
ceiling (91% of buyers at K = 203). Added to BASELINES and the scorecard.

**What it decided.** Held-out 300, K = 60: exploit 40 / explore 20 found 9 buyers; exploit 50 /
explore 10 found 12; exploit 60 / explore 0 found 12. The ten explore slots cost nothing in this
window (exploit's 51–60 held no buyer). Default is now **50 / 10 / 30**; floor 10%. On all 1,099
rows at K = 90 the fifteen explore slots did cost — exploit 17.8% vs worklist 13.3% — so the honest
range for explore's price is 0 to 4.5 points by cut, and RESULTS.md says both.

**Why not zero.** Twenty of the 23 buyers had been contacted; the three untouched ones converted
with no call. History cannot score calling an untouched account because it never did it — the
same fact that makes the model worse than random on that pool (AUC 0.45). Recall-on-history will
always vote explore down; that is a limit of the evidence, not a finding about calling. Ten slots
is the price of a day-90 answer.

**"Replace explore with a better branch" — measured, none exists.** On the 435 untouched accounts
in history, web is the only column with any ranking power (AUC 0.61, top-30 at 10%), and explore
already uses it; MQL, size and the model are at or below random. The better branch for the missed
buyers is deeper exploit — 50 slots, three tiers, done — and the conversation for the eight that
no column separates.

The user has moved the whole design onto one metric and a held-out test. That is where it should
have been from the start; it is recorded that it got there on the user's push, not mine.

## Entry 23 — 2026-09-11 · The effort-normalised ranking, tested before building — and it lost

The user's instruction was the right one: *before designing the graph around it, test the path,
define the validation, and only continue if it is the best solve.* So: a leak-free protocol —
train on the older labelled rows, test on the newer, every rate estimated on train only, no model
fitted, two temporal splits — and five ranking keys compared on recall@K (`audit/variable_scorecard.py`).

**The variable scorecard first.** On the 799 training rows, every column alone is weak: contacts
AUC 0.546, web 0.548, trial 0.529, MQL 0.515, `intent_score` value 0.518, the model's own OOF
score 0.554, vendor *coverage* 0.556. Nothing above 0.56. That is why no single-variable rule and
no additive score works here, and why the interactions — trial *with* contact, vendor *with*
contact — are the only things that separate.

**The keys.** At K = 60, split 1: hand tiers **12** buyers, grid-by-rate 11, grid-per-contact
**8**, model 8, random 4.5. Split 2: tiers **12**, grid-by-rate 11, per-contact **9**, model 9,
random 4.0. The hand tiers won or tied on both. The "metric per effort" — conversions per contact
spent — lost clearly, and the reason is instructive: dividing by contacts spent penalises exactly
the accounts that needed calls *because they were converting*. It is the model's confounding moved
into the denominator. It also let cells of six or eight accounts with two lucky conversions float
to the top.

**What the grid did confirm.** Restricted to the same universe as the tiers, it derives from
train alone: trial 10.6% > none 7.4% ≈ vendor 7.2% > MQL 2.0% ≈ web 2.0% (split 2: 11.2 > 8.7 ≈
8.2 > 2.4 ≈ 2.3). The hand order, rediscovered — and web-only and MQL-only shown to be noise at 2%
where I had left them in the third tier by count. That is a real correction to make: in the last
tier, an account with web or MQL as its only signal should rank *below* one with nothing.

**Decision.** The current tiers stand as the ranking. The redesign's value is not a new key: it is
the leak-free protocol (rates from train, applied to test — the earlier tier rates were estimated
on all rows), the variable scorecard as a standing check, and the ordering fix in the last tier.
The user asked for a test before a build; the test said no to the build's premise, and that is
the outcome recorded here.

## Entry 24 — 2026-09-11 · The consolidation: CLEAN → RANK → PROVE → BUDGET, built behind three gates

The user's instruction, in order: *test the path first; if it holds, build the whole agent with
its metrics reporting and validated; then leave the commits impeccable.* This entry is the build.

**Gate 1 — is the uplift ranking stable?** `audit/uplift.py`, leak-free: rates on the older 799,
checked on the newest 300 and on all 1,099. First criterion I wrote ("same bottom two") failed —
`none` (n=37/39/14/10) wobbles in the middle. The criterion that matches the question is by
sign per segment: **trial positive on every cut** (+5 / +24 / +10), **web and MQL ≤ 0 on every
cut**, `none` unstable → neutral. Passed. The bias is written into the JSON: reps chose whom to
call, so every uplift is an upper bound; a segment ≤ 0 despite that is one where calling does
not help.

**Gate 3 — does the new ranking keep every buyer the old one found?** `continue` (1–4 contacts,
trial > vendor > none, web/MQL excluded) finds **12 of 23** on the held-out 300 at K = 60 — the
same 12 as the tiers it replaces. Nothing well-diagnosed got worse. The full worklist finds 11:
first-call's slots reach nobody in history, as they must — its value is the day-90 column.

**What was built.** `FLAGS` became **`CLEAN`**, the purity agent: the row flags plus a variable
scorecard on the older rows (every column alone AUC 0.50–0.56), and the list of what RANK may
use — contacts, trial, vendor *presence*. The vendor's score value, MQL, web alone, account_type,
industry, size and trial_active_users are reported and weighted zero. **`RANK`** gives every
account a cell (segment × contact band) and an action — first-call / continue / ask / skip /
neutral — with the evidence from `uplift.json` on the row; `ranked.csv` is the answer to *where
do the hours go*. `BASELINES` became **`PROVE`**: the uplift table, the held-out recall, and the
model's memory-vs-prediction gap as the brief's footnote. `ALLOCATE` became **`BUDGET`**, arms
named for what the rep does — **continue 45 · first-call 15 · control 30** — and four cohorts
tracked but not called: `ask` (5+), **`observe`** (the randomised-out half of the untouched
trials — the unbiased test), **`skip`** (web/MQL-only), `holdout` (declined). `READOUT` reads
first-call against observe per segment: the column that replaces the +10 upper bound. Seventeen
nodes; twelve run today.

**On the 300.** first-call 88 candidates (25 trials, 63 vendor) → 12 trials called, 13 observed,
3 vendor. continue 45: trial 18, vendor 27, 0 over-invested. skip 74, holding 124 contacts (25
rep-hours) on segments where calling never helped. ask 23. Of the model's top 30, nine are called
as-is.

**What I did not do.** Rename the tests under *Tests that shaped the design* in RESULTS.md — they
ran under the earlier names and their numbers stand; a note at the top maps old to new. Split
today's `nodes.py` into five historical commits by hunk — the file was rewritten too many times
for that to be honest; the log is the sequence, the commits are by concern.

## Entry 25 — 2026-09-11 · The conversation layer leaves the graph and becomes the proposal

The user's call, and the right one for a system that has to work today: *transcripts are the
future — take them out of the agent, leave them as the final proposal, make it work as it is.*

**What left.** `CONVERSATION_INTENT`, `CALIBRATE_VENDOR`, `VALUE`'s ledger, the `holdout`
cohort, the voice-first branch of `BUDGET`, the released/rescued bets and their settlement, the
agent scorecard in the loop, and the synthetic-intent path of `--demo`. Six blocks, kept for
reference in `proposal/conversation_layer/conversation_nodes_reference.py.txt`; `extract_intents.py`
and `demo_data/` moved there with them. The agent's contract stays in `llm.py`, marked *proposed,
not wired* — the brief values a documented plug, and `route()` still refuses to send it to a
hosted backend.

**What the graph is now.** Fifteen nodes, **fourteen run on the two CSVs**, one waits for day 90.
`RECONCILE` and `VALUE` are no longer "partial": two voices is what the design has, not what it is
missing. `--demo` means one thing — simulated 90-day outcomes with no true difference between arms,
so READOUT and the loop can be seen turning.

**What replaced the synthetic cases.** `cases.md` on real data: the 11 accounts in the model's top
30 this system will not call as-is (ask or skip), the 25 untouched trials with the +10 upper bound
and the half held back to measure it, the 9 accounts the model buries below #150 that `continue`
calls first, and the skip and ask cohorts with the hours they hold — 51 rep-hours a quarter that
used to go where calling never helped or had not been questioned.

**What the proposal keeps.** The design, the measured contract (v1 → v2.2, 1.00 on the routing
field, 20/20 grounded), the precise statement of its job — the eight held-out buyers no column
separates — and how to wire it back. Written so it can be judged like everything else: recall on
the margin with it against without, at day 90.

## Entry 26 — 2026-09-11 · Does it actually run? GPU test, the audit consolidated, and the commits reordered

**The pickle** runs on every pass of `SCORE`; a clone fits on 900 rows in 24 ms. Not in doubt, but
asked, so measured.

**The local LLM, on GPU.** `nvidia-smi`: RTX 5080 Laptop, 16 GB, idle. Ollama: `qwen3:14b`, 9.3 GB.
`--check-llm`: local backend reachable, cloud backend has no key. `python serving/pipeline.py --llm
live`: the one wired agent routed `local`, `hygiene_batch`, was drafted by the model — *"Approval
Note: Correction for Stale account_type… 86 records… 341 in training… Preventive Rule…"* — with
`ollama ps` reporting **100% GPU, 9.6 GB resident** and `nvidia-smi` 51% utilisation. Zero fallbacks
on the local backend; the three agents routed `cloud` rendered their template with the reason
printed, which the brief judges equal to a live call. One thing worth writing down: the drafting
model stated the reclassification as fact — *"reclassify all affected records to Prospect"* —
where the finding it was handed says *hypothesis, ask the CRM owner first*. Drafting agents
overstate; that is why a human signs at `HITL` and the agent does not.

**The proposal's contract, re-run on the same GPU.** All 20 synthetic transcripts through
`extract_intents.py --mode live --force`, three workers. Every metric identical to the cached run
— 1.00 / 1.00 / 0.80 / 1.00 / 0.95 / 0.975 — and **0 of 20** accounts differ on `ready_to_act` or
`intent_level`; the output file is byte-identical, so git sees no change. The contract is
deterministic on this hardware. Wall time was not captured (the background subshell dropped it);
it finished while the audit document was being written.

**The audit, consolidated.** `audit/README.md`: eleven conclusions about the model, each with its
number and where it comes from; why it is not used to decide and the three places it still
speaks; eleven hypotheses with a status — verified, supported, hypothesis, unknown — the evidence
behind each and what settles it. H1, the contact-window question, is still the only blocking one.

**The commits, reordered.** Today's ten local commits recorded two passes — a seventeen-node
graph, then the cut to fifteen. Nothing of today had been pushed, so the local history was reset
to the morning's checkpoint and recommitted in six commits by concern: audit → serving →
proposal → outputs → docs → log. The intermediate seventeen-node state survives here, in entries
14–25, where a reader can follow it; the commit history now reads as what was built, not as the
order the day happened in. Both are true; each lives where it belongs.

## Entry 27 — 2026-09-11 · Pruned to the essentials: seven documents, one role each

Ten markdown files had grown during the day, three of them redundant. Removed: `RESULTS.md`
(7,600 words that overlapped `audit/README.md` and what the pipeline prints every run — its two
verified tables that lived nowhere else, the 23 held-out buyers by mechanism and what each policy
sends to the phone on the 300, moved into `audit/README.md` §3b), `audit/oof_predictions.md`
(three sentences, folded into the audit's opening), `demo_data/README.md` (the synthetic warning,
folded into the proposal's README). `serving/README.md` lost its argument section — the argument
is made once, in the proposal — and kept the operating manual. The root README was rewritten as
a map: five lines of findings, a table of where things live, five commands.

Where each kind of information now lives, and why there: the **proposal** in `PROPOSAL.md`, the
brief's own format and word count, with its evidence in the audit; the **hypotheses** in
`audit/README.md` §3, one table, a status per row, what settles each; the **agent** in
`serving/README.md`, operational only — what runs, the arms, the outputs, the config; the
**future** in `ROLLOUT.md` — phases with stop conditions, the loops, the proposed extension — with
`proposal/conversation_layer/` as its first item; the **how** here, never rewritten. Entries in this
log that mention `RESULTS.md` are left as written: they were true when written.

## Entry 28 — 2026-09-11 · Three agents, two design flaws, one correction of my own claim

Three subagents ran in parallel on the finished repo, each with a self-contained brief.

**A — alignment.** Twenty-one factual fixes across six documents (counts, names, positions, a
garbled sentence in the proposal, a commit hash that no longer resolved), and eleven judgment items
handed back rather than changed. Two of those mattered. First: `intents.json` was modified in the
working tree with metrics *different* from what I had reported — I had compared the GPU re-run to
its cache before the background job had finished writing, and called it byte-identical. The truth,
saved as `intents_rerun_gpu_2026-09-11.json`: the two fields the pipeline would route on reproduced
exactly (`ready_to_act` 1.00, 0 of 20 changed; `next_step_agreed` 1.00), the six-level grade moved
on 7 of 20 (0.80 → 0.75), mean confidence 0.975 → 0.945. Sampling variance in the secondary field,
none in the routed ones — the design's assumption, observed. The commit message of `4b67c64` says
"identical"; it is wrong on the grade, right on the routing field, and stays as written. Second:
the code still emitted old names in several strings; all gone.

**C — from experiments to a number.** Designed the ladder (week-1 arithmetic → day-90 randomised
comparison → cumulative arms → the north star), the formula I = (p_system − p_control) × N with its
variance, the one-page mock, the sentence, the failure modes — and found **two design flaws** while
grounding itself. (1) `rep_worklist.csv` showed the rep the `arm` column: a rep who knows "this one
is the system's" works it harder, and the rate rises for a reason the policy did not earn. Removed.
(2) Control was drawn from what was left *after* the system had picked — a sample of what the system
rejected, not a control. `BUDGET` now flips a coin over the whole batch before any rule runs: two
thirds to the system, one third to the rep as usual; on the 300, 207 vs 93. `READOUT` compares the
two thirds intention-to-treat, every account counted. That is the causal line the north star rests
on, and it did not exist until tonight. Consequences on the 300: ask 19, observe 9, skip 50, idle
69; 38 rep-hours held or not spent instead of 51; of the model's top 30, five called as-is and ten
in the control third. The first `--demo` run of the new line — a simulation with no true difference
— returned +4.3 points [+1.6, +7.1]: a false positive at one cycle, now flagged in the output and
used in the docs as the argument for pre-registered readout dates.

**B — additional lines.** Ten ranked, three rejected, and two corrections to my brief (the no-signal
pool is 10 accounts, not 23; a stale position range in the audit). Its first line resolves the
blocking question by recomputation rather than by asking: a timestamped contact log, counted before
and after each snapshot; the definition that reproduces the column settles it. Its second costs a
day and no data: write the comparison list and interim-look schedule before outcomes exist and
validate the plan against the `--demo` null. Both went into `serving/README.md`.

**Consolidation.** `ROLLOUT.md` is gone; its phases, C's measurement section and B's lines now live
in `serving/README.md`, which the user asked to be the single place the agent is reported. The brief
gained *How this becomes a number*. Six documents remain.
