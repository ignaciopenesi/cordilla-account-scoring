# Cordilla account scoring — what I found, and what I would ship instead

## 1. Problem framing

The VP asked for a dashboard. That is a solution, so I started with the decision under it.
**Who decides:** the SDR manager allocates contact hours weekly; the rep decides who to call
today. **The decision:** which of tens of thousands of untouched accounts get the next hour
— the scarce resource is hours. **What would say it works:** more conversions per logged
contact on accounts the system directed than on ones the rep chose alone, against a control.
**What would say it is noise trusted by default:** the team works the list and the rate does
not move, or moves only because the score climbs when they call. Cordilla has never had a
control, which is why nobody could write up how the last model died. So: more conversions
per hour, *and* knowing whether it helps before reps stop believing it.

## 2. Model audit

`clone(model).fit()` over all 1,200 rows in file order reproduces the pickle bit-for-bit
(`audit/` §0.4): it was fit with no holdout, so every metric anyone computed was in-sample.

**The headline is noise.** In-sample AUC is 0.759 — and the identical architecture fitted to
randomly permuted labels 200 times has a median of **0.762** (p = 0.575). Out-of-fold it
scores 0.573 ± 0.024; refit forward in time, the only regime production sees, **0.474 —
below chance**, against **0.608** for `ORDER BY sales_contacts_90d DESC` on the same rows.
Brier and log-loss are worse than printing 6.5% everywhere. Fine under a shuffled split,
inverted under a temporal one: that is the brief's folklore, found inside the pickle.

**Its importances point the wrong way.** Importance tracks cardinality (Spearman +0.77,
p = 0.04), not signal: a pure-noise column in `intent_score`'s slot earns 75% of its
importance. That column's *values* contribute −0.001 ± 0.004 AUC (paired, 25 repeats); only
its *missingness* does (+0.028, t = 6.6). Median imputation put 482 rows on a single value
and the trees found it — it built a missingness flag by accident and learned nothing else.
Where the vendor did score, conversion is flat across quintiles (p = 0.42).

**The structural finding.** No feature survives multiple-testing correction (78 positives).
The two with credible signal — `sales_contacts_90d` (OR 2.2 at ≥4, robust to every
adjustment) and `intent_known` — both measure what Cordilla already did to the account.
Remove them and it scores 0.434: these nine columns hold no account-intrinsic signal. Also
in `audit/`: the seed alone replaces a third of the top-30, a null `account_type` crashes
the batch, 101 labels are censored, 341 of 402 training "Suspects" show activity, and the
model expects 19.7 conversions in 300 accounts against a field rate of 1–3%.

**What I would trust:** the data are clean, the defects are fixable, and
`sales_contacts ≥ 4` is a weak population signal — *conditional on the data owner confirming
the contact window precedes the outcome window*, which nothing states and which decides
whether that signal is real or leakage. **Ship the scores?** No, and not as a ranking
either. Falsifiable version: give me a holdout it never saw and let it beat that one-line
sort.

## 3. AI-assisted serving design

If the data measures Cordilla rather than the account, a better model cannot help. What can
is a system that **produces the missing data while it runs** — a control group, the rep's
knowledge, the prospect's own words. `serving/` is a stateful graph: one state passed node
to node, one human approval before any write to Salesforce, agents drafting only what a
human reads.

`INGEST → VALIDATE → SCORE → {BASELINES, FLAGS, CONVERSATION_INTENT, CALIBRATE_VENDOR} →
RECONCILE → {ALLOCATE, HYGIENE, VERDICT} → PRESCRIBE → ⏸HITL → EMIT → (day 90) READOUT`

**Eleven of fifteen nodes run on the two CSVs**, in four seconds. The rest need inputs that
do not exist and are **declared bypassed with what would unblock them**, not stubbed;
`--demo` runs all fifteen on labelled synthetic inputs.

**The model is one voice of three, never the decision.** `RECONCILE` compares the score,
our logged effort, and what the prospect said. Agreement teaches nothing; **disagreement is
the new data** — on the real 300: 24 accounts ranked high that nobody contacted, 22
absorbing effort with no result, 9 the rep works anyway.

**Conversation completes the intent vendor, it does not replace it.** Vendor *coverage*
predicts conversion (8.22% vs 3.94%, p = 0.003); the vendor *score* does not (p = 0.42) — it
tells you who is visible, not who wants to buy. The 300 split four ways: **103** where a
vendor record and a call both exist, which is the only way to find out whether the vendor is
any good and something nobody at Cordilla can do today; **67** where the vendor is blind but
a call already happened, fillable now with no new outreach; **81** unverified; **49** blind,
only 10 genuinely cold. And **197 of 481 logged contacts (41%) are with accounts the vendor
never covered** — already generated, and discarded.

**`ALLOCATE` is three matched arms, not a list**: exploit (the `ORDER BY` rule), explore
(130 never contacted, 25 with a live trial), rep's-choice as control. It compares policies
rather than ranking accounts, and the randomisation produces the unbiased outcome data
Cordilla has never had. Neither ruled-out shape appears: no per-account brief, no tier.

## 4. Productionization and trust

**Why is this account scored this way?** The rep never sees a score — only flags with
numbers: *no vendor record · snapshot 240 days old · seed-unstable · 6 contacts, no result*.
An unexplained individual error kills adoption in weeks. **Trust** the flags,
`intent_known`, the never-contacted set. **Double-check** anything ranked high with no
vendor record, anything over 180 days stale, and the top 30 — a third of it is the seed.

**Every finding carries its fix**, including our own. Detectors emit typed findings —
`what · evidence · severity · owner · action · cost` — ranked by owner (crm / vendor /
pipeline / model / process), so the manager approves **actions**, not a report; the real run
surfaces ten, one blocking. That includes the agent we introduce: against 20 transcripts
generated *from* known intent levels, the extractor scores next-step 1.00 and hot-vs-cold
0.80, but **exact level 0.50, speaker role 0.05**. What is *extracted* is reliable; what is
*inferred* is not. So the quote is what a human reads and the level stays a hypothesis until
`READOUT` measures it — shipping an unmeasured instrument is the mistake this audit is
about.

**Staying current** is `VERDICT` weekly and `READOUT` at 90 days, growing the winning arm
but never to 100%. Simulating one cycle with *no* true difference still produces a
3.3-point spread between arms, so the pipeline files that one cycle of 30 per arm resolves
nothing — said before the first readout, not after.

**Salesforce or outside.** Inside wins adoption and loses trust: a field becomes truth, and
these probabilities are worse than a constant. Outside wins control and loses use — reps
live in Salesforce. So **hybrid, conditioned on validation**: flags, `intent_known` and the
snapshot date become fields with a date; the probability never does; questions reach the rep
as tasks or Slack; the experiment lives in the manager's weekly page. Two facts settle it —
a null `account_type`, the least maintained field in the CRM, crashes the pipeline, so it
cannot run unguarded inside it; and the last model died as a field nobody could question.
Transcripts add a third: personal data, so extraction runs locally and never leaves the
network. **What has not been validated does not enter the system of record.**
