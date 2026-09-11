# Cordilla Systems — model audit & AI-assisted serving

Take-home for the AI Transformation Analyst role at Dialpad. Five lines:

1. **The inherited model does not work, and the reason is inside the pickle.** Fitted with no holdout; its in-sample AUC (0.759) is what the same architecture scores on random labels (0.762); its list of 90 converts at **31% scored from memory and 6.7% out of fold** — random is 7.3%. → `audit/README.md`
2. **It reads effort as intent.** Its strongest feature is our own contact count; its #1 account has 5 fruitless contacts and a 290-day-old snapshot; on accounts nobody has called it is worse than random. → `audit/README.md` §1
3. **Where the next hour changes most is measurable — as an upper bound — and it is the first call on an untouched trial account: positive on every cut, +10 points overall.** Web-only and MQL-only accounts: calling never helped. → `audit/uplift.py`
4. **`serving/` ranks every account by that, coin-flips a third of the batch to the rep as control before any rule runs, cuts the rest at the budget, asks the rep before the sixth call, skips where calling never helped, and splits the untouched trials at random so day 90 measures the +10 without the bias.** Fifteen nodes, fourteen run today, one human signature before anything writes. → `serving/README.md`
5. **The conversation layer — the one input not a function of Cordilla's own effort — is designed, measured, and deliberately not wired.** → `proposal/conversation_layer/`

## Where things live

| file | role |
|---|---|
| `PROPOSAL.md` | the proposal, 1,190 words, the four areas the brief asks for |
| `audit/README.md` | the audit: eleven conclusions on the model, why it is not used, eleven hypotheses with status; `01_model_audit.ipynb` is the evidence, the three scripts and one artifact beside it the outcome tests |
| `serving/README.md` | the agent: the fifteen nodes, arms and cohorts, configuration, outputs — **and how the improvement is measured, the rollout phases, and the additional lines of improvement** |
| `proposal/conversation_layer/` | the conversation layer: design, measured contract, how to wire it back |
| `RESEARCH-LOG.md` | how it was done — 27 entries, timestamped, never rewritten |

## Run

```
bash serving/check.sh                                # everything: six modes, three audit scripts, protected shas (~1 min)
python serving/pipeline.py                           # real mode: 14 of 15 nodes, ~4 s → serving/out/
python serving/pipeline.py --demo --cycles 4 --reset-cycles   # + simulated day-90 outcomes: READOUT and the loop, four cycles
python serving/pipeline.py --llm live                # the wired agent drafts on the local model (config.toml)
jupyter nbconvert --to notebook --execute --inplace audit/01_model_audit.ipynb
```

Everything below is the original starter README, lightly corrected.

---

## Setup

    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

Tested against Python 3.11+ with the exact pinned versions above. If you'd rather work in a notebook than plain scripts (either is fine, see the take-home packet), `pip install -r requirements-notebook.txt` instead (adds Jupyter on top of the same pinned core).

Loading the model (already trained, don't retrain it):

    import pickle
    with open("model/model.pkl", "rb") as f:
        model = pickle.load(f)
    # model.predict_proba(df[feature_columns]), feature columns are listed below and in the take-home packet

Expected feature columns, in the order the model was trained on: `account_type`, `employee_count`, `industry`, `intent_score`, `mql_count_90d`, `trial_started`, `trial_active_users`, `web_touchpoints_90d`, `sales_contacts_90d`. `snapshot_date` and `account_id` are identifiers, not model inputs.

**Treat 2026-08-01 as "today" for this exercise.** Both CSVs are static snapshots generated as of that date. Any recency/age calculation (e.g. "how old is this account's snapshot") should use 2026-08-01 as the reference point, not your actual system clock.

## What's here

- `model/model.pkl`, a real, already-trained scikit-learn pipeline. Don't retrain it, your job is to understand and audit it, not rebuild it.
- `data/training_data.csv`, the labeled historical data the model above was actually trained on. Provided so you can audit *how* it was trained, not just what it predicts.
- `data/accounts_to_score.csv`, an unlabeled batch you'll run the model against as part of the serving step. Don't modify or regenerate either CSV; everyone works from the same files.
- `audit/01_model_audit.ipynb`, the model audit. Runs end to end in ~4 minutes:

      jupyter nbconvert --to notebook --execute --inplace audit/01_model_audit.ipynb

  or just open it — it is committed with all outputs and figures, so it reads on GitHub
  without running anything. It never refits the shipped model; §0.4 explains the one
  place it fits a *clone* of the architecture, and why that is diagnosis rather than
  retraining.
- `serving/`, the AI-assisted serving step — `serving/README.md`.
- `PROPOSAL.md`, the written design proposal: framing, audit, serving design, productionization and trust.
- `RESEARCH-LOG.md`, kept as I went, timestamped, never rewritten — including the places where the AI was wrong and what I changed.

## Working process

Commit as you actually go, small, real commits over time, not one commit at the end. We read the commit history as part of how you reason and work, not just the final diff.

**We'd genuinely like you to use AI here, assisted coding tools especially (Claude Code, Codex, Cursor, Antigravity, or similar), on your own accounts.** Dialpad doesn't provide one for this exercise. Disclose your actual sessions/prompts in `RESEARCH-LOG.md`, specific enough that we can see what shaped a decision, not a vague "used AI throughout."

## When you're done

Push this to a public git repo and send us the link. That's the submission. The presentation gets scheduled as a separate follow-up after that, not something to prepare beforehand.
