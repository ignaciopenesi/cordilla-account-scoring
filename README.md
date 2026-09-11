# Cordilla Systems — model audit & AI-assisted serving

Take-home for the AI Transformation Analyst role at Dialpad. An inherited lead-scoring model is
audited against real outcomes and found to predict no better than chance; a fifteen-node serving
graph replaces it with rules validated on held-out data, a coin-flipped control, and a readout that
turns the experiment into one number with an interval. The evidence, the agent, the proposal and the
log each live in one file:

| file | what it is | read it if you want |
|---|---|---|
| `PROPOSAL.md` | the proposal the brief asks for — framing, audit, serving design, productionisation and trust — in 1,200 words | the argument |
| `audit/README.md` | what the model is, why it is not used to decide, eleven hypotheses with their status, the held-out buyers one by one, and proof that everything runs | the evidence |
| `serving/README.md` | the agent: the fifteen nodes, arms and cohorts, configuration, outputs — and how the improvement is measured, the rollout phases, the additional lines of improvement | how it works and what comes next |
| `extensions/conversation_layer/README.md` | the one input not a function of Cordilla's own effort — what the prospect said on the call — designed, measured on synthetic transcripts, deliberately not wired | the future |
| `RESEARCH-LOG.md` | how it was done, 28 entries, timestamped, never rewritten — including where the AI was wrong and what changed | the process |
| `audit/01_model_audit.ipynb` · `audit/*.py` | the notebook that opens the model (110 cells, ~1 min) and the three scripts that measure it against outcomes | the numbers |
| `serving/out/` | this week's outputs, committed so they can be read here: `manager_brief.md`, `ranked.csv`, `cases.md`, `metrics.md`, the worklist, the actions | the deliverable a manager would get |

## Run

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt     # Python 3.11 or 3.12
bash serving/check.sh                          # everything: six pipeline modes, three audit scripts, protected shas, ~10 s
python serving/pipeline.py                     # real mode: 14 of 15 nodes, ~4 s → serving/out/
python serving/pipeline.py --demo --cycles 4 --reset-cycles    # + simulated day-90 outcomes: READOUT and the loop, four cycles
python serving/pipeline.py --llm live          # the wired agent drafts on the local model in serving/config.toml
jupyter nbconvert --to notebook --execute --inplace audit/01_model_audit.ipynb    # needs requirements-notebook.txt
```

A `--demo` run rewrites three files in `serving/out/`; `bash serving/check.sh` restores the committed
real-mode state. Word counts quoted for `PROPOSAL.md` are prose words — headings and table rows
excluded — the count `check.sh` asserts.

## The data and the model, as provided

- `model/model.pkl` — a scikit-learn pipeline, already trained. **Never retrained here**; every clone
  fitted for diagnosis lives in `audit/` and ships nowhere. Load it with `pickle.load`; the feature
  columns, in training order: `account_type`, `employee_count`, `industry`, `intent_score`,
  `mql_count_90d`, `trial_started`, `trial_active_users`, `web_touchpoints_90d`, `sales_contacts_90d`.
- `data/training_data.csv` — the 1,200 labelled accounts the model was trained on.
  `data/accounts_to_score.csv` — the 300 to score. **Neither file is modified**; `check.sh` verifies
  both hashes and the model's on every run.
- **2026-08-01 is "today"** for every age and recency calculation, not the system clock.
