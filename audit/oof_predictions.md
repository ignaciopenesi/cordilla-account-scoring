# `oof_predictions.npy` — out-of-fold scores for the 1,200 training rows

**What it is.** One probability per training row, in file order, produced by a model that
never saw that row. Built in the audit (`01_model_audit.ipynb` §2.3 and the verification
script `panel_A_provenance_heldout.py`): `RepeatedStratifiedKFold(n_splits=5, n_repeats=10,
random_state=7)`, a `clone()` of the pickled pipeline fitted on each training fold and
scored on the held-out fold, averaged over the 10 repeats.

**Why it exists.** The pickle scores its own training rows from memory (in-sample AUC 0.759,
which is what a random-label model also scores). These are the scores it would give if it
had to *predict* — AUC 0.576. `serving/BASELINES` reads this file to compare the model's
honest list against the graph's rules on real outcomes.

**What it is not.** Not a retrained model. The pickle in `model/` is untouched (sha256
`fc2cd6aa…`). Cloning for diagnosis is what the audit did to prove provenance; the brief's
"do not retrain" is about what gets shipped, and nothing here ships.
