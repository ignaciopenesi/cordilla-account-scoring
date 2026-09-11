"""Uplift by segment: what a call changes, estimated leak-free, with its bias named.

The business question is not "who converts" but "where does the next hour of calling change
the outcome most". For each intent segment, uplift = conversion with 1-4 logged contacts minus
conversion with none. Estimated on TRAIN (the older labelled rows), checked on TEST (the newer),
and on all rows; a segment's rank is trusted only if it holds on all three.

BIAS, stated once: reps chose whom to call, and they call accounts that already look better. So
every uplift here is an UPPER BOUND on the true effect of a call. A segment at or below zero
despite that bias is one where calling does not help -- that much can be said today. The true
magnitude comes only from randomising the first call (BUDGET's first-call arm and its observe
cohort), read at day 90.

Segments (intent axis): trial started > vendor record present > web>=4 only > MQL only > none.
Run: python audit/uplift.py  -> audit/uplift.json
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import fisher_exact, norm

ROOT = Path(__file__).resolve().parent.parent
TODAY = pd.Timestamp("2026-08-01")
SEGMENTS = ["trial", "vendor", "none", "mql", "web"]


def segment(d: pd.DataFrame) -> np.ndarray:
    return np.select([d.trial_started == 1, d.intent_score.notna(), d.web_touchpoints_90d >= 4, d.mql_count_90d > 0],
                     ["trial", "vendor", "web", "mql"], "none")


def uplift_table(d: pd.DataFrame) -> list[dict]:
    x = d.assign(seg=segment(d)); C = x.sales_contacts_90d; rows = []
    for s in SEGMENTS:
        a, b = x[(x.seg == s) & (C == 0)], x[(x.seg == s) & C.between(1, 4)]
        k0, n0, k1, n1 = int(a.converted_within_90d.sum()), len(a), int(b.converted_within_90d.sum()), len(b)
        p0, p1 = (k0 / n0 if n0 else np.nan), (k1 / n1 if n1 else np.nan)
        se = np.sqrt(p0 * (1 - p0) / n0 + p1 * (1 - p1) / n1) if n0 and n1 else np.nan
        hours = b.sales_contacts_90d.mean() * 12 / 60 if n1 else np.nan
        rows.append({"segment": s, "n_uncalled": n0, "conv_uncalled": k0, "rate_uncalled": round(p0, 4),
                     "n_called": n1, "conv_called": k1, "rate_called": round(p1, 4),
                     "uplift_pts": round((p1 - p0) * 100, 1), "ci95_lo": round((p1 - p0 - 1.96 * se) * 100, 1),
                     "ci95_hi": round((p1 - p0 + 1.96 * se) * 100, 1),
                     "fisher_p": round(fisher_exact([[k1, n1 - k1], [k0, n0 - k0]])[1], 3) if n0 and n1 else None,
                     "hours_per_called_account": round(hours, 2), "uplift_per_hour": round((p1 - p0) / hours * 100, 1) if hours else None})
    return rows


def dose(d: pd.DataFrame) -> dict:
    x = d.assign(seg=segment(d)); out = {}
    for s in ("trial", "vendor"):
        e = x[x.seg == s]
        out[s] = {int(k): {"n": int((e.sales_contacts_90d == k).sum()),
                            "rate": round(float(e[e.sales_contacts_90d == k].converted_within_90d.mean()), 4)}
                  for k in range(0, 6) if (e.sales_contacts_90d == k).sum() >= 8}
    return out


t = pd.read_csv(ROOT / "data/training_data.csv", parse_dates=["snapshot_date"])
t = t[(TODAY - t.snapshot_date).dt.days >= 90].sort_values("snapshot_date").reset_index(drop=True)
train, test = t.iloc[:-300], t.iloc[-300:]
cuts = {"train": uplift_table(train), "test": uplift_table(test), "all": uplift_table(t)}
order = {k: [r["segment"] for r in sorted(v, key=lambda r: -r["uplift_pts"])] for k, v in cuts.items()}
top_stable = len({o[0] for o in order.values()}) == 1
by_seg = {s: [next(r["uplift_pts"] for r in v if r["segment"] == s) for v in cuts.values()] for s in SEGMENTS}
skip_segments = [s for s, u in by_seg.items() if all(x <= 0 for x in u)]            # calling never helped, on any cut
positive_segments = [s for s, u in by_seg.items() if all(x > 0 for x in u)]         # calling helped on every cut
unstable = [s for s in SEGMENTS if s not in skip_segments and s not in positive_segments]
z = norm.ppf(.975) + norm.ppf(.8)
power = {f"{int(p0*100)}->{int(p1*100)}": int(np.ceil(z**2 * (p0 * (1 - p0) + p1 * (1 - p1)) / (p1 - p0)**2))
         for p0, p1 in ((.05, .15), (.05, .10))}
out = {"protocol": "train = oldest labelled rows with closed window (n=%d), test = newest 300; rates estimated per cut; no model fitted" % len(train),
       "bias": "upper bound: reps call accounts that already look better; a segment <= 0 despite that is one where calling does not help",
       "cuts": cuts, "order_by_uplift": order, "top_segment": order["all"][0], "top_segment_stable": top_stable,
       "positive_segments": positive_segments, "skip_segments": skip_segments, "unstable_segments": unstable,
       "uplift_by_segment_train_test_all": by_seg,
       "dose": {"all": dose(t)}, "n_per_group_to_measure_unbiased": power,
       "verdict": (f"top segment '{order['all'][0]}' on every cut; calling never helped {skip_segments} on any cut; "
                   f"{unstable} unstable (small n) -- rank on the top and the skip set, treat the rest as neutral"
                   if top_stable and skip_segments else "NOT stable -- do not rank on this")}
(ROOT / "audit/uplift.json").write_text(json.dumps(out, indent=2))

pd.set_option("display.width", 200)
for k, v in cuts.items():
    print(f"\n── {k} ──")
    print(pd.DataFrame(v)[["segment", "n_uncalled", "rate_uncalled", "n_called", "rate_called", "uplift_pts", "ci95_lo", "ci95_hi", "fisher_p", "uplift_per_hour"]].to_string(index=False))
print("\norder by uplift:", {k: " > ".join(o) for k, o in order.items()})
print("verdict:", out["verdict"])
print("dose (all):", json.dumps(out["dose"]["all"]))
print("to measure unbiased, per group:", power)
print("written: audit/uplift.json")
