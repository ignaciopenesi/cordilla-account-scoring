# Cordilla account scoring — what I found, and what I would ship instead

## 1. Problem framing

The VP asked for a dashboard. That is a solution, so I started with the decision under it. **Who
decides:** the SDR manager allocates contact hours weekly; the rep decides who to call today.
**The decision:** which of tens of thousands of untouched accounts get the next hour. Hours are the
scarce resource, so I priced one: **1,915 logged contacts bought 78 conversions — 24.6 contacts,
about five rep-hours, each.** In the batch I was handed, **52 of 300 accounts hold 260 of 481
contacts**: 54% of the effort on 17% of the accounts.

Optimising that ratio directly is a trap: the same curve says *call more* read as a rate and *never
call twice* read as a cost — because reps keep dialling accounts that go well and drop the dead. **No observational cut of this
data yields conversions-per-hour.** That is why the arms in §3 are the instrument, not a side
experiment: it is the model's own error, one level up.

## 2. Model audit

`clone(model).fit()` over all 1,200 rows in file order reproduces the pickle bit-for-bit
(`audit/` §0.4): no holdout, so every metric ever computed on it was in-sample.

**The headline is noise.** In-sample AUC is 0.759 — and the identical architecture fitted to
randomly permuted labels 200 times has a median of **0.762** (p = 0.575). Out-of-fold it scores
0.573 ± 0.024; refit forward in time, the only regime production sees, **0.474 — below chance**,
against **0.608** for `ORDER BY sales_contacts_90d DESC`. Fine shuffled, inverted in time: the brief's
folklore, found inside the pickle. Its list of 90 converts at **31% scored from memory and 6.7%
out-of-fold** — random is 7.3%. The first number is the dashboard; the second is the field.

**Its importances point the wrong way.** Importance tracks cardinality (Spearman +0.77), not signal: a pure-noise column in `intent_score`'s slot earns 75% of its importance. Only its *missingness* carries anything (+0.028
AUC) — median imputation put 482 rows on one value and the trees found it.

**The structural finding.** No feature survives multiple-testing correction (78 positives), and the
two with credible signal — `sales_contacts_90d` (OR 2.2 at ≥4) and `intent_known` — both measure
what Cordilla already did to the account. Remove them and it scores 0.434: these nine columns hold
no account-intrinsic signal.

**What I would trust:** `sales_contacts ≥ 4` as a weak population signal — *conditional on the data
owner confirming the contact window precedes the outcome window*, which nothing states and which
decides whether it is real or leakage. **Ship the scores?** No. Give me a holdout it never saw and let it beat that one-line sort.

## 3. AI-assisted serving design

If the data measures Cordilla rather than the account, a better model cannot help. What can is a
system that **produces the missing data while it runs** — a control group, the rep's knowledge, the
prospect's own words. `serving/` is a graph of fifteen nodes with one human approval before any
write. **Eleven run on the two CSVs in four seconds**; the rest are **declared bypassed with what
unblocks them**, not stubbed.

**The model is one voice of three, never the decision.** `RECONCILE` compares the score, our
logged effort, and what the prospect said. Agreement teaches nothing; **disagreement is the new
data** — 24 ranked high that nobody contacted, 22 absorbing effort with no result,
9 the rep works anyway. `RANK` then places every account by **where the next hour changes most**: for each intent segment, conversion with 1–4 contacts minus conversion with none, estimated on the older rows only. Trial is +10 points on every cut (an upper bound — reps chose whom to call); web-only and MQL-only are ≤ 0 and never called. `BUDGET` cuts at the budget into **continue**, **first-call** and the rep's **control**, and splits the untouched trials at random — half called, half observed — so day 90 measures the +10 unbiased. **Of the model's top 30, nine are called as-is.**6%). **Of the model's top 30, six are called as-is; eleven are asked first.**

**Conversation completes the intent vendor, it does not replace it.** Vendor *coverage* predicts conversion (8.22% vs 3.94%); its *score* does not. **197 of 481 logged contacts (41%) are with accounts the vendor never covered.** A conversation layer — the one input not a function of Cordilla's own effort — is designed, measured on synthetic transcripts (**1.00 on `ready_to_act`**) and **deliberately not wired** until real transcripts with outcomes exist.

**`VALUE` prices the result in hours and counts only decisions it changed.** With transcripts the score is
**inverted** — 6.9% mean for those that said *no*, 5.5% for *yes* — because dead accounts absorbed more contacts, its strongest feature. One said *"we just renewed with
our current vendor for three years, take us off your list"* and scores above the median. Agreement is logged at **zero value on purpose**: a correct score that changes no decision buys nothing. At full transcript
coverage that is ≈41 rep-hours a cycle, labelled as the extrapolation it is.

## 4. Productionization, trust, and the metric

**The rep never sees a score** — only flags: *no vendor record · snapshot 240 days old · 6 contacts,
no result*. An unexplained individual error kills adoption in weeks. Findings carry an owner, a cost, an action.

**The metric is two numbers, and the hierarchy between them is structural rather than
typographic.** The north star is **conversions per 100 contacts, by arm, read cumulatively** — the
only thing that proves the system works, and it is not readable yet:
detecting a 50% relative lift at the field rate needs **2,515 accounts per arm**, which at today's
30-per-arm cycle is **84 weeks**. Assigning the whole batch
instead of a third (97 per arm) lands it in two quarters at no extra rep-hours: taking the metric
seriously changed the allocation.

The weekly headline is **rep-hours redirected off accounts that stated a decline**, filed as a
**bet** carrying the date it settles and the result that falsifies it — so it cannot be read as an
outcome. Day 90 marks each won, lost, or *underpowered*: zero conversions needs n ≥ 99 to mean
anything at a 3% base rate, and this cycle returns `UNDERPOWERED 0/2` rather than a win. The stock
is declared decaying — 789 contacts of historical waste is spent once, so a falling number is the
system working, not dying. And **proxy validity** is scheduled: if redirected hours stop predicting
conversions, the weekly metric is retired in the same report. Nobody ever wrote up why the last
scores stopped matching the field; this is that writeup, scheduled before it is needed. Three
gated loops in `READOUT` read the accumulated cycles — arm sizes move only once intervals
separate, never below a 20% floor; the agent's real precision replaces its synthetic score;
the weekly metric retires if it stops tracking the north star (`ROLLOUT.md`).

**Salesforce or outside.** Inside wins adoption and loses trust; outside wins control and loses use.
So **hybrid, conditioned on validation**: flags, `intent_known` and the snapshot date become fields
carrying a date; the probability never does. Transcripts are personal data, so extraction runs
locally — `route()` refuses to send a PII-bearing agent to a hosted backend. **What has not been
validated does not enter the system of record.**
