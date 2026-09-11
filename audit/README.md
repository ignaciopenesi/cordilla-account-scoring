# Audit — what we found, why the model is not used, and the hypotheses as they stand

**Scope.** One inherited pickle (`model/model.pkl`: a scikit-learn `Pipeline` — `ColumnTransformer`
→ `GradientBoostingClassifier`, 40 trees of depth 2, learning rate 0.05, sha256 `fc2cd6aa…`), 1,200
labelled accounts, 300 to score. Reference date 2026-08-01. **The pickle was never retrained and
the CSVs never modified**; every clone fitted for diagnosis lives in this folder and ships nowhere.

**Evidence, in two layers.** `01_model_audit.ipynb` (110 cells, ~4 min) opens the model. Three scripts beside it measure it against
outcomes, leak-free, and leave their results as JSON the pipeline reads (`uplift.json`, `heldout_comparison.json`): `oof_predictions.npy` (out-of-fold scores — what the model
knows about rows it never saw: `RepeatedStratifiedKFold(5, 10, random_state=7)`, i.e. 5 folds repeated 10 times, a `clone()` per fold, averaged; the notebook's §2.3 by another route), `heldout_comparison.py` (300 accounts none of the methods saw),
`variable_scorecard.py` (every column alone; ranking keys tried and rejected), `uplift.py` (what a
call changes, by segment). `RESEARCH-LOG.md` holds the sequence and the corrections.

---

## 1 · Conclusions about the model

| # | conclusion | the number | where |
|---|---|---|---|
| 1 | **It was fitted with no holdout.** `clone(model).fit()` on the 1,200 rows in file order reproduces the pickle bit for bit. Every metric anyone computed on it was in-sample. | max Δp = 0.0 | notebook §0.4 |
| 2 | **Its headline is noise.** In-sample AUC 0.759 (ranking quality; 0.5 is a coin flip); the same architecture fitted to permuted labels 200 times scores a median of 0.762. | p = 0.575 | notebook §2.2 |
| 3 | **Out of sample it is weak; forward in time it is below chance.** Out-of-fold (OOF) AUC 0.576 on the 1,099 closed rows (the notebook's single model: 0.573 ± 0.024); forward-chaining 0.474. `ORDER BY sales_contacts_90d DESC` scores 0.608 on the same rows. | | notebook §2.3, §2.6a · `oof_predictions.npy` |
| 4 | **Its number is memory, not prediction.** Its list of 90 converts at **31.1%** when it scores rows it was trained on and **6.7%** when it scores rows it never saw — random is 7.3%. On 300 held-out accounts: memory 25–33%, prediction 10–13%. This is the brief's folklore, measured. | | `PROVE` · `heldout_comparison.py` |
| 5 | **It reads effort as intent.** Its strongest feature is `sales_contacts_90d`. Its #1 account (`ACC-01491`) has 5 contacts, no result and a 290-day-old snapshot; its top 10 average 3.6 contacts against 1.6 for the batch. Accounts with 5+ fruitless contacts sit at median rank 37 of 300; untouched accounts with a live trial at median rank 108, none in its top 30. | | `RANK` · `serving/out/cases.md` |
| 6 | **Importance tracks cardinality, not signal.** Rank correlation (Spearman) between importance and distinct values = +0.77; a pure-noise column in `intent_score`'s slot earns 75% of its importance. The vendor score's *value* contributes −0.001 AUC; only its *missingness* does (+0.028). | p = 0.041 | notebook §3.3–3.4 |
| 7 | **It adds nothing on top of a hand-written rule.** Tested three ways on held-out data: as the ranker (13.3% vs 20.0% for the rules, K=60), added to the rules (replacing half of `continue`'s picks with its best removed conversions, 7 → 5), and as a tiebreaker inside a rule (the worst of five tried: 8 buyers vs 11). | | `variable_scorecard.py` · `heldout_comparison.py` |
| 8 | **On the accounts nobody has called it is worse than random.** AUC 0.446 on the 435 untouched accounts in history. It learned that no contact means no conversion, because that is what the record shows. | | §3b below · `heldout_comparison.py` |
| 9 | **A third of its top 30 is the seed.** Changing only `random_state` replaces 21.4 of 30; the #30 and #31 accounts differ by 0.0005. | | notebook §4.1 |
| 10 | **It promises what the business does not see.** Its probabilities sum (Σp) to 19.7 expected conversions in 300 accounts (6.6%) against a field rate of 1–3%. Brier and log-loss (calibration scores) are worse than printing 6.5% on every row. | | `SCORE` · `VERDICT` |
| 11 | **It breaks on the least-maintained field.** A null `account_type` raises `TypeError` and kills the batch; `intent_score = −50` raises the score; unseen categories score silently. | | notebook §4.2 · `VALIDATE` |

## 2 · Why it is not used to decide — and what it is still used for

**Not as a ranker, not as an addition, not as a tiebreaker** (rows 4, 7, 8). The dashboard the VP
asked for would show 31% and deliver 7%; the previous scoring effort "lost credibility once the
scores stopped matching the field" for exactly this reason, and nobody wrote it up because there
was no holdout to write it up against.

**Still used, in three places, none of them a decision:** as one voice in `RECONCILE` (where it
disagrees with the team's own effort — 55 accounts — the rep is asked); in the head-to-head the
brief requires (*the model's top 30 → what happens to each here*, every run); and as the footnote
of `PROVE` that keeps the memory-vs-prediction gap visible so the next model cannot ship the same
way.

**What decides instead:** rules on the three columns that survive the scorecard — contacts, trial
started, vendor *presence* — validated on outcomes the rules never saw, and an experiment with a
control so day 90 can say whether they were right. `serving/README.md`.

## 3 · The hypotheses, consolidated

Status: **verified** (real outcomes, held-out where it matters) · **supported** (real data,
observational, direction stable) · **hypothesis** (stated, tested at day 90) · **unknown**.

| # | statement | status | evidence | settled by |
|---|---|---|---|---|
| H1 | **The contact window precedes the outcome window** (`sales_contacts_90d` is not the same 90 days as `converted_within_90d`) | **UNKNOWN — blocking** | nothing in the files states it. If they overlap, the one signal in this dataset is leakage and every hours number here is measuring it | one question to the data owner |
| H2 | **Conversion follows contact** — 20 of the 23 held-out buyers had been contacted; untouched accounts convert at 2.6% *when nobody calls* | **verified as correlation**; causality **unknown** | `uplift.py`, `heldout_comparison.py` | the arms: `first-call` vs `observe`, `continue` vs `control` |
| H3 | **The first call on an untouched trial account changes the outcome most**: +10 pts (5.0% → 15.2%), CI [+2, +18], p = 0.034; positive on train, test and all | **supported — an upper bound** (reps chose whom to call) | `uplift.py`; dose: 1 call 16%, 2: 18%, 3: 15%, 4: 7% | `first-call` (called) vs `observe` (not), ~138 per group for 5%→15% |
| H4 | **Calling web-only or MQL-only accounts never helps**: uplift ≤ 0 on every cut (web −7, MQL 0 overall), despite selection bias in their favour; with 1–4 contacts, 0 of 141 converted | **supported** → `skip` | `uplift.py`, `variable_scorecard.py` | tracked: if they convert anyway, the rule was wrong |
| H5 | **Vendor coverage predicts; the vendor's score does not.** Covered 8.22% vs 3.94% (p = 0.003); by quintile among the covered: 9.0 / 5.3 / 12.8 / 7.6 / 9.8. In the 1–4-contact, no-trial pool: 8.3% vs 2.7% on the early 60% (p = 0.07), 8.2% vs 1.6% on all (p = 0.002) | **verified** (coverage) · **verified** (score is flat) | notebook §3.4; `variable_scorecard.py` | already used: `continue`'s second tier |
| H6 | **"Suspect" is mislabelled.** The brief does not define it. Under the funnel reading (no engagement yet), Suspects carry *more* contacts than Prospects (1.69 vs 1.54; 61% vs 59% with ≥1; 18% vs 14% with ≥4), the same MQLs and trials, Mann-Whitney rank test p = 0.20; 15% truly untouched vs 16%. Under *any* reading the field is empty: conversion identical across types (χ² p = 0.84), importance 0.003 | **checked — the label carries no information** | `HYGIENE`, `CLEAN` | one question to the CRM owner: what is it supposed to mean |
| H7 | **A two-quarter-old snapshot is still actionable.** 102 of 300 are >180 days; every feature is a 90-day window | **hypothesis — flagged, not blocked** | `CLEAN` flags it; `READOUT` compares stale vs fresh inside each arm | day 90; if stale converts materially below fresh, the flag becomes a filter |
| H8 | **Trials with 0 active users are not dead**: 15.8% vs 13.1% for live trials at 1–4 contacts | **supported** — the rule takes any trial | `HYGIENE`; `uplift.py` dose table | ask product: provisioned-and-unused, or missing telemetry |
| H9 | **`web_touchpoints_90d = 0` may mean "not measured"**: 0 converts at 7.4% vs 4.5% for 1–3 | **hypothesis** — directional (p = 0.12) | notebook §3.6 | data contract with the attribution vendor: NULL when unmeasured |
| H10 | **101 training labels were closed before their window** (snapshot < 90 days old, labelled 0); those rows carry 33% more MQLs | **verified** | notebook §3.10; `VALIDATE` | excluded from every evaluation here; label = NULL in the labelling job |
| H11 | **The prospect's own words are the one signal not a function of Cordilla's effort**, and they would rank the eight held-out buyers no column separates | **hypothesis — designed, measured on synthetic transcripts, not wired** | `extensions/conversation_layer/`; 1.00 on the routing field, 20/20 grounded, on 12 templates of my own ground truth | real transcripts on accounts with outcomes; recall on the margin with vs without |

## 3b · Where the 23 held-out buyers are, one by one

| account | contacts | trial | vendor record | MQL | web | model rank /300 | reached by |
|---|---|---|---|---|---|---|---|
| `ACC-00560` | 5 | yes | yes | 2 | 0 | #4 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00054` | 5 | — | yes | 2 | 0 | #27 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00984` | 5 | — | yes | 1 | 5 | #37 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-00731` | 5 | — | yes | 1 | 6 | #18 | ask (5+ contacts) — recoverable if the rep answers |
| `ACC-01259` | 4 | yes | yes | 1 | 0 | #33 | continue segment 'trial', position 4 — in the top 40 |
| `ACC-00807` | 4 | — | yes | 0 | 0 | #68 | continue segment 'vendor', position 41 — below the cut |
| `ACC-01231` | 4 | — | yes | 0 | 4 | #71 | continue segment 'vendor', position 43 — below the cut |
| `ACC-00064` | 3 | yes | yes | 0 | 0 | #36 | continue segment 'trial', position 5 — in the top 40 |
| `ACC-00214` | 3 | yes | — | 0 | 3 | #249 | continue segment 'trial', position 6 — in the top 40 |
| `ACC-00372` | 3 | — | yes | 3 | 0 | #231 | continue segment 'vendor', position 54 — below the cut |
| `ACC-00139` | 3 | — | yes | 0 | 7 | #119 | continue segment 'vendor', position 49 — below the cut |
| `ACC-01072` | 2 | — | yes | 2 | 8 | #98 | continue segment 'vendor', position 83 — below the cut |
| `ACC-00848` | 2 | — | yes | 1 | 4 | #228 | continue segment 'vendor', position 79 — below the cut |
| `ACC-01143` | 2 | yes | yes | 2 | 0 | #59 | continue segment 'trial', position 22 — in the top 40 |
| `ACC-01468` | 2 | yes | — | 2 | 0 | #99 | continue segment 'trial', position 24 — in the top 40 |
| `ACC-00103` | 2 | yes | yes | 1 | 3 | #136 | continue segment 'trial', position 14 — in the top 40 |
| `ACC-00975` | 1 | — | yes | 0 | 6 | #167 | continue segment 'vendor', position 101 — below the cut |
| `ACC-00235` | 1 | yes | yes | 0 | 2 | #41 | continue segment 'trial', position 26 — in the top 40 |
| `ACC-00981` | 1 | — | yes | 2 | 0 | #152 | continue segment 'vendor', position 103 — below the cut |
| `ACC-01357` | 1 | yes | yes | 5 | 2 | #87 | continue segment 'trial', position 33 — in the top 40 |
| `ACC-00607` | 0 | — | — | 0 | 0 | #294 | 0 contacts, no signal — nothing reaches it |
| `ACC-01313` | 0 | — | yes | 0 | 9 | #76 | first-call, position 22 |
| `ACC-01499` | 0 | — | yes | 1 | 0 | #288 | first-call, position 76 |

| mechanism | converters | of 23 | what it means |
|---|---|---|---|
| **continue, top 40** | **8** | 35% | **every one has a trial.** In the 1–4-contact pool, trial converts 23.5%, no trial 6.3% — the trial does continue's work |
| **continue pool, below the cut** | **8** | 35% | **none has a trial.** On contacts, MQL, web and the model's own score they are indistinguishable from the 118 non-converters beside them (Mann-Whitney rank test p = 0.59 / 0.95 / 0.79 / 0.56; the model ranks them at median 51 of 126 — random). One column separates them: **all 8 have a vendor record, vs 56%** |
| ask (5+ contacts) | 4 | 17% | the model ranks them #4, #18, #27, #37 — it loves them, for the contacts. Recoverable if the rep answers *live deal* |
| first-call, top 20 | 0 | 0% | `ACC-01313`, 9 web touches, never called — first-call ranks it at position 22, outside the top 20 |
| first-call, deep | 2 | 9% | positions 22 and 76 of 76 — no ranking reaches them |
| no signal at all | 1 | 4% | 0 contacts, 0 MQL, 0 web, no vendor — nothing in the data sees it; the control decides |

**What each policy sends to the phone, on the 300 to score (no outcomes):**

| list | n | stale (flagged) | exhausted (5+) | never touched | contacts already sunk | hours in exhausted accounts |
|---|---|---|---|---|---|---|
| MODEL top-60 | 60 | 24 | **20** | 16 | 168 | **23 h** |
| GRAPH continue + first-call | 60 | 20 | **0** | 15 | 126 | **0 h** |

The model's top 60 carries 20 exhausted accounts and 23 rep-hours already sunk in them; the graph's 60 carries none. Twenty-four of the model's top 60 are on snapshots older than 180 days — flagged, worked, and tested at day 90.

## 4 · Does everything actually run? Checked 2026-09-11

- **The pickle**: loads and scores the 300 on every run (`SCORE`); a clone fits on 900 rows in 24 ms on one CPU core — it is a small model on a small table. `serving/check.sh`: six modes, three audit scripts, protected shas, all green.
- **The local LLM, on GPU**: `qwen3:14b` via Ollama on an RTX 5080 Laptop (16 GB) — `100% GPU`, 9.6 GB resident, 51% utilisation during the run. `python serving/pipeline.py --llm live` drafted `hygiene_batch` live (the one wired agent routed `local`); the three routed `cloud` fell back to the rendered template with the reason printed (`ANTHROPIC_API_KEY not set`), which the brief judges equal to a live call. Zero fallbacks on the local backend. One observation for the log: the drafting model wrote the reclassification as a fact where the finding says hypothesis — the reason a human signs, not the agent.
- **The proposal's extraction contract**, re-run live on the same GPU against the 20 synthetic transcripts (`extract_intents.py --mode live --force`, saved as `extensions/conversation_layer/demo_data/intents_rerun_gpu_2026-09-11.json`): the two fields the pipeline would route on reproduced exactly — `ready_to_act` **1.00, 0 of 20 changed**; `next_step_agreed` 1.00 — while the six-level grade moved on **7 of 20** (exact 0.80 → 0.75, hot-vs-cold 0.95 → 1.00) and mean confidence 0.975 → 0.945. Sampling variance in the secondary field, none in the routed ones — which is the design's assumption, observed. An earlier note in the log called this run byte-identical; it was written before the file had been rewritten, and is corrected in entry 28.
- **The experiment's control** is a coin-flipped third of the batch drawn before any rule runs (207 system / 93 control on the 300), so system-vs-control at day 90 is a comparison of policies, intention-to-treat (every account counted in the third it was assigned to, whatever happened after). An earlier version drew control from the leftovers after the system had picked; that compared the system to what it rejected, and is fixed.

## 5 · Reproduce

```bash
bash serving/check.sh                        # everything, ~1 min
python audit/uplift.py                       # the uplift table, leak-free
python audit/heldout_comparison.py           # 300 held-out accounts, every policy
python audit/variable_scorecard.py           # every column alone; five ranking keys
jupyter nbconvert --to notebook --execute --inplace audit/01_model_audit.ipynb   # ~4 min
```
