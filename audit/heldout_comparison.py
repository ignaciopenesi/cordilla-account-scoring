"""Held-out prediction test: model alone · exploit alone · the graph, on 300 accounts none of them saw.

The 1,200 labelled rows, minus the 101 whose 90-day window had not closed, sorted by
snapshot date. The most recent 300 are the TEST set; the older 799 are what any method is
allowed to know. Each method builds its list of K from the 300 and we count who converted.

NO MODEL IS FITTED HERE. The model's prediction for a test row is its out-of-fold score
(`oof_predictions.npy`, built in the audit: 5-fold x 10 repeats, each row scored by a clone
that never saw it). The graph's rules are not fitted to anything. The pickle's own score on
the same rows is shown beside them so memory and prediction sit in one table.

Metrics -- accuracy is meaningless at a 7% positive rate (predicting "nobody converts" scores 93%):
  precision@K   of the K you said to call, the share that converted   (the scorecard's metric)
  recall@K      of everyone who converted in the 300, the share your list found
  lift          precision / base rate
  contacts sunk what had already been spent on the K -- the hours dimension

Run:  python audit/heldout_comparison.py        writes audit/heldout_comparison.json
"""
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TODAY = pd.Timestamp("2026-08-01")
FEATURES = ["account_type", "employee_count", "industry", "intent_score", "mql_count_90d",
            "trial_started", "trial_active_users", "web_touchpoints_90d", "sales_contacts_90d"]
TEST_N = 300

t = pd.read_csv(ROOT / "data/training_data.csv", parse_dates=["snapshot_date"])
t["p_oof"] = np.load(ROOT / "audit/oof_predictions.npy")            # aligned to file order
with open(ROOT / "model/model.pkl", "rb") as f:
    t["p_memory"] = pickle.load(f).predict_proba(t[FEATURES])[:, 1]  # the pickle scoring itself
t = t[(TODAY - t.snapshot_date).dt.days >= 90]                       # label window closed
t = t.sort_values("snapshot_date").reset_index(drop=True)
test, train = t.iloc[-TEST_N:].copy(), t.iloc[:-TEST_N]
y = test.converted_within_90d
base, n_pos = y.mean(), int(y.sum())
C = test.sales_contacts_90d
signal = (test.trial_started == 1) | (test.mql_count_90d > 0) | (test.web_touchpoints_90d >= 4)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    ph, d = k / n, 1 + z**2 / n
    c = (ph + z**2 / (2 * n)) / d
    h = z * np.sqrt(ph * (1 - ph) / n + z**2 / (4 * n**2)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _seg(d): return np.select([d.trial_started == 1, d.intent_score.notna(), d.web_touchpoints_90d >= 4, d.mql_count_90d > 0], ["trial", "vendor", "web", "mql"], "none")
test["seg"] = _seg(test); test["_sr"] = test.seg.map({"trial": 0, "vendor": 1, "none": 2, "mql": 3, "web": 4})
exploit_pool = test[C.between(1, 4) & ~test.seg.isin(["mql", "web"])].sort_values(["_sr", "sales_contacts_90d", "account_id"], ascending=[True, False, True])
explore_pool = test[(C == 0) & test.seg.isin(["trial", "vendor"])].sort_values(["_sr", "web_touchpoints_90d", "account_id"], ascending=[True, False, True])
ask_pool = test[C >= 5]


def policies(K):
    return {
        "model — the pickle scoring rows it was trained on (memory)": test.nlargest(K, "p_memory"),
        "model — out-of-fold (prediction)":                            test.nlargest(K, "p_oof"),
        "continue alone (1–4 contacts: trial > vendor > none)":                   exploit_pool.head(K),
        "first-call alone (untouched trial, then vendor)":                 explore_pool.head(K),
        "THE GRAPH — continue 5/6 + first-call 1/6, ask and skip excluded":         pd.concat([exploit_pool.head(K * 5 // 6), explore_pool.head(K - K * 5 // 6)]),
        "continue ∪ model picks (half each) — does the model add anything?":
            pd.concat([exploit_pool.head(K // 2),
                       test[~test.account_id.isin(exploit_pool.head(K // 2).account_id)].nlargest(K - K // 2, "p_oof")]),
        "ask cohort, if called anyway (5+ contacts)":                  ask_pool.nlargest(K, "sales_contacts_90d"),
    }


out = {"test_n": TEST_N, "train_n": int(len(train)), "test_base_rate": round(float(base), 4),
       "test_converters": n_pos, "test_window": [str(test.snapshot_date.min().date()), str(test.snapshot_date.max().date())],
       "train_window": [str(train.snapshot_date.min().date()), str(train.snapshot_date.max().date())],
       "fits_performed": 0, "by_K": {}}
rng = np.random.default_rng(11)
print(f"TEST = the {TEST_N} most recent labelled accounts ({out['test_window'][0]} → {out['test_window'][1]}) · "
      f"{n_pos} converted ({base:.1%}) · TRAIN = the {len(train)} before them · fits performed here: 0")
for K in (30, 60):
    rows = []
    for name, d in policies(K).items():
        k, n = int(d.converted_within_90d.sum()), len(d)
        lo, hi = wilson(k, n)
        rows.append({"policy": name, "n": n, "converted": k,
                     "precision": round(k / n, 4) if n else None, "ci95": f"[{lo:.0%}, {hi:.0%}]" if n else "",
                     "recall": round(k / n_pos, 4), "lift": round(k / n / base, 2) if n else None,
                     "contacts_sunk": int(d.sales_contacts_90d.sum()),
                     "model_rank_median": int(d.p_oof.rank(ascending=False).median()) if n else None})
    draws = np.array([test.sample(K, random_state=int(r)).converted_within_90d.sum() for r in rng.integers(0, 10**6, 200)])
    rows.append({"policy": "random (mean of 200 draws)", "n": K, "converted": round(float(draws.mean()), 1),
                 "precision": round(float(draws.mean() / K), 4),
                 "ci95": f"5–95%: [{np.percentile(draws, 5) / K:.0%}, {np.percentile(draws, 95) / K:.0%}]",
                 "recall": round(float(draws.mean() / n_pos), 4), "lift": round(float(draws.mean() / K / base), 2),
                 "contacts_sunk": int(round(C.mean() * K)), "model_rank_median": None})
    worked = test[C >= 1]
    rows.append({"policy": "the team today — every account it chose to work", "n": int(len(worked)),
                 "converted": int(worked.converted_within_90d.sum()),
                 "precision": round(worked.converted_within_90d.mean(), 4),
                 "ci95": "[{:.0%}, {:.0%}]".format(*wilson(int(worked.converted_within_90d.sum()), len(worked))),
                 "recall": round(worked.converted_within_90d.sum() / n_pos, 4),
                 "lift": round(worked.converted_within_90d.mean() / base, 2),
                 "contacts_sunk": int(worked.sales_contacts_90d.sum()), "model_rank_median": None})
    rows.append({"policy": "the graph WITH the conversation agent", "n": None, "converted": None, "precision": None,
                 "ci95": "needs call transcripts on accounts with a known outcome — none exist; the proposed extension in serving/README.md",
                 "recall": None, "lift": None, "contacts_sunk": None, "model_rank_median": None})
    out["by_K"][K] = rows
    tab = pd.DataFrame(rows)
    tab["precision"] = tab.precision.map(lambda v: f"{v:.1%}" if v is not None and v == v else "—")
    tab["recall"] = tab.recall.map(lambda v: f"{v:.0%}" if v is not None and v == v else "—")
    print(f"\nK = {K}")
    print(tab[["policy", "converted", "precision", "ci95", "recall", "lift", "contacts_sunk", "model_rank_median"]]
          .to_string(index=False))

# ── the converters, one by one: which mechanism reaches each ──────────────────────────────────
conv = test[test.converted_within_90d == 1].copy()
pos_ex = {a: i + 1 for i, a in enumerate(exploit_pool.account_id)}
pos_xp = {a: i + 1 for i, a in enumerate(explore_pool.account_id)}
def mechanism(r):
    c = int(r.sales_contacts_90d)
    if c >= 5:
        return "ask (5+ contacts) — recoverable if the rep answers"
    if c == 0:
        return f"first-call, position {pos_xp[r.account_id]}" if r.account_id in pos_xp else ("skip — web/MQL-only" if r.seg in ("web", "mql") else "0 contacts, no signal — control decides")
    tier = r.seg
    pe = pos_ex[r.account_id]
    return f"continue segment '{tier}', position {pe}" + (" — in the top 40" if pe <= 40 else " — below the cut")
conv["mechanism"] = conv.apply(mechanism, axis=1)
conv["model_rank"] = conv.p_oof.rank(ascending=False).astype(int)
out["converters"] = [{"account_id": r.account_id, "contacts": int(r.sales_contacts_90d),
                      "trial": bool(r.trial_started), "vendor_record": bool(pd.notna(r.intent_score)),
                      "mql": int(r.mql_count_90d), "web": int(r.web_touchpoints_90d),
                      "model_rank_of_300": int(test.p_oof.rank(ascending=False)[r.name]),
                      "mechanism": r.mechanism} for _, r in conv.sort_values("sales_contacts_90d", ascending=False).iterrows()]
summary = {"continue top-40": int(sum("in the top 40" in m for m in conv.mechanism)),
           "continue pool, below the cut": int(sum("below the cut" in m for m in conv.mechanism)),
           "ask (5+)": int(sum(m.startswith("ask") for m in conv.mechanism)),
           "first-call, reached (top 20)": int(sum(m.startswith("first-call") and int(m.split()[-1]) <= 20 for m in conv.mechanism)),
           "first-call, deep": int(sum(m.startswith("first-call") and int(m.split()[-1]) > 20 for m in conv.mechanism)),
           "no signal / skip": int(sum(m.startswith(("0 contacts", "skip")) for m in conv.mechanism))}
out["converter_summary"] = summary
print(f"\nthe {n_pos} converters, by the mechanism that reaches them:")
for k, v in summary.items():
    print(f"  {v:2d}  {k}")
(ROOT / "audit/heldout_comparison.json").write_text(json.dumps(out, indent=2, default=str))
print(f"\nwritten: audit/heldout_comparison.json")
