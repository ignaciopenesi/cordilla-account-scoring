# Rollout — how this gets into Cordilla's week, and how it learns

Phased, because every phase has a result that would stop the next one. Nothing here needs
a new system: the pipeline runs on the CSVs today, and every phase adds one input it was
already declared to be waiting for (`python serving/pipeline.py --map`).

Reference date is 2026-08-01 throughout. Owners match the `owner` column in `actions.csv`.

| phase | when | what happens | what is measured | owner | stops the next phase if |
|---|---|---|---|---|---|
| **0 · Sign** | week 0 | the manager approves the 12 actions; the **blocking question** to the data owner goes out; recording with per-call disclosure switched on for the **67 fill-gap accounts** (they already receive calls — zero new outreach) | — | manager · pipeline · process | the data owner says `sales_contacts_90d` **overlaps** the outcome window → the one signal is leakage and §1 of the proposal is rewritten before anything ships |
| **1 · First cycles** | weeks 1–4 | weekly run · 3 arms drawn (**continue 45 · first-call 15 · control 30**, or **97 each** if the manager commits the volume) · **the untouched trials are split at random: half called, half `observe`d — this is the unbiased test of the +10** · `ask` gets a question, not a call · `skip` (web/MQL-only) is never called · stale accounts worked with the flag on the row · bets filed · brief + cases + worklist delivered · reps work the worklist | **rep acceptance** of the worklist (guardrail ≥ 65%) · **answers to `ask` questions** (the first real signal on over-invested accounts) · contacts logged against `holdout` accounts (must not rise) · stale accounts entering arms (must stay 0) | manager · reps | acceptance under 65% for two consecutive weeks → the worklist format changes before the arms continue; adoption failed the last effort before any metric moved |
| **2 · First readout of the untouched trials** | weeks 6–13 | first-call vs observe accumulates per segment · the ask cohort's answers return accounts to `continue` or to rest | the first unbiased uplift numbers, n small · ask answer rate | process · manager | ask answers under 50% → the question format changes |
| **3 · First settlement** | day 90 · 2026-10-30 | `READOUT` runs on real outcomes · bets marked **won / lost / underpowered** · `cycles.jsonl` gets its first real line  | released → converted anyway? · rescued → converted? · both against the 3% base, both **pending until n ≥ 99** | pipeline | any released account converts → the release was wrong on that account, and the contract goes back to revision by the method that took it v1→v2.2 |
| **4 · The loop turns** | weeks 13–26 | cycles accumulate · allocation update **holds** until every arm passes n = 99 and intervals separate · first **proxy-validity** check: does rep-hours-redirected still track conversions/100 contacts? | cumulative conversions/100 contacts by arm with intervals · proxy validity · floor per arm never breached | pipeline · manager | proxy validity fails → the weekly headline is **retired in the same report**, and the brief carries only the north star until it is readable |
| **5 · The uplift column reads** | quarter 2 · at 97/arm, ~138 per group in first-call vs observe | ~2,500 accounts per arm · the first number that proves the hours went to a better place — or did not | **conversions per 100 contacts, explore vs control**, cumulative, with intervals | manager · VP | explore sits below control with separated intervals → **kill switch**: the system stops directing hours. Reported, not buried. |

## What changes automatically, and on what evidence

Three loops run inside `READOUT`. Each is gated, and each gate is a number in the code.

| loop | learns from | changes | gate | where |
|---|---|---|---|---|
| **allocation** | cumulative conversions by arm, `cycles.jsonl` | arm sizes for the next cycle, ±5 accounts, **floor 10% per arm** — first-call never reaches zero | every arm n ≥ 99 **and** the best arm's lower bound clears the worst arm's upper bound | `_learn()` → `next_cycle.json` → `ALLOCATE` |
| **uplift** | first-call (called) vs observe (not called), per segment, cumulative | replaces the audit's upper bound with the real effect of a call; a segment whose real uplift is ≤ 0 leaves first-call | ~138 per group at 5% → 15% | `READOUT` → `uplift_day90` |
| **metric** | the weekly headline against the north star, across cycles | retires the weekly headline if it stops predicting conversions | needs the same n as the north star | `_learn()` → `proxy_validity` |

Two things do **not** change automatically, on purpose: the model is never retrained (the
brief forbids it, and out of sample it loses to `ORDER BY sales_contacts_90d`), and nothing
reaches Salesforce without the `HITL` signature. Automation here means *the evidence
accumulates and the rules read it* — not that the system acts without a human.

## What the manager sees each week

`manager_brief.md` (3 minutes) → **`ranked.csv`** (all 300, by action: where the hours go) → `cases.md` (the accounts, by name, with the prospect's
sentence) → `metrics.md` (the bets, their dates, the track record) → `rep_worklist.csv`
(what the reps actually get — no score on it) → `actions.csv` (what to sign).

## What would make me stop before phase 1

The blocking question. If the contact window overlaps the outcome window, the 24.6
contacts per conversion in `metrics.md` is measuring leakage, and the honest move is to
say so before the first worklist goes out — not after the second quarter.

## Proposed extension — the conversation layer

Designed, measured on synthetic transcripts, and kept out of the pipeline until real call transcripts exist for accounts with a known outcome. It would work the margin — the accounts no column separates — and be judged like every other mechanism: recall on the margin with it against without, at day 90. Plan, contract and measurement in `proposal/conversation_layer/`. Precondition: recording with per-call disclosure on the 67 fill-gap accounts, which already receive calls.
