# Cordilla account scoring — what I found, and what I would ship instead

## 1. Problem framing

The VP asked for a dashboard. That is a solution, not a problem, so I started with the
decision underneath it. **Who decides:** the SDR manager allocates the team's contact
hours each week; the rep decides who to call today. **What the decision is:** which of
tens of thousands of untouched accounts get the next hour — the scarce resource is hours,
not accounts. **What would tell us it is working:** more conversions per logged contact on
accounts the system directed than on accounts the rep chose alone, measured against a
control group. **What would tell us it is noise everyone trusts by default:** the team
works the list and the rate does not move — or moves only because the score climbs when
they call. Cordilla has never had a control — which is why nobody could write up how the last
model died. So the objective is two-fold: more conversions per hour, and knowing whether
the tool helps *before* reps stop believing it.

## 2. Model audit

The pickle reproduces bit-for-bit from `clone(model).fit()` over all 1,200 rows in file
order (`audit/` §0.4): it was fit with no holdout, so every metric anyone computed on it
was in-sample.

**The headline is noise.** In-sample AUC is 0.759. Fit the identical architecture to
randomly permuted labels 200 times and the median in-sample AUC is **0.762** (p = 0.575).
Out-of-fold it scores 0.573 ± 0.024; refit forward in time, quarter by quarter — the only
regime production ever sees — **0.474, below chance**. `ORDER BY sales_contacts_90d DESC` scores 0.608 on the same rows. Brier and
log-loss are worse than printing 6.5% on every account. Fine under a shuffled split, inverted under a
temporal one: that is the brief's folklore, found inside the pickle.

**Its importances point the wrong way.** Feature importance tracks column cardinality
(Spearman +0.77, p = 0.04), not signal; a pure-noise column in `intent_score`'s slot earns
75% of its importance. `intent_score`'s *values* contribute −0.001 ± 0.004 AUC (paired,
25 repeats); only its *missingness* contributes (+0.028, t = 6.6). Median imputation put
482 rows on the single value 25.3 and seven of the model's 31 intent splits sit inside
(24.0, 26.6]: it built a missingness flag by accident and learned nothing else. Where the
vendor did score, conversion is flat across intent quintiles (p = 0.42).

**The structural finding.** No feature survives multiple-testing correction (78
positives). The two with any credible signal — `sales_contacts_90d` (OR 2.2 at ≥4,
robust to every adjustment) and `intent_known` — both measure what Cordilla already did
to the account, not what the account is. Remove them and the model scores 0.434. These
nine columns contain no account-intrinsic signal. Also: the random seed alone replaces a
third of the top-30; a null `account_type` crashes the batch; 101 labels are censored;
341 of 402 training "Suspects" show activity; and the model expects 19.7 conversions in
300 accounts against a field rate of 1–3%.

**What I would trust:** the data are clean; the defects are concrete and fixable;
`sales_contacts ≥ 4` is a weak population signal — *conditional on the data owner
confirming the contact window precedes the outcome window*, which nothing in the files
states and which decides whether the one signal is real or leakage. **Would I ship the scores?** No — not as probabilities and
not as a ranking, since a one-line sort beats them where it counts. The falsifiable
version: give me a holdout the model never saw and let it beat that sort.

## 3. AI-assisted serving design

If the data measures Cordilla rather than the account, a better model cannot help. What
can is a system that **produces the missing data while it runs** — a control group, the
rep's knowledge, the prospect's own words. `serving/` is a stateful graph: one
typed state passed node to node, one human approval before anything writes to Salesforce,
the LLM drafting only what a human must read.

`INGEST → VALIDATE → SCORE → {BASELINES, FLAGS, CONVERSATION INTENT} → RECONCILE →
{ALLOCATE, HYGIENE, VERDICT} → ⏸ HITL → EMIT → (day 90) READOUT`

**The model is one voice of three, never the decision.** `RECONCILE` compares, per
account, the pickle's score, the rep's effort, and the intent extracted from recorded
calls. Agreement teaches nothing; **disagreement is the new data** — 24 accounts ranked high
that nobody contacted, 9 the rep insists on that the model ranks low.

**`ALLOCATE` is three matched arms, not a list**: *exploit* (the `ORDER BY` rule), *explore*
(130 accounts never contacted, 25 with a live trial), and *rep's choice* as control. It is
the Stitch Fix 90/10 randomisation — the only way to get unbiased outcome data — and it
compares policies rather than ranking accounts. The LLM drafts the experiment card.

**`CONVERSATION INTENT` replaces "ask the rep."** Every logged contact is recorded (with
disclosure, transcript-only storage) and an agent extracts intent level A–F, objections,
next step. The rep already said what they know; the system listens instead of asking. It
is the one account-intrinsic signal available, the central hypothesis the arms test, and
a documented plug today — the CSVs carry no transcripts.

**`HYGIENE`** proposes, never executes: 86 Suspect reclassifications with evidence, 101
label corrections, contract tickets for the zero-vs-unmeasured web field and the blocking
`sales_contacts` window question. **`VERDICT`** runs the permutation null and week-over-week
overlap on every run and writes one paragraph for the manager. **Monday:** the rep works a
third of their accounts from a list they did not pick, sees one line of flags per account,
gets 5–10 two-minute questions; the manager reads one page and signs.

## 4. Productionization and trust

**Why is this account scored this way?** The rep is never shown a score — only flags with
numbers: *no vendor record · snapshot 240 days old · seed-unstable · 6 contacts, no result*.
The literature and the audit agree that an unexplained individual error kills adoption in
weeks. **Trust:** the flags, `intent_known`, the never-contacted set,
`contacts ≥ 4` once the window question is answered. **Double-check:** any account the
model ranks high with no vendor record, anything over 180 days stale, anything in the
top 30 (a third of it is the seed).

**Staying current:** `VERDICT` weekly — distinguishable from noise? how much did the list
move? — and `READOUT` at 90 days, which grows the winning arm but never to 100%, so
exploration keeps detecting when the optimum moves. Sales acceptance rate (65–75%) is
the adoption metric.

**Salesforce or outside it.** Inside wins on adoption, loses on trust: a field becomes
truth, and these probabilities are worse than a constant. Outside wins on control, loses
on use — reps live in Salesforce. So: **hybrid, conditioned on validation.**
Flags, `intent_known` and the snapshot date enter Salesforce as fields with a date. The
probability never does. Questions reach the rep as Salesforce tasks or Slack, in their
flow. The experiment and verdict live in the manager's weekly page. Two facts settle it: a
null `account_type` — Salesforce's least maintained field — crashes the pipeline, so it
cannot run unguarded inside the CRM; and the last model died as a field nobody could
question. What has not been validated does not enter the system of record.

**The first honest number.** Thirty accounts per arm at ~6% gives a noisy first readout;
I say so. What matters is that it accumulates — and that after ninety days Cordilla will
have, for the first time, a measurement against a control.
