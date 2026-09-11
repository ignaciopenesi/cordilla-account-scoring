# Cordilla — week of 2026-08-01

_No ranked call list, no probability on any account. The audit found this model's ranking indistinguishable from noise; it is used only where it disagrees with something else._

## The scorecard — the graph against three baselines

| | the list it says to call | historical, real outcomes — of the 90 called, how many convert · of the buyers, how many found | prospective, day 90 | rep-hours it refuses to spend |
|---|---|---|---|---|
| model alone — the dashboard the VP asked for | top 90 by score | **6.7%** [3%, 14%] · finds **8%** of buyers · *from memory: 31.1%* | _not yet — READOUT_ | 0 — calls everything it ranks |
| random — no system | 90 at random | **7.3%** 5–95%: [3%, 11%] · finds **8%** of buyers | _not yet — READOUT_ | 0 — calls everything it ranks |
| the team today — rep's own picks | accounts the team chose to work | **8.3%** [6%, 11%] | _not yet — READOUT_ | 0 — calls everything it ranks |
| **THE GRAPH — its worklist** | continue 45 + first-call 15 · ask, observe and skip tracked, not called | **12.2%** [7%, 21%] · finds **14%** of buyers | _not yet — READOUT_ | **51 h / quarter** |
| the graph — confident picks only | continue alone | **15.6%** [9%, 24%] · finds **18%** of buyers | _not yet — READOUT_ | — |

_Historical: each policy builds its list from the 1,099 labelled training rows with a closed 90-day window, and we count who converted — observational, the comparison is fair, the levels are not causal. Prospective: the arms READOUT assigns today, read at day 90 against control — causal, and not readable before ~2,500 per arm. The graph must beat the first three rows on both columns, or it is retired._

## This week's verdict

Run of 2026-08-01. Every feature is stable against training (max PSI 0.06); snapshot age is not — but that is how the batch was drawn, not drift. The top 30 shares 21 of 30 accounts with last week's list even though no underlying data changed, which is the model's own seed, not the market. Only 7 of the top 30 carry no flags at all. The model expects 19.7 conversions across 300 accounts (6.6%) against a field rate the business reports at 1–3%. Recommendation this week: run the exploit arm off sales_contacts, not off the score, and do not publish the probabilities.

## What changed this week

**88 first-call candidates** — never contacted, trial or vendor record; 15 called this week, 13 held back at random so day 90 can measure what the first call does.

**105 in conversation** — 1–4 contacts, trial > vendor > none; 45 on this week's list, none over-invested.

**23 asked, not called** — 5+ contacts, no result: 133 contacts (**27 rep-hours**) held pending one question to the rep.

**74 skipped** — web-only or MQL-only, where calling never helped on any cut: 124 contacts (**25 rep-hours**) not spent again.

Every account, by position and rule, in `ranked.csv`. Named cases in `cases.md`.

## The model's top 30, and what happens to each here

| the model's top 30 | count |
|---|---|
| pool — not drawn this cycle | **9** |
| ask, don't call — 5+ contacts, no result, no voice | **9** |
| exploit — called | **9** |
| explore — never contacted, has signal | **2** |
| control — rep's pick | **1** |

**Of the 30 the model says to call, 9 are called as-is.** Every other verdict is a flag or a cohort the row itself shows.

| rank | account | score | contacts | age | flags | here |
|---|---|---|---|---|---|---|
| #1 | `ACC-01491` | 20.9% | 5 | 290d | stale 180, over invested | ask, don't call — 5+ contacts, no result, no voice |
| #2 | `ACC-00371` | 20.4% | 2 | 256d | stale 180 | exploit — called |
| #3 | `ACC-01064` | 18.7% | 5 | 94d | over invested | ask, don't call — 5+ contacts, no result, no voice |
| #4 | `ACC-01283` | 17.6% | 4 | 122d | — | exploit — called |
| #5 | `ACC-01111` | 15.3% | 3 | 109d | — | exploit — called |
| #6 | `ACC-00400` | 15.2% | 4 | 86d | — | exploit — called |
| #7 | `ACC-00122` | 14.8% | 6 | 38d | no vendor record, over invested | pool — not drawn this cycle |
| #8 | `ACC-00646` | 14.8% | 6 | 272d | no vendor record, stale 180, over invested | pool — not drawn this cycle |
| #9 | `ACC-00657` | 14.4% | 0 | 305d | stale 180, never touched | control — rep's pick |

## Where the metric stands

| | |
|---|---|
| **North star** · conversions per 100 contacts, by arm | **not readable** · 15/2,515 per arm · 168 weeks at this pace, two quarters at 97/arm |
| **Weekly headline** · rep-hours redirected | **51 rep-hours** held or not spent this week — observable on the row; whether they convert better elsewhere is the bet |
| **Bets** | 1 open · 0 settled · first cycle |
| **Price of a conversion today** | 24.6 contacts · 4.9 rep-hours |
| **Arms this cycle** | continue 45 · first-call 15 · control 30 · cohorts ask 23 · observe 13 · skip 74 |

## On real outcomes — each policy's list of 90, and how many converted

_1099 labelled training rows with a closed 90-day window · base rate 7.1% · observational — every policy is judged on accounts someone already chose to work this way._

| who builds the list of 90 | converted | rate | 95% CI | lift | contacts already sunk | rep-hours sunk |
|---|---|---|---|---|---|---|
| model — in-sample (what a dashboard shows) | 28 | 31.1% | [22%, 41%] | 4.38× | 295 | 59.0 |
| **model — out-of-fold (what it actually knows)** | 6 | **6.7%** | [3%, 14%] | 0.94× | 304 | 60.8 |
| graph continue (1-4 contacts: trial > vendor > none) | 14 | 15.6% | [9%, 24%] | 2.19× | 234 | 46.8 |
| graph first-call (untouched trial, then vendor) | 4 | 4.4% | [2%, 11%] | 0.63× | 0 | 0.0 |
| **graph worklist (continue 75 + first-call 15)** | 11 | **12.2%** | [7%, 21%] | 1.72× | 213 | 42.6 |
| old exploit (ORDER BY contacts, all) | 12 | 13.3% | [8%, 22%] | 1.88× | 486 | 97.2 |
| ask cohort, if called anyway (5+ contacts) | 12 | 14.6% | [9%, 24%] | 2.06× | 454 | 90.8 |
| random (mean of 200 draws) | 6.6 | 7.3% | 5–95%: [3%, 11%] | 1.03× | 146 | 29.2 |

**The model from memory: 31.1%. The model on rows it never saw: 6.7%.** The first is what a dashboard would show; the second is what it knows.

## The prediction test — 300 accounts none of the methods saw

_Test: the 300 most recent labelled accounts (2026-01-08 → 2026-05-03), 23 converted (7.7%). Train: the 799 before them. Fits performed: 0 — the model's score is its out-of-fold prediction._

**K = 30**

| who builds the list | converted | precision | 95% CI | recall | contacts sunk |
|---|---|---|---|---|---|
| model — the pickle scoring rows it was trained on (memory) | 10 | 33.3% | [19%, 51%] | 43% | 107 |
| model — out-of-fold (prediction) | 3 | 10.0% | [3%, 26%] | 13% | 116 |
| **continue alone (1–4 contacts: trial > vendor > none)** | 7 | **23.3%** | [12%, 41%] | 30% | 71 |
| first-call alone (untouched trial, then vendor) | 1 | 3.3% | [1%, 17%] | 4% | 0 |
| **THE GRAPH — continue 5/6 + first-call 1/6, ask and skip excluded** | 6 | **20.0%** | [10%, 37%] | 26% | 66 |
| continue ∪ model picks (half each) — does the model add anything? | 5 | 16.7% | [7%, 34%] | 22% | 105 |
| ask cohort, if called anyway (5+ contacts) | 4 | 17.4% | [7%, 37%] | 17% | 133 |
| random (mean of 200 draws) | 2.3 | 7.8% | 5–95%: [0%, 17%] | 10% | 50 |
| the team today — every account it chose to work | 20 | 10.9% | [7%, 16%] | 87% | 497 |
| the graph WITH the conversation agent | — | — | needs call transcripts on accounts with a known outcome — none exist; ROLLOUT phase 3 | — | — |

**K = 60**

| who builds the list | converted | precision | 95% CI | recall | contacts sunk |
|---|---|---|---|---|---|
| model — the pickle scoring rows it was trained on (memory) | 15 | 25.0% | [16%, 37%] | 65% | 194 |
| model — out-of-fold (prediction) | 8 | 13.3% | [7%, 24%] | 35% | 193 |
| **continue alone (1–4 contacts: trial > vendor > none)** | 12 | **20.0%** | [12%, 32%] | 52% | 165 |
| first-call alone (untouched trial, then vendor) | 1 | 1.7% | [0%, 9%] | 4% | 0 |
| **THE GRAPH — continue 5/6 + first-call 1/6, ask and skip excluded** | 11 | **18.3%** | [11%, 30%] | 48% | 135 |
| continue ∪ model picks (half each) — does the model add anything? | 10 | 16.7% | [9%, 28%] | 43% | 189 |
| ask cohort, if called anyway (5+ contacts) | 4 | 17.4% | [7%, 37%] | 17% | 133 |
| random (mean of 200 draws) | 4.6 | 7.6% | 5–95%: [3%, 13%] | 20% | 99 |
| the team today — every account it chose to work | 20 | 10.9% | [7%, 16%] | 87% | 497 |
| the graph WITH the conversation agent | — | — | needs call transcripts on accounts with a known outcome — none exist; ROLLOUT phase 3 | — | — |

**What this test can judge:** the model against the rules — exploit beats the model's honest score about 2×, and adding the model's picks to exploit removes conversions. **What it cannot judge:** explore and the agent. Both pick accounts history never called; their historical rate is *what happens when nobody calls*, which is the question the arms exist to answer. Reading explore's row as its value would be the same confounding error in reverse.

_The weekly number is filed as a bet with its falsifier; it cannot be read as a result. Detail, guardrails and the kill switch in `metrics.md`._

## This week's allocation — the experiment you are approving

**This week: 90 accounts — continue 45, first-call 15, control 30 — plus a holdout nobody calls.**

**continue (45)** — Hypothesis: the best information we hold — a prospect who stated readiness, then 1–4 logged contacts with a trial, then with a vendor record, then by count — beats the model's score. Confirms: converts at or above control. Kills: converts below control once both arms pass 2,500 accounts.

**first-call (15)** — Hypothesis: the first call on an untouched trial account is where an hour changes most (+10 pts on history, an upper bound). Half are called, half observed. Confirms: called converts above observed. Kills: no difference at 138 per group.

**control (30)** — The rep picks. This is what happens without the system, and it is the only reason either arm above can be read.

**ask** — 5+ contacts, no result, no conversation on file. The rep gets one question, not a call: what do you know that the data does not? Their answer decides whether the account rests or returns.

**holdout** — Prospects who said no after 4+ contacts and agreed to no next step. Nobody calls them. If they convert anyway, the extractor misread them.

First readout 2026-10-30. It will be noisy — 30 per arm cannot resolve a realistic difference — and it accumulates. The control arm exists because Cordilla has never had one, which is why nobody could write up how the last scoring effort died.

## Actions awaiting your signature

| severity | owner | what | action |
|---|---|---|---|
| blocking | pipeline | It is unknown whether sales_contacts_90d precedes the outcome window or overlaps it | One question to the data owner: does the contact window PRECEDE the snapshot, or is it the same 90 days in which conversion is measured? If it overlaps, the one signal in this dataset is leakage and nothing built on it is real. |
| high | crm | Accounts are being scored on information older than the feature window | Flag it on the row, do not block it — working hypothesis: still actionable. READOUT compares stale vs fresh conversion within each arm; if stale loses, the flag becomes a filter. |
| high | crm | account_type carries no information — and if 'Suspect' means 'no engagement', it is wrong on 85% of rows | First, one question to the CRM owner: what is 'Suspect' supposed to mean? If 'no engagement': bulk-reclassify the 86 scoring accounts and add a validation rule. If something else: document it, because today the field predicts nothing. |
| high | model | The model's own arithmetic promises more conversions than the business sees | Do not publish probabilities to any user or Salesforce field. Use the score only for the disagreement analysis in RECONCILE. |
| high | model | The model's dashboard number is memory, not prediction | Never show an in-sample rate to anyone. Every number about this model that reaches a manager comes from out-of-fold or forward-in-time scoring, and says which. |
| high | model | The model's ranking has never been validated out of sample in production | Re-run the permutation null and the forward-chaining split (audit §2.2, §2.6a) whenever the model or the data pipeline changes. No metric gets reported without a temporal split — that is how the last one shipped. |
| high | pipeline | Training labels are assigned before the 90-day window closes | Label = NULL, not 0, when snapshot_date + 90d > today. Re-label the 101 affected rows and add the rule to the labeling job. |
| high | process | Conversions per hour cannot be estimated from this data at all — only randomised | Do not compute or report conversions-per-hour from historical CRM data, in any cut. The arms in BUDGET are the measuring instrument, not a side experiment: randomised assignment is the only thing that makes the denominator readable. |
| high | process | At today's allocation the primary metric never becomes readable | Assign the whole batch, not a third of it: 97 accounts per arm per cycle (291 of the 300) makes the readout land in two quarters. If the manager will not commit that volume, say so now and report only the weekly bets — do not promise a lift number that the design cannot deliver. |
| medium | pipeline | Trials with zero active users are ambiguous | Ask product whether these are provisioned-but-never-used or missing seat telemetry. If telemetry, instrument it — the field is currently unreadable. |
| medium | vendor | web_touchpoints_90d cannot distinguish 'no visits' from 'not measured' | Data contract with the attribution vendor: return NULL when no measurement was taken. Until then, treat 0 as unknown rather than as a measured zero. |

## Not running today

| node | reason | unblocked_by |
|---|---|---|

## Proposed, not wired — the conversation layer

The one input that is not a function of Cordilla's own effort is what the prospect said on the call. A layer that extracts it is designed, measured on synthetic transcripts (1.00 on the routing field, quotes grounded 20/20) and deliberately kept out of this graph until real transcripts with outcomes exist. It would work the margin — the accounts no column separates. See `proposal/conversation_layer/`.

---

## Appendix — the agents, as rendered

_Every prompt, verbatim, with the worked example that stands in for a live call. For the reviewer; the manager stops at the line above._

### run_verdict

```
┌──────────────────────────────────────────────────────────────────────────
│ AGENT · run_verdict   [template]
│ purpose     : Say whether this week's run is worth trusting, and recommend what to do about it
│ sensitivity : aggregate
│ routed to   : cloud
│ reads       : PSI table, overlap with previous run, score concentration, flags in top K, sum of probabilities vs the field rate
│ returns     : one paragraph, under 120 words
├─ SYSTEM ─────────────────────────────────────────────────────────────────
│ You write a weekly one-paragraph verdict on whether a scoring run is
│ worth trusting. You are allowed — expected — to say it is not. End with
│ a concrete recommendation for THIS week, not a general observation.
├─ PROMPT ─────────────────────────────────────────────────────────────────
│ Run of 2026-08-01. every feature is stable against training (max PSI 0.06, intent_score). Overlap of the top 30 with the previous run:
│ 30/30. the model's top-30 shares only 11/30 accounts with a plain sort by contact count. Of the top 30, 7 carry no flags. The model's predicted
│ probabilities sum to 19.7 expected conversions across 300 accounts (6.6%), against a
│ field rate the business reports at 1-3%.
│ 
│ Write the manager's paragraph. End with one concrete recommendation for this week.
├─ RETURNS (worked example) ───────────────────────────────────────────────
│ Run of 2026-08-01. Every feature is stable against training (max PSI 0.06); snapshot age is not — but that is how the batch was drawn, not drift. The top 30 shares 21 of 30 accounts with last week's list even though no underlying data changed, which is the model's own seed, not the market. Only 7 of the top 30 carry no flags at all. The model expects 19.7 conversions across 300 accounts (6.6%) against a field rate the business reports at 1–3%. Recommendation this week: run the exploit arm off sales_contacts, not off the score, and do not publish the probabilities.
└──────────────────────────────────────────────────────────────────────────
```

### experiment_card

```
┌──────────────────────────────────────────────────────────────────────────
│ AGENT · experiment_card   [template]
│ purpose     : Write the week's allocation as an experiment the manager can approve or refuse
│ sensitivity : aggregate
│ routed to   : cloud
│ reads       : arms (name, size, selection rule), matching variables, base rate, readout date
│ returns     : markdown, ~150 words
├─ SYSTEM ─────────────────────────────────────────────────────────────────
│ You write experiment cards for an SDR manager who is not technical and
│ is sceptical of being experimented on. Be concrete about what each arm
│ is testing and what result would make us stop. Never oversell, and never
│ promise a lift number we do not have.
├─ PROMPT ─────────────────────────────────────────────────────────────────
│ This week's allocation splits 90 accounts into 3 matched arms
│ (intent segment and contact band). Base rate is 6.5% in training, 1-3% per the business.
│ 
│ - **continue** (45 accounts): 1–4 logged contacts, trial > vendor record > no signal, most contacts first
│ - **first-call** (15 accounts): never contacted, trial first (half called, half observed — that is how the +10 gets measured for real), then vendor record
│ - **control** (30 accounts): the rep picks — what would happen without the system
│ - **ask** (23, not an arm): 5+ contacts, no result — the rep gets a question
│ - **observe** (13, not an arm): the other half of the untouched trials, deliberately not called
│ - **skip** (74, not an arm): web-only or MQL-only — calling never helped on any cut
│ 
│ Write the experiment card the SDR manager reads before approving. For each arm state the
│ hypothesis in one sentence, the result that would confirm it, and the result that would
│ kill it. End with the readout date and one sentence on why the control arm exists.
├─ RETURNS (worked example) ───────────────────────────────────────────────
│ **This week: 90 accounts — continue 45, first-call 15, control 30 — plus a holdout nobody calls.**
│ 
│ **continue (45)** — Hypothesis: the best information we hold — a prospect who stated readiness, then 1–4 logged contacts with a trial, then with a vendor record, then by count — beats the model's score. Confirms: converts at or above control. Kills: converts below control once both arms pass 2,500 accounts.
│ 
│ **first-call (15)** — Hypothesis: the first call on an untouched trial account is where an hour changes most (+10 pts on history, an upper bound). Half are called, half observed. Confirms: called converts above observed. Kills: no difference at 138 per group.
│ 
│ **control (30)** — The rep picks. This is what happens without the system, and it is the only reason either arm above can be read.
│ 
│ **ask** — 5+ contacts, no result, no conversation on file. The rep gets one question, not a call: what do you know that the data does not? Their answer decides whether the account rests or returns.
│ 
│ **holdout** — Prospects who said no after 4+ contacts and agreed to no next step. Nobody calls them. If they convert anyway, the extractor misread them.
│ 
│ First readout 2026-10-30. It will be noisy — 30 per arm cannot resolve a realistic difference — and it accumulates. The control arm exists because Cordilla has never had one, which is why nobody could write up how the last scoring effort died.
└──────────────────────────────────────────────────────────────────────────
```