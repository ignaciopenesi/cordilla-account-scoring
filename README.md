# Cordilla Systems — model audit & AI-assisted serving

Take-home for the AI Transformation Analyst role at Dialpad. The short version:

- **The inherited model does not work, and the reason is inside the pickle.** Its
  in-sample AUC of 0.759 is what the same architecture scores on random labels
  (null median 0.762, p = 0.575). Refit forward in time it scores 0.474 — below chance.
  A one-line `ORDER BY sales_contacts_90d DESC` beats it. → `audit/01_model_audit.ipynb`
- **The nine columns contain no account-intrinsic signal.** The only two that carry any
  measure what Cordilla already did to the account. So the ask is not a better model —
  it is producing the data that is missing while the system runs. → `PROPOSAL.md`
- **`serving/` is a stateful graph that runs end to end in four seconds.** It scores the
  300, keeps the model as *one voice of three* and uses it only where it disagrees,
  allocates effort into three matched arms with a control, proposes CRM corrections with
  the rule that stops each defect recurring, and writes one weekly verdict — with a single
  human approval before anything touches Salesforce. **Nodes whose inputs do not exist yet
  are declared as bypassed, not stubbed:** 11 run, 2 are partial, 2 are bypassed, and each
  bypass records what would unblock it. → `serving/README.md`
- **How I worked, including where AI was wrong and what I changed** → `RESEARCH-LOG.md`

```
audit/01_model_audit.ipynb   110 cells, runs in ~4 min, committed with outputs
serving/pipeline.py          python serving/pipeline.py          (11 of 15 nodes, ~4s)
                             python serving/pipeline.py --demo   (all 15, synthetic inputs)
serving/README.md            the graph, what runs today and what does not
PROPOSAL.md                  ~1,250 words, the four areas
RESEARCH-LOG.md              8 entries, kept as I went
```

Everything below is the original starter README, kept as provided.

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
- `audit/01_model_audit.ipynb`, the model audit. Runs end to end in ~3 minutes:

      jupyter nbconvert --to notebook --execute --inplace audit/01_model_audit.ipynb

  or just open it — it is committed with all outputs and figures, so it reads on GitHub
  without running anything. It never refits the shipped model; §0.4 explains the one
  place it fits a *clone* of the architecture, and why that is diagnosis rather than
  retraining.
- `serving/`, the AI-assisted serving step — see `serving/README.md` once it lands.
- `PROPOSAL.md`, the written design proposal: framing, audit, serving design, productionization and trust.
- `RESEARCH-LOG.md`, kept as I went: six entries, timestamped, never rewritten — including three places where I corrected my own work and two where I overrode what an AI tool gave me.

## Working process

Commit as you actually go, small, real commits over time, not one commit at the end. We read the commit history as part of how you reason and work, not just the final diff.

**We'd genuinely like you to use AI here, assisted coding tools especially (Claude Code, Codex, Cursor, Antigravity, or similar), on your own accounts.** Dialpad doesn't provide one for this exercise. Disclose your actual sessions/prompts in `RESEARCH-LOG.md`, specific enough that we can see what shaped a decision, not a vague "used AI throughout."

## When you're done

Push this to a public git repo and send us the link. That's the submission. The presentation gets scheduled as a separate follow-up after that, not something to prepare beforehand.
