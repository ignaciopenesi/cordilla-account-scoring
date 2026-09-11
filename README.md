# Cordilla Systems, Model Audit & AI-Assisted Serving Exercise

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
- `audit/`, your model audit (notebook or scripts, your call).
- `serving/`, your AI-assisted serving step: load the model, score `accounts_to_score.csv`, and do something workflow-shaped with the output.
- `PROPOSAL.md`, your written design proposal (see the take-home packet for the required sections).
- `RESEARCH-LOG.md`, your running log as you work: hypotheses, what you tried, dead ends, and specifically what you asked your AI tool and how you used what came back.

## Working process

Commit as you actually go, small, real commits over time, not one commit at the end. We read the commit history as part of how you reason and work, not just the final diff.

**We'd genuinely like you to use AI here, assisted coding tools especially (Claude Code, Codex, Cursor, Antigravity, or similar), on your own accounts.** Dialpad doesn't provide one for this exercise. Disclose your actual sessions/prompts in `RESEARCH-LOG.md`, specific enough that we can see what shaped a decision, not a vague "used AI throughout."

## When you're done

Push this to a public git repo and send us the link. That's the submission. The presentation gets scheduled as a separate follow-up after that, not something to prepare beforehand.
