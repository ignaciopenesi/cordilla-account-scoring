"""The nodes. Each takes State, adds to it, returns it.

Nodes that cannot run on today's inputs call state.bypass() and say what would unblock
them. They are not stubs and they are not faked -- where part of a node IS computable
today, that part runs and the rest is declared.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

import llm
from pipeline import FEATURES, OUT, ROOT, TODAY, State

CAT = ["account_type", "industry"]
RANGES = {"intent_score": (0, 100), "employee_count": (1, 10_000_000),
          "mql_count_90d": (0, 1000), "trial_active_users": (0, 1_000_000),
          "web_touchpoints_90d": (0, 10_000), "sales_contacts_90d": (0, 1000)}

# The one place hours enter the system. It is a PARAMETER, not a finding: Cordilla logs
# contacts, not time, so every ratio below is computed per contact and converted here.
# It cancels out of every arm-vs-arm comparison — both sides carry the same constant —
# so no decision in this pipeline turns on its value. Replace it with measured call
# duration the day the telephony log is joined in, and nothing else changes.
CONTACT_MINUTES = 12

# Default arm sizes, set by recall on the held-out 300 (audit/heldout_comparison.py): of the 23
# buyers, exploit 60 / explore 0 finds 12 and exploit 50 / explore 10 finds the same 12 -- the
# ten explore slots cost nothing, because exploit's slots 51-60 held no buyer. 40/20 found 9.
# Explore is kept at 10 as an exploration QUOTA, not as a branch competing on historical recall:
# history contains no calls to untouched accounts, so it cannot score calling them; only the
# day-90 readout can. The model is worse than random on that pool (AUC 0.45); web is the only
# column that ranks it (AUC 0.61) and explore already uses it -- there is no better data branch.
ARM_DEFAULTS = {"continue": 45, "first-call": 15, "control": 30}   # control size is informational: control is the coin-flipped third
SYSTEM_SHARE = 2 / 3      # of the batch, at random, before any rule runs; the rest is the rep's as usual


# ═════════════════════════════════════════════════════════════════════════════
def INGEST(s: State) -> State:
    """Load everything. One place where data enters, so the rest of the graph never
    changes when the source does -- today CSVs, tomorrow Salesforce."""
    OUT.mkdir(exist_ok=True)          # VERDICT writes here before EMIT does
    s.accounts = pd.read_csv(ROOT / "data/accounts_to_score.csv", parse_dates=["snapshot_date"])
    s.training = pd.read_csv(ROOT / "data/training_data.csv", parse_dates=["snapshot_date"])
    with open(ROOT / "model/model.pkl", "rb") as f:
        s.model = pickle.load(f)

    # Capabilities are what is actually wired up. The bypasses below read this.
    s.capabilities = {"crm_accounts", "labeled_history", "scoring_model"}

    if s.args.demo:
        s.capabilities.add("outcomes_90d")       # SIMULATED, see READOUT -- the shape of day 90, not its answer

    s.say(f"  {len(s.accounts)} accounts to score, {len(s.training)} labeled rows")
    s.say(f"  capabilities wired: {', '.join(sorted(s.capabilities))}")
    s.say("  NOT wired: outcomes_90d (arrive at day 90)" if not s.has("outcomes_90d")
          else "  outcomes_90d SIMULATED for the demo — the readout's shape, not Cordilla's answer")
    s.say("  not in this graph, by design: the conversation layer — see extensions/conversation_layer/")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def VALIDATE(s: State) -> State:
    """The gate. Every rule here exists because the audit found the defect it catches.
    Touches nothing in the CRM -- it only decides what the model is allowed to see."""
    df = s.accounts.copy()
    df["age_days"] = (TODAY - df.snapshot_date).dt.days
    reasons = pd.Series([""] * len(df), index=df.index)

    # audit §4.2 — a null in either categorical raises TypeError and kills the whole batch
    for c in CAT:
        bad = df[c].isna()
        reasons[bad] += f"null_{c};"

    # audit §4.2 — out-of-range numerics are accepted, and intent_score = -50 RAISES the score
    for c, (lo, hi) in RANGES.items():
        bad = df[c].notna() & (~df[c].between(lo, hi))
        reasons[bad] += f"out_of_range_{c};"

    # audit §4.2 — unseen categories score silently, with no warning
    for c in CAT:
        known = set(s.training[c].dropna().unique())
        unseen = df[c].notna() & ~df[c].isin(known)
        reasons[unseen] += f"unseen_{c};"

    s.quarantine = df[reasons != ""].assign(quarantine_reason=reasons[reasons != ""])
    s.accounts = df[reasons == ""].copy()

    # audit §3.10 — 101 training labels record "did not convert in 90 days" for accounts
    # that have not had 90 days. The rule that stops it recurring:
    censored = (TODAY - s.training.snapshot_date).dt.days < 90
    if censored.any():
        s.find(what="Training labels are assigned before the 90-day window closes",
               evidence=f"{censored.sum()} of {len(s.training)} rows ({censored.mean():.1%}) are "
                        f"labeled 0 with fewer than 90 days observed; those rows carry 33% more "
                        f"MQLs than the rest (p_BH = 0.027)",
               severity="high", owner="pipeline",
               action="Label = NULL, not 0, when snapshot_date + 90d > today. Re-label the "
                      f"{censored.sum()} affected rows and add the rule to the labeling job.",
               cost="one rule in the labeling job", 
               expect="the next model is not taught that marketing-engaged accounts fail",
               source="VALIDATE")

    n_stale = (s.accounts.age_days > 180).sum()
    s.say(f"  {len(s.accounts)} passed, {len(s.quarantine)} quarantined")
    s.say(f"  staleness: {(s.accounts.age_days > 90).sum()} over 90d, {n_stale} over 180d "
          f"(features are 90-day windows)")
    if n_stale:
        s.find(what="Accounts are being scored on information older than the feature window",
               evidence=f"{n_stale} of {len(s.accounts)} scoring accounts have a snapshot over "
                        f"180 days old; {(s.accounts.age_days > 90).sum()} are over 90 days, and "
                        f"every feature is a 90-day window",
               severity="high", owner="crm",
               action="Flag it on the row, do not block it — working hypothesis: still actionable. "
                      "READOUT compares stale vs fresh conversion within each arm; if stale loses, "
                      "the flag becomes a filter.",
               cost="enrichment refresh on ~1/3 of the batch",
               expect="reps stop calling a description of a company from two quarters ago",
               source="VALIDATE")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def SCORE(s: State) -> State:
    """The pickle scores. Required by the brief -- and deliberately just one input here.

    The audit (§2) showed this ranking is indistinguishable from noise in-sample and below
    chance forward in time. So the score is never shown to a rep and never sorts the list
    on its own. It earns its place in RECONCILE, as one voice of three."""
    s.accounts["p"] = s.model.predict_proba(s.accounts[FEATURES])[:, 1]
    s.accounts["p_rank"] = s.accounts.p.rank(ascending=False, method="first")
    p = s.accounts.p
    s.say(f"  scored {len(s.accounts)}: {p.min():.3f}–{p.max():.3f}, sum {p.sum():.1f} expected")
    s.artifacts["sum_p"] = float(p.sum())
    s.artifacts["mean_p"] = float(p.mean())

    s.find(what="The model's own arithmetic promises more conversions than the business sees",
           evidence=f"predicted probabilities sum to {p.sum():.1f} conversions across "
                    f"{len(p)} accounts ({p.mean():.2%}), against a field rate the brief puts "
                    f"at 1-3% (i.e. 3-9 conversions)",
           severity="high", owner="model",
           action="Do not publish probabilities to any user or Salesforce field. Use the score "
                  "only for the disagreement analysis in RECONCILE.",
           cost="0 — a policy",
           expect="nobody forecasts off a number that is 2-6x the observed rate",
           source="SCORE")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def PROVE(s: State) -> State:
    """What the score has to beat. A score with nothing to compare against means nothing --
    and audit §2.4/§2.6 showed a one-line sort beats this model where it counts.

    Two comparisons. On the 300 (no outcomes): how much the model's list and the contact
    rule overlap. On the 1,200 labelled rows (real outcomes): build each policy's list of
    90 and count how many actually converted. The model is scored two ways -- from memory
    (in-sample, what a dashboard would show) and out-of-fold (audit/oof_predictions.npy,
    what it knows about rows it never saw). The gap between those two numbers is the
    previous scoring effort's whole story."""
    a, t = s.accounts, s.training
    a["rank_contacts"] = (a.sales_contacts_90d + 1e-9 * np.arange(len(a))).rank(ascending=False, method="first")
    a["rank_random"] = pd.Series(np.random.default_rng(42).permutation(len(a)) + 1, index=a.index)

    top_model = set(a.nsmallest(30, "p_rank").account_id)
    top_rule = set(a.nsmallest(30, "rank_contacts").account_id)
    overlap = len(top_model & top_rule)
    s.artifacts["top30_overlap_model_vs_rule"] = overlap
    s.say(f"  top-30 by model vs top-30 by ORDER BY sales_contacts: {overlap}/30 shared")

    # ── real outcomes: each policy's list of K, and how many of them converted ──────────
    oof_path = ROOT / "audit/oof_predictions.npy"
    if not oof_path.exists():
        s.say("  (audit/oof_predictions.npy not found — outcome comparison skipped)")
        return s
    K = 90
    tt = t.copy()
    tt["p_in"] = s.model.predict_proba(tt[FEATURES])[:, 1]
    tt["p_oof"] = np.load(oof_path)
    clean = tt[(TODAY - tt.snapshot_date).dt.days >= 90].copy()      # label window closed
    y, base = clean.converted_within_90d, clean.converted_within_90d.mean()
    C = clean.sales_contacts_90d
    signal = (clean.trial_started == 1) | (clean.mql_count_90d > 0) | (clean.web_touchpoints_90d >= 4)
    seg = pd.Series(segment_of(clean), index=clean.index)
    seg_rank = seg.map({"trial": 0, "vendor": 1, "none": 2, "mql": 3, "web": 4})
    ex_pool = clean[C.between(1, 4) & ~seg.isin(["mql", "web"])].assign(_sr=seg_rank).sort_values(
        ["_sr", "sales_contacts_90d", "account_id"], ascending=[True, False, True])
    xp_pool = clean[(C == 0) & seg.isin(["trial", "vendor"])].assign(_sr=seg_rank).sort_values(
        ["_sr", "web_touchpoints_90d", "account_id"], ascending=[True, False, True]).head(K)
    policies = {
        "model — in-sample (what a dashboard shows)": clean.nlargest(K, "p_in"),
        "model — out-of-fold (what it actually knows)": clean.nlargest(K, "p_oof"),
        "graph continue (1-4 contacts: trial > vendor > none)": ex_pool.head(K),
        "graph first-call (untouched trial, then vendor)": xp_pool,
        "graph worklist (continue 75 + first-call 15)": pd.concat([ex_pool.head(K * 5 // 6), xp_pool.head(K - K * 5 // 6)]),
        "old exploit (ORDER BY contacts, all)": clean.nlargest(K, "sales_contacts_90d"),
        "ask cohort, if called anyway (5+ contacts)": clean[C >= 5].nlargest(K, "sales_contacts_90d"),
    }
    # random = the average of 200 draws, not one lucky or unlucky list
    rng = np.random.default_rng(11)
    rnd = np.array([clean.sample(K, random_state=int(rs)).converted_within_90d.sum()
                    for rs in rng.integers(0, 10**6, 200)])

    def wilson(k, n_, z=1.96):
        ph, d = k / n_, 1 + z**2 / n_
        c = (ph + z**2 / (2 * n_)) / d
        h = z * np.sqrt(ph * (1 - ph) / n_ + z**2 / (4 * n_**2)) / d
        return max(0, c - h), min(1, c + h)

    rows = []
    for name, d in policies.items():
        k, n_ = int(d.converted_within_90d.sum()), len(d)
        lo, hi = wilson(k, n_)
        rows.append({"policy": name, "n": n_, "converted": k, "rate": round(k / n_, 4),
                     "ci95": f"[{lo:.0%}, {hi:.0%}]", "lift": round(k / n_ / base, 2),
                     "recall": round(k / int(y.sum()), 4),
                     "hours_per_converter": round(n_ * CONTACT_MINUTES / 60 / k, 1) if k else None,
                     "contacts_already_sunk": int(d.sales_contacts_90d.sum()),
                     "rep_hours_sunk": round(d.sales_contacts_90d.sum() * CONTACT_MINUTES / 60, 1)})
    worked = clean[C >= 1]
    tk, tn = int(worked.converted_within_90d.sum()), len(worked)
    tlo, thi = wilson(tk, tn)
    lo_r, hi_r = np.percentile(rnd, [5, 95]) / K
    rows.append({"policy": "random (mean of 200 draws)", "n": K, "converted": round(float(rnd.mean()), 1),
                 "rate": round(float(rnd.mean() / K), 4), "ci95": f"5–95%: [{lo_r:.0%}, {hi_r:.0%}]",
                 "lift": round(float(rnd.mean() / K / base), 2),
                 "recall": round(float(rnd.mean() / int(y.sum())), 4),
                 "hours_per_converter": round(K * CONTACT_MINUTES / 60 / float(rnd.mean()), 1),
                 "contacts_already_sunk": int(round(C.mean() * K)),
                 "rep_hours_sunk": round(C.mean() * K * CONTACT_MINUTES / 60, 1)})
    s.artifacts["model_vs_graph_outcomes"] = {"team_today_rate": round(tk / tn, 4), "team_today_ci": f"[{tlo:.0%}, {thi:.0%}]",
                                              "team_today_k": tk, "team_today_n": tn,
                                              "n_clean_rows": int(len(clean)), "base_rate": round(float(base), 4),
                                              "K": K, "rows": rows, "note": "observational — every policy "
                                              "is judged on accounts someone already chose to work this way"}
    upj = ROOT / "audit/uplift.json"
    if upj.exists():
        U = json.loads(upj.read_text()); s.artifacts["uplift"] = U
        s.say(f"\n  uplift by segment (what a call changes; upper bound — reps chose whom to call):")
        tab = pd.DataFrame(U["cuts"]["all"])[["segment", "rate_uncalled", "rate_called", "uplift_pts", "ci95_lo", "ci95_hi", "uplift_per_hour"]]
        tab["rate_uncalled"] = tab.rate_uncalled.map("{:.1%}".format); tab["rate_called"] = tab.rate_called.map("{:.1%}".format)
        s.say("    " + tab.to_string(index=False).replace("\n", "\n    "))
        s.say(f"    {U['verdict']}")
    ho = ROOT / "audit/heldout_comparison.json"
    if ho.exists():
        s.artifacts["heldout"] = json.loads(ho.read_text())
        h = s.artifacts["heldout"]; r60 = {r["policy"]: r for r in h["by_K"]["60"]}
        ex_, gr_, mo_ = (r60[k] for k in r60 if k.startswith("continue alone")), (r60[k] for k in r60 if k.startswith("THE GRAPH")), (r60[k] for k in r60 if "out-of-fold" in k)
        ex_, gr_, mo_ = next(ex_), next(gr_), next(mo_)
        s.say(f"\n  held-out test — the {h['test_n']} most recent labelled accounts, none seen by any method, K=60:")
        s.say(f"    continue alone {ex_['precision']:.1%} (recall {ex_['recall']:.0%}) · the graph {gr_['precision']:.1%} "
              f"(recall {gr_['recall']:.0%}) · model out-of-fold {mo_['precision']:.1%} (recall {mo_['recall']:.0%})")
        s.say(f"    first-call's historical rate is the rate of accounts nobody called — history cannot value it; the arm can")
    tab = pd.DataFrame(rows)[["policy", "converted", "rate", "recall", "hours_per_converter", "ci95", "contacts_already_sunk"]]
    tab["rate"] = tab.rate.map("{:.1%}".format); tab["recall"] = tab.recall.map("{:.0%}".format)
    s.say(f"\n  on {len(clean)} labelled rows ({int(y.sum())} converters, base {base:.1%}), each policy picks {K}:")
    s.say(f"  rate = of the {K} you call, how many convert · recall = of the {int(y.sum())} who converted, how many you found")
    s.say("    " + tab.to_string(index=False).replace("\n", "\n    "))
    mem, oof = rows[0], rows[1]
    s.say(f"  the team today — accounts it chose to work (≥1 contact): {tk}/{tn} = {tk / tn:.1%}")
    s.say(f"\n  the model from memory: {mem['rate']:.1%}. The model on rows it never saw: {oof['rate']:.1%}.")
    s.say(f"  That gap is the previous scoring effort — 'promising in testing, lost credibility in the field'.")
    s.find(what="The model's dashboard number is memory, not prediction",
           evidence=f"on {len(clean)} labelled rows, the model's top-{K} converts at {mem['rate']:.1%} when "
                    f"it scores rows it was trained on and {oof['rate']:.1%} when it scores rows it never "
                    f"saw (out-of-fold) — against a {base:.1%} base and {rows[-1]['rate']:.1%} for a random "
                    f"list (mean of 200). The graph's worklist converts at {rows[4]['rate']:.1%} with "
                    f"{rows[4]['contacts_already_sunk']} contacts already sunk vs {rows[5]['contacts_already_sunk']} "
                    f"for the old contact sort at the same rate",
           severity="high", owner="model",
           action="Never show an in-sample rate to anyone. Every number about this model that reaches a "
                  "manager comes from out-of-fold or forward-in-time scoring, and says which.",
           cost="0 — the OOF scores exist; it is a rule about which column to read",
           expect="the VP sees 6.7%, not 31%, and asks the right question",
           source="PROVE")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def CLEAN(s: State) -> State:
    """The purity agent. Every column is asked three questions on the OLDER labelled rows only
    (leak-free): does it separate converters? is it clean? is it redundant? The answers decide
    which columns RANK is allowed to use, and the rep sees the row-level flags instead of a score.

    Findings here change the decision, not just a report: a column that fails stays out of the
    ranking. Today that is the vendor's intent VALUE (flat by quintile), MQL count, web on its
    own, account_type, industry, employee_count and trial_active_users."""
    a, t = s.accounts, s.training
    # row flags, as before (the rep reads these)
    a["f_no_vendor_record"] = a.intent_score.isna()
    a["f_stale_180"] = a.age_days > 180
    a["f_never_touched"] = a.sales_contacts_90d == 0
    a["f_over_invested"] = a.sales_contacts_90d >= 5
    flagcols = [c for c in a.columns if c.startswith("f_")]
    a["n_flags"] = a[flagcols].sum(axis=1)
    a["flags"] = a[flagcols].apply(lambda r: ", ".join(c[2:].replace("_", " ") for c in flagcols if r[c]) or "—", axis=1)
    for c in flagcols:
        s.say(f"  {c[2:]:<18} {int(a[c].sum()):3d}")
    s.artifacts["clean_in_top30"] = int((a.nsmallest(30, "p_rank").n_flags == 0).sum())

    # variable scorecard on the older labelled rows -- never on the newest 300
    from sklearn.metrics import roc_auc_score
    clean = t[(TODAY - t.snapshot_date).dt.days >= 90].sort_values("snapshot_date")
    train = clean.iloc[:-300] if len(clean) > 300 else clean
    y = train.converted_within_90d
    def auc(x):
        x = x.fillna(x.median()) if x.dtype != object else x
        return float(roc_auc_score(y, x)) if x.nunique() > 1 else 0.5
    rows = []
    checks = {
        "sales_contacts_90d": ("effort, not intent -- but the only column with a stable interaction", "yes: bands 0 / 1-4 / 5+"),
        "trial_started": ("the strongest interaction: 5% untouched -> 15% with 1-4 contacts", "yes: defines the top segment"),
        "trial_active_users": ("0-user trials convert like live ones; the field is ambiguous", "no"),
        "mql_count_90d": ("MQL-only accounts: 0 of 105 converted; adding MQL>0 to a rule made it worse", "only to define skip"),
        "web_touchpoints_90d": ("web-only with 1-4 contacts: 0 of 72; 0 may mean 'not measured'", "only to define skip; ranks untouched (AUC 0.61)"),
        "intent_score (value)": ("flat by quintile among covered: 9.0 / 5.3 / 12.8 / 7.6 / 9.8", "no"),
        "intent_score (present)": ("coverage separates: ~8% vs ~4%; with 1-4 contacts and no trial, 8.3% vs 2.7%", "yes: defines the vendor segment"),
        "employee_count": ("no separation", "no"),
        "account_type": ("the three types convert identically (chi2 p=0.84); 'Suspect' is our hypothesis, unverified by the brief", "no"),
        "industry": ("range 5.5%-8.5%, not usable", "no"),
        "model score": ("out-of-fold AUC 0.58; adds nothing on top of the rules, tested three ways", "no -- one voice in RECONCILE"),
    }
    for col, (note, used) in checks.items():
        if col == "intent_score (value)":
            x = train.intent_score; sep = auc(x)
        elif col == "intent_score (present)":
            sep = auc(train.intent_score.notna().astype(int))
        elif col == "model score":
            sep = 0.576
        elif col in ("account_type", "industry"):
            g = train.groupby(col).converted_within_90d.mean(); sep = None
            note = f"{note} (rates {g.min():.1%}-{g.max():.1%})"
        else:
            sep = auc(train[col])
        rows.append({"variable": col, "auc_alone": round(sep, 3) if sep is not None else None,
                     "missing": f"{train[col].isna().mean():.0%}" if col in train else "—",
                     "note": note, "used_in_ranking": used})
    s.artifacts["variable_scorecard"] = rows
    used = [r["variable"] for r in rows if r["used_in_ranking"].startswith("yes")]
    s.say(f"\n  variable scorecard on {len(train)} older rows: every column alone is AUC 0.50-0.56")
    s.say(f"  RANK may use: {', '.join(used)} -- everything else is reported and given no weight")
    s.artifacts["hygiene_batch_note"] = llm.draft(
        "hygiene_batch", mode=s.args.llm, defect="columns that carry no information are in the model",
        rule="a column enters the ranking only if it separates converters on held-out rows and means what it says",
        count=f"{len(rows) - len(used)} of {len(rows)} columns excluded", examples="intent_score value, mql_count_90d, account_type",
        correction="report them on the row; give them no weight")
    return s


# ═════════════════════════════════════════════════════════════════════════════
SEGMENTS = ["trial", "vendor", "none", "mql", "web"]


def segment_of(d: pd.DataFrame) -> np.ndarray:
    """The intent axis. Order matters: an account with a trial is 'trial' whatever else it has."""
    return np.select([d.trial_started == 1, d.intent_score.notna(), d.web_touchpoints_90d >= 4, d.mql_count_90d > 0],
                     ["trial", "vendor", "web", "mql"], "none")


def RANK(s: State) -> State:
    """Where does the next hour change the outcome most? Every account gets a cell -- intent
    segment x contact band -- and the cell's evidence from audit/uplift.json, estimated on the
    OLDER labelled rows only. From that, an action:

      first-call   untouched, segment with positive uplift on every cut (trial, then vendor):
                   the first call is where history says an hour changes most (+10 pts for trial,
                   an upper bound). Half are called, half observed, so day 90 measures it unbiased.
      continue     1-4 contacts, segment not in the skip set: trial > vendor > none, most
                   contacts first. This is the ranking that found 12 of 23 buyers held-out.
      ask          5+ contacts: the rep answers one question before the next hour.
      skip         web-only or MQL-only, any contacts: calling never helped on any cut.
      neutral      untouched with no signal: history is silent; control decides.

    The model's score is not used here -- tested as a ranker, an addition and a tiebreaker."""
    a = s.accounts
    up = ROOT / "audit/uplift.json"
    U = json.loads(up.read_text()) if up.exists() else {}
    positive, skip = U.get("positive_segments", ["trial", "vendor"]), U.get("skip_segments", ["mql", "web"])
    train_rows = {r["segment"]: r for r in U.get("cuts", {}).get("train", [])}

    a["segment"] = segment_of(a)
    C = a.sales_contacts_90d
    band = np.select([C == 0, C <= 4], ["0", "1-4"], "5+")
    a["cell"] = [f"{sg}|{b}" for sg, b in zip(a.segment, band)]
    seg_rank = {sg: i for i, sg in enumerate(["trial", "vendor", "none", "mql", "web"])}

    def action(r):
        if r.segment in skip:
            return "skip"
        if r.sales_contacts_90d >= 5:
            return "ask"
        if r.sales_contacts_90d == 0:
            return "first-call" if r.segment in positive else "neutral"
        return "continue"
    a["action"] = a.apply(action, axis=1)
    # the evidence behind each row: uplift of the first call (0 contacts) or the rate in conversation (1-4)
    a["evidence_pts"] = [
        (train_rows.get(sg, {}).get("uplift_pts") if b == "0" else
         round(100 * train_rows.get(sg, {}).get("rate_called", float("nan")), 1) if b == "1-4" else None)
        for sg, b in zip(a.segment, band)]
    a["seg_rank"] = a.segment.map(seg_rank)
    # one order over the 300, by action then by evidence -- this is ranked.csv
    act_rank = {"first-call": 0, "continue": 1, "ask": 2, "neutral": 3, "skip": 4}
    a["rank_pos"] = a.assign(_ar=a.action.map(act_rank)).sort_values(
        ["_ar", "seg_rank", "sales_contacts_90d", "web_touchpoints_90d", "account_id"],
        ascending=[True, True, False, False, True]).reset_index().reset_index().set_index("index")["level_0"].reindex(a.index) + 1

    counts = a.action.value_counts()
    s.say("  " + " · ".join(f"{k} {int(counts.get(k, 0))}" for k in ["first-call", "continue", "ask", "neutral", "skip"]))
    s.say(f"  first-call by segment: {a[a.action == 'first-call'].segment.value_counts().to_dict()} "
          f"· continue by segment: {a[a.action == 'continue'].segment.value_counts().to_dict()}")
    s.say(f"  skip holds {int(a[a.action == 'skip'].sales_contacts_90d.sum())} contacts already sunk "
          f"({a[a.action == 'skip'].sales_contacts_90d.sum() * CONTACT_MINUTES / 60:.0f} rep-h) on segments where calling never helped")
    if U:
        s.say(f"  evidence: {U['verdict']}")
    s.artifacts["rank"] = {"positive_segments": positive, "skip_segments": skip, "actions": counts.to_dict(),
                           "uplift_verdict": U.get("verdict", "audit/uplift.json missing")}
    return s


# ═════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════
def RECONCILE(s: State) -> State:
    """Two voices today -- the model's score and the team's own logged effort -- and where they
    disagree. A third voice, the prospect's own words, is designed and measured but not wired:
    see extensions/conversation_layer/.

    Three voices per account: the model, our own effort, and what the prospect said.
    Where they agree, nothing is learned. Where they disagree IS the new data.

    PARTIAL TODAY: two of the three voices exist."""
    a = s.accounts
    q_hi, q_lo = a.p.quantile(0.75), a.p.quantile(0.25)

    a["disagreement"] = np.select(
        [(a.p >= q_hi) & (a.sales_contacts_90d == 0),
         (a.p <= q_lo) & (a.sales_contacts_90d >= 3),
         (a.p >= q_hi) & (a.sales_contacts_90d >= 5)],
        ["model_high_nobody_looked", "rep_insists_model_low", "high_effort_no_result"],
        default="")
    counts = a.disagreement.value_counts().drop("", errors="ignore")
    for k, v in counts.items():
        s.say(f"  {v:3d}  {k}")

    # Where the two voices disagree and the rep is one of them, ask the rep. This is the
    # disagreement_question agent's contract; the answer is data nobody has today.
    ex = a[a.disagreement == "rep_insists_model_low"].head(1)
    if len(ex):
        r = ex.iloc[0]
        s.artifacts["example_question"] = llm.draft(
            "disagreement_question", mode=s.args.llm,
            account_id=r.account_id, score=f"{r.p:.1%}",
            percentile=f"{100 * (1 - r.p_rank / len(a)):.0f}th",
            contacts=int(r.sales_contacts_90d), flags=r.flags,
            disagreement_kind="rep insists, model low")
        print(s.artifacts["example_question"])

    return s


# ═════════════════════════════════════════════════════════════════════════════
def VALUE(s: State) -> State:
    """What did this run buy, in the unit the SDR manager actually spends?

    The scarce resource is rep hours, so every number here has hours in it. The node is
    in three parts, and they mature at three different speeds -- which is the whole
    design, because reporting a fast number as though it were a slow one is how the
    previous scoring effort lost its credibility.

      A · THE PRICE OF A CONVERSION   runs on the CSVs alone, today
      C · THE BETS                    every hours claim, with the date it gets settled
      (B, a ledger of decisions the prospect's own words changed, is designed and measured
       on synthetic transcripts -- extensions/conversation_layer/ -- and not wired here.)

    Accuracy is not value. An extractor at 100% is worth nothing if it never contradicts
    what the team was already going to do. And a decision changed is not a decision
    improved -- that distinction is part C's entire job."""
    _hours_economics(s)                      # A
    _metric_contract(s)                      # C
    return s


# ── A ────────────────────────────────────────────────────────────────────────
def _hours_economics(s: State) -> State:
    """What an hour of outreach costs and buys today, from the two CSVs.

    This is the baseline the system has to beat, and it needs no transcripts, no
    outcomes and no model -- so unlike the rest of VALUE it runs on every run."""
    t, a = s.training, s.accounts
    spent, conv = int(t.sales_contacts_90d.sum()), int(t.converted_within_90d.sum())
    price = spent / conv
    s.say(f"  the price of a conversion, as the business runs today:")
    s.say(f"    {spent:,} logged contacts → {conv} conversions = {price:.1f} contacts per conversion")
    s.say(f"    at {CONTACT_MINUTES} min per logged contact that is "
          f"{price * CONTACT_MINUTES / 60:.1f} rep-hours per conversion")

    # Where this quarter's hours are going, in the batch we were handed.
    batch = int(a.sales_contacts_90d.sum())
    heavy = a[a.sales_contacts_90d >= 4]
    s.say(f"\n  where the batch's hours are:")
    s.say(f"    {batch} contacts logged across {len(a)} accounts")
    s.say(f"    {len(heavy)} accounts (of {len(a)}) hold {int(heavy.sales_contacts_90d.sum())} of them "
          f"— {heavy.sales_contacts_90d.sum() / batch:.0%} of the effort on "
          f"{len(heavy) / len(a):.0%} of the accounts")

    # The stock of effort that has already gone into accounts that never paid out.
    dead = t[(t.sales_contacts_90d >= 4) & (t.converted_within_90d == 0)]
    stock = int(dead.sales_contacts_90d.sum())
    s.say(f"\n  the recoverable stock, measured on history:")
    s.say(f"    {len(dead)} accounts took ≥4 contacts and never converted, absorbing {stock} "
          f"contacts = {stock / spent:.0%} of all effort ever logged")
    s.say(f"    that is a STOCK, not a rate. Clean it once and it shrinks — see the bets below.")

    # ── the demonstration that this cannot be optimised from the data ──────────
    # Two readings of one table, giving opposite policies. Neither is causal.
    MIN_CELL = 50            # below this a cell is one or two conversions of noise
    rows = []
    for k in sorted(t.sales_contacts_90d.unique()):
        d = t[t.sales_contacts_90d == k]
        if len(d) < 5:
            continue
        c, n_ = int(d.converted_within_90d.sum()), len(d)
        rows.append({"contacts": int(k), "accounts": n_, "conversions": c,
                     "conv rate": f"{c / n_:.1%}",
                     # k=0 is not "free", it is not bought with outreach at all
                     "contacts per conversion": "n/a" if k == 0 else (f"{k * n_ / c:.0f}" if c else "—")})
    tab = pd.DataFrame(rows)
    s.say(f"\n  the same table, read two ways:")
    s.say("    " + tab.to_string(index=False).replace("\n", "\n    "))

    # The row that is easy to miss: conversions that cost no outreach at all.
    free = t[(t.sales_contacts_90d == 0) & (t.converted_within_90d == 1)]
    s.say(f"    note the top row: {len(free)} of {conv} conversions ({len(free) / conv:.0%}) "
          f"happened on accounts with ZERO logged contacts.")
    s.say(f"    Whatever outreach policy wins, it is competing against a baseline that already "
          f"converts for free.")

    eligible = [r for r in rows if r["accounts"] >= MIN_CELL and r["contacts"] > 0]
    best_rate = max(eligible, key=lambda r: float(r["conv rate"].rstrip("%")))
    cheap = min(eligible, key=lambda r: int(r["contacts per conversion"]))
    s.say(f"    · as a RATE  → {best_rate['contacts']} contacts converts best "
          f"({best_rate['conv rate']}). Policy: call more.")
    s.say(f"    · as a COST  → {cheap['contacts']} contact is cheapest "
          f"({cheap['contacts per conversion']} per conversion). Policy: never call twice.")
    s.say(f"    Same 1,200 rows, opposite policies, and neither is causal: reps keep dialling")
    s.say(f"    accounts that are going well and drop the ones that die, so contact count is an")
    s.say(f"    EFFECT of intent as much as a cause of conversion.")

    s.artifacts["hours_economics"] = {
        "contacts_per_conversion": round(price, 1),
        "rep_hours_per_conversion": round(price * CONTACT_MINUTES / 60, 1),
        "minutes_per_contact_assumed": CONTACT_MINUTES,
        "batch_contacts": batch,
        "batch_concentration": {"accounts_ge_4_contacts": int(len(heavy)),
                                "contacts_they_hold": int(heavy.sales_contacts_90d.sum()),
                                "share_of_batch_effort": round(
                                    float(heavy.sales_contacts_90d.sum() / batch), 3)},
        "recoverable_stock_contacts": stock,
        "yield_curve": rows,
    }

    s.find(what="Conversions per hour cannot be estimated from this data at all — only randomised",
           evidence=f"the same yield curve says 'call more' read as a rate ({best_rate['contacts']} "
                    f"contacts converts at {best_rate['conv rate']} vs {conv / len(t):.1%} base) and "
                    f"'never call twice' read as a cost ({cheap['contacts per conversion']} contacts "
                    f"per conversion at {cheap['contacts']} vs "
                    f"{best_rate['contacts per conversion']} at {best_rate['contacts']}), both on cells of "
                    f"{MIN_CELL}+ accounts. Contact count is confounded with the intent the rep "
                    f"already observed, so every observational estimate of hours-ROI is uninterpretable",
           severity="high", owner="process",
           action="Do not compute or report conversions-per-hour from historical CRM data, in any "
                  "cut. The arms in BUDGET are the measuring instrument, not a side experiment: "
                  "randomised assignment is the only thing that makes the denominator readable.",
           cost="0 — it is a decision not to publish a number that is already being computed",
           expect="the team stops justifying effort with a statistic that rises because effort was "
                  "spent, which is the mechanism that killed the previous scoring effort",
           source="VALUE")
    return s


# ── C ────────────────────────────────────────────────────────────────────────
def _n_per_arm(p0: float, rel_lift: float, alpha=0.05, power=0.80) -> int:
    """Accounts per arm to detect a relative lift on a proportion. Two-sided, unpooled.

    Written out rather than imported so the number in the brief can be checked by hand."""
    from scipy.stats import norm
    p1 = p0 * (1 + rel_lift)
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    return int(np.ceil(z**2 * (p0 * (1 - p0) + p1 * (1 - p1)) / (p1 - p0) ** 2))


def _metric_contract(s: State) -> State:
    """The metric this system reports, and the rules that stop it being misread.

    Two numbers, and the hierarchy between them is structural rather than typographic:
    the fast number is printed as a BET with the date it gets settled and the result that
    falsifies it. You cannot read it as an outcome, because it states what outcome it is
    predicting. The previous scoring effort had no such record, which is why nobody could
    write up why it stopped working."""
    ARM, CYCLES_PER_QUARTER = min(ARM_DEFAULTS.values()), 13     # power is set by the smallest arm
    eco = s.artifacts["hours_economics"]
    base_field, base_train = 0.03, float(s.training.converted_within_90d.mean())

    n_field = _n_per_arm(base_field, 0.50)
    n_train = _n_per_arm(base_train, 0.50)
    weeks_at_30 = int(np.ceil(n_field / ARM))
    arm_for_2q = int(np.ceil(n_field / (2 * CYCLES_PER_QUARTER)))

    s.say(f"\n  ── the metric contract ──")
    s.say(f"  NORTH STAR   conversions per 100 contacts, by arm, read cumulatively")
    s.say(f"    to detect a 50% relative lift needs {n_train:,} accounts per arm at the "
          f"{base_train:.1%} training rate,")
    s.say(f"    {n_field:,} at the {base_field:.0%} rate the business reports. At {ARM} per cycle in the "
          f"smallest arm that is")
    s.say(f"    {weeks_at_30} weeks — {weeks_at_30 / 52:.1f} years. The north star is NOT reachable "
          f"at today's allocation.")
    s.say(f"    Reaching it in two quarters requires {arm_for_2q} accounts per arm per cycle "
          f"({arm_for_2q * 3} of the 300).")
    s.say(f"  WEEKLY       rep-hours held (ask) and not spent (skip) — observable today, on the row")
    s.say(f"    the claim that they convert better elsewhere is a BET with a date, below.")

    settle = TODAY + pd.Timedelta(days=90)
    bets = []
    bets.append({
        "bet": "redirected hours convert better than the hours they replaced",
        "claim": "conversions per 100 rep-hours are higher in the system's two thirds than in the control third, every account counted",
        "settles": f"not before {n_field:,} accounts per arm ({weeks_at_30} weeks at {ARM}/arm, "
                   f"{2 * CYCLES_PER_QUARTER} cycles at {arm_for_2q}/arm)",
        "falsified_if": "the cumulative interval for the system's two thirds sits below the control third's once the halves are "
                        "powered — at which point the system is reallocating hours to worse places",
        "note": "THIS is the one that proves the system works. Nothing before it does.",
    })
    s.artifacts["bets"] = bets
    s.say(f"\n  bets outstanding: {len(bets)}")
    for b in bets:
        s.say(f"    · {b['bet']} — settles {b['settles']}")

    guardrails = [
        {"guardrail": "rep acceptance of the worklist", "must_not": "fall below 65%",
         "why": "adoption is what killed the previous effort, and it fails before any metric moves"},
        {"guardrail": "contacts logged against accounts that stated a decline", "must_not": "rise",
         "why": "the release must actually take effect, not just be recommended"},
        {"guardrail": "conversion of stale vs fresh accounts within each arm",
         "must_not": "diverge — stale converting materially below fresh",
         "why": "the working hypothesis is that a two-quarter-old description is still actionable; "
                "this is where it gets tested, and if it fails the flag becomes a filter"},
        {"guardrail": "never-contacted accounts entering an arm each cycle", "must_not": "fall to zero",
         "why": "exploration going to zero is how the system stops producing unbiased data"},
    ]
    s.artifacts["guardrails"] = guardrails

    s.artifacts["metric_spec"] = {
        "north_star": {
            "metric": "conversions per 100 logged contacts, by arm, cumulative",
            "unit": f"conversions / 100 contacts (× {CONTACT_MINUTES} min = rep-hours)",
            "n_per_arm_for_50pct_lift": {f"at_{base_field:.0%}_field_rate": n_field,
                                         f"at_{base_train:.1%}_training_rate": n_train},
            "weeks_at_current_allocation": weeks_at_30,
            "accounts_per_arm_for_two_quarter_readout": arm_for_2q,
            "readable_today": False,
        },
        "weekly_headline": {
            "metric": "rep-hours held pending a question (ask) and not spent where calling never helped (skip)",
            "status": "observable today, on the row -- a saving, not yet a result",
            "decays_by_design": "the recoverable stock is "
                                f"{eco['recoverable_stock_contacts']} contacts and is spent once; "
                                "a falling number here is the system working, not failing",
        },
        "proxy_validity": {
            "check": "at each 90-day readout, does the weekly headline still track the north star?",
            "rule": "if redirected hours stop predicting conversions per 100 contacts, the weekly "
                    "metric is retired — in the same report, not quietly",
            "why": "nobody ever wrote up why the last scores stopped matching the field. This is "
                   "that writeup, scheduled in advance.",
        },
        "guardrails": guardrails,
        "kill_switch": f"if the system's two thirds' cumulative rate sits below the control third's once both pass "
                       f"{n_field:,} accounts, the reallocation is wrong and the system stops "
                       f"directing hours.",
    }

    if weeks_at_30 > 2 * CYCLES_PER_QUARTER:
        s.find(what="At today's allocation the primary metric never becomes readable",
               evidence=f"detecting a 50% relative lift at the {base_field:.0%} field rate needs "
                        f"{n_field:,} accounts per arm. At {ARM} per arm per weekly cycle that is "
                        f"{weeks_at_30} weeks ({weeks_at_30 / 52:.1f} years) — longer than the "
                        f"previous scoring effort survived before it lost credibility",
               severity="high", owner="process",
               action=f"Assign the whole batch, not a third of it: {arm_for_2q} accounts per arm "
                      f"per cycle ({arm_for_2q * 3} of the 300) makes the readout land in two "
                      f"quarters. If the manager will not commit that volume, say so now and "
                      f"report only the weekly bets — do not promise a lift number that the "
                      f"design cannot deliver.",
               cost="no new rep hours — the same accounts are being worked, they are being "
                    "recorded as assigned rather than left out of the experiment",
               expect="the north star becomes reachable within the horizon anyone will wait, "
                      "instead of being quoted as a plan nobody can hold you to",
               source="VALUE")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def BUDGET(s: State) -> State:
    """Cut RANK's order at the budget and hand out arms and cohorts. Three arms compare
    policies; three cohorts are tracked without being called. Nothing here is a tier: every
    row carries the rule that placed it, and READOUT reads each arm against control.

      first-call  untouched trial (randomised: half called, half -> observe), then untouched vendor
      continue    RANK's 'continue' order: trial > vendor > none, most contacts first
      control     the rep picks -- what happens without the system
      ask         5+ contacts: a question to the rep, not a call
      observe     the randomised-out half of first-call candidates: the unbiased test of uplift
      skip        web-only / MQL-only: calling never helped on any cut; never called, tracked"""
    a = s.accounts
    sizes = _arm_sizes(s)

    # The coin flip comes FIRST. Two thirds of the batch go to the system, one third to the rep,
    # at random -- before any rule looks at any row. Everything the system does (arms, ask, skip,
    # observe) happens inside its two thirds; the rep works the other third as they always have,
    # and nothing from here touches it. That makes the two halves exchangeable, so at day 90
    # "system third vs control third" is a causal comparison of POLICIES, intention-to-treat --
    # including the accounts the system chose not to call. Drawing control from the leftovers
    # after the system had picked, as an earlier version did, compared the system to what it
    # rejected; that is not a control.
    rng = np.random.default_rng(2026)
    a["half"] = np.where(rng.random(len(a)) < SYSTEM_SHARE, "system", "control")
    sys_ = a[a.half == "system"]
    taken = set()

    skip = sys_[sys_.action == "skip"]; taken |= set(skip.account_id)
    ask = sys_[(sys_.action == "ask") & ~sys_.account_id.isin(taken)]; taken |= set(ask.account_id)

    fc_pool = sys_[(sys_.action == "first-call") & ~sys_.account_id.isin(taken)]
    trials = fc_pool[fc_pool.segment == "trial"].sample(frac=1, random_state=11)
    half = len(trials) // 2
    called_trials, observe = trials.iloc[:half], trials.iloc[half:]
    rest_fc = fc_pool[fc_pool.segment != "trial"].sort_values(["seg_rank", "web_touchpoints_90d", "account_id"], ascending=[True, False, True])
    first_call = pd.concat([called_trials, rest_fc]).head(sizes["first-call"])
    taken |= set(first_call.account_id) | set(observe.account_id)

    cont = sys_[(sys_.action == "continue") & ~sys_.account_id.isin(taken)].sort_values(
        ["seg_rank", "sales_contacts_90d", "account_id"], ascending=[True, False, True]).head(sizes["continue"])
    taken |= set(cont.account_id)
    control = a[a.half == "control"]                       # the rep's third: every account, as usual
    idle = sys_[~sys_.account_id.isin(taken)]              # the system's share it chose not to touch this week

    a["arm"] = pd.Series([None] * len(a), index=a.index, dtype="object")
    for name, d in (("continue", cont), ("first-call", first_call), ("control", control),
                    ("ask", ask), ("observe", observe), ("skip", skip), ("idle", idle)):
        a.loc[a.account_id.isin(d.account_id), "arm"] = name
    s.artifacts["arms"] = {"continue": int(len(cont)), "first-call": int(len(first_call)), "control": int(len(control))}
    s.artifacts["cohorts"] = {"ask": int(len(ask)), "observe": int(len(observe)), "skip": int(len(skip)), "idle": int(len(idle))}
    s.artifacts["halves"] = {"system": int(len(sys_)), "control": int(len(control)), "system_share": SYSTEM_SHARE}
    s.artifacts["ask"] = int(len(ask))
    s.artifacts["arm_sizes_requested"] = sizes
    s.artifacts["continue_by_segment"] = {f"1-4 contacts · {sg}": int((cont.segment == sg).sum()) for sg in ["trial", "vendor", "none"]}

    s.say(f"  coin flip first: system {len(sys_)} · control {len(control)} — the rep works the control third as usual; "
          f"nothing here touches it")
    s.say(f"  arms     continue {len(cont)} · first-call {len(first_call)} · control {len(control)} (the whole third)")
    s.say(f"  cohorts  ask {len(ask)} · observe {len(observe)} · skip {len(skip)} · idle {len(idle)}   (inside the system's two thirds, not called this week)")
    s.say(f"  first-call: {len(called_trials)} untouched trials called, {len(observe)} observed — the unbiased test; "
          f"+ {len(first_call) - len(called_trials)} untouched vendor")
    s.say("  continue, by segment: " + " · ".join(f"{k} {v}" for k, v in s.artifacts["continue_by_segment"].items()))
    s.say(f"  continue carries {int(cont.f_over_invested.sum())} over-invested accounts")
    if s.artifacts.get("arm_sizes_source"):
        s.say(f"  arm sizes from {s.artifacts['arm_sizes_source']}")

    _model_vs_us(s)

    arm_block = "\n".join([
        f"- **continue** ({len(cont)} accounts): 1–4 logged contacts, trial > vendor record > no signal, most contacts first",
        f"- **first-call** ({len(first_call)} accounts): never contacted, trial first (half called, half observed — that is how the +10 gets measured for real), then vendor record",
        f"- **control** ({len(control)} accounts, a third of the batch by coin flip): the rep works them as usual — nothing from the system touches them. Day 90 compares the system's third against this one, every account counted",
        f"- **ask** ({len(ask)}, not an arm): 5+ contacts, no result — the rep gets a question",
        f"- **observe** ({len(observe)}, not an arm): the other half of the untouched trials, deliberately not called",
        f"- **skip** ({len(skip)}, not an arm): web-only or MQL-only — calling never helped on any cut",
    ])
    s.artifacts["experiment_card"] = llm.draft(
        "experiment_card", mode=s.args.llm, total=sum(sizes.values()), n_arms=3,
        matched_on="intent segment and contact band", base_rate="6.5% in training, 1-3% per the business", arm_block=arm_block)
    print(s.artifacts["experiment_card"])
    return s


def _model_vs_us(s: State) -> None:
    """The head-to-head, on every run. The model's answer to 'who do I call' is its top 30.
    This is what happens to each of those 30 here, and why -- every reason is a flag or a
    cohort the manager can verify on the row."""
    a = s.accounts
    rank = a.p.rank(ascending=False, method="first").astype(int)
    top = a[rank <= 30].copy(); top["rank"] = rank[top.index]
    def fate(r):
        if r.arm == "ask":
            return "ask, don't call — 5+ contacts, no result, no voice"
        if r.arm == "continue":
            return "continue — called"
        if r.arm == "first-call":
            return "first-call — never contacted, trial or vendor"
        if r.arm == "control":
            return "control third — the rep works it as usual"
        if r.arm in ("skip", "observe", "idle"):
            return f"{r.arm} — tracked, not called"
        return "pool — not drawn this cycle"
    top["fate"] = top.apply(fate, axis=1)
    n_stale_called = int((top.f_stale_180 & top.arm.isin(["continue", "first-call"])).sum())
    counts = top.fate.value_counts()
    s.say("\n  the model's top 30, and what happens to each here:")
    for k, v in counts.items():
        s.say(f"    {v:2d}  {k}")
    called = int(top.arm.isin(["continue"]).sum())
    s.say(f"  → of the 30 the model says to call, {called} are called as-is"
          f"{f' ({n_stale_called} of them flagged stale — hypothesis: still actionable)' if n_stale_called else ''}.")
    s.artifacts["model_vs_us"] = {
        "top30_fates": counts.to_dict(),
        "called_as_is": called, "called_but_stale": n_stale_called,
        "top9": [{"rank": int(r["rank"]), "account_id": r.account_id, "p": round(float(r.p), 4),
                  "contacts": int(r.sales_contacts_90d), "age_days": int(r.age_days),
                  "flags": r["flags"], "fate": r.fate}
                 for _, r in top.sort_values("rank").head(9).iterrows()],
    }


def _arm_sizes(s: State) -> dict:
    """Where the arm sizes come from. READOUT writes next_cycle.json after each readout;
    BUDGET reads it here. No file means the first cycle, and ARM_DEFAULTS applies."""
    sizes = dict(ARM_DEFAULTS)
    path = OUT / "next_cycle.json"
    if path.exists() and not getattr(s.args, "reset_cycles", False):
        try:
            nxt = json.loads(path.read_text())
            if bool(nxt.get("simulated", False)) != bool(getattr(s.args, "demo", False)):
                s.say("  next_cycle.json is from the other mode (simulated ≠ real) — ignored")
                return sizes
            sizes.update({k: int(v) for k, v in nxt.get("arm_sizes", {}).items() if k in sizes})
            s.artifacts["arm_sizes_source"] = (f"next_cycle.json (written by READOUT after cycle "
                                               f"{nxt.get('cycle', '?')}: {nxt.get('reason', '')})")
        except (ValueError, KeyError) as e:
            s.say(f"  ⚠ next_cycle.json unreadable ({e}) — using defaults")
    return sizes


# ═════════════════════════════════════════════════════════════════════════════
def HYGIENE(s: State) -> State:
    """CRM contradictions, as proposals with evidence. Proposes, never executes.

    Every defect here comes with the rule that stops it recurring -- a one-off cleanup is
    worth much less than the rule."""
    a, t = s.accounts, s.training

    # audit §3.9 — WORKING HYPOTHESIS, not a definition from the brief: in the usual funnel,
    # Suspect = fits the profile, has shown nothing; Prospect = has engaged. The exercise names
    # the three values and says the non-customers are "mostly untouched", nothing more. Under
    # that reading 85% of Suspects are mislabelled. Under any reading the field carries no
    # information: conversion is identical across the three types (chi2 p = 0.84).
    susp = a[(a.account_type == "Suspect") &
             ((a.mql_count_90d > 0) | (a.trial_started == 1) | (a.sales_contacts_90d > 0))]
    t_susp = t[(t.account_type == "Suspect") &
               ((t.mql_count_90d > 0) | (t.trial_started == 1) | (t.sales_contacts_90d > 0))]
    if len(susp):
        s.say(f"  {len(susp)} of {(a.account_type == 'Suspect').sum()} scoring 'Suspects' show activity "
              f"({len(t_susp)} of {(t.account_type == 'Suspect').sum()} in training)")
        s.artifacts["hygiene_suspects"] = llm.draft(
            "hygiene_batch", mode=s.args.llm, defect="account_type is stale",
            rule="Suspect with an MQL, a trial, or a logged sales contact",
            count=f"{len(susp)} in the scoring batch, {len(t_susp)} in training history",
            examples=", ".join(susp.account_id.head(3)),
            correction="reclassify to Prospect")
        print(s.artifacts["hygiene_suspects"])
        s.find(what="account_type carries no information — and if 'Suspect' means 'no engagement', it is wrong on 85% of rows",
               evidence=f"the brief lists the three values and does not define them; the usual funnel "
                        f"reading (Suspect = no engagement yet) is OUR hypothesis. Under it, "
                        f"{len(t_susp)} of {(t.account_type=='Suspect').sum()} training 'Suspects' and "
                        f"{len(susp)} of {(a.account_type=='Suspect').sum()} scoring ones are mislabelled — "
                        f"they have an MQL, a trial or a contact. Under ANY reading the field is empty: "
                        f"conversion is identical across the three types (chi2 p = 0.84), model "
                        f"importance 0.003",
               severity="high", owner="crm",
               action=f"First, one question to the CRM owner: what is 'Suspect' supposed to mean? "
                      f"If 'no engagement': bulk-reclassify the {len(susp)} scoring accounts and add a "
                      f"validation rule. If something else: document it, because today the field "
                      f"predicts nothing.",
               cost="one bulk update + one validation rule",
               expect="the VP stops seeing 'Suspects' near the top of a list and losing trust in it",
               source="HYGIENE")

    # audit §3.7 — trial started, nobody ever logged in
    ghost = a[(a.trial_started == 1) & (a.trial_active_users == 0)]
    if len(ghost):
        s.find(what="Trials with zero active users are ambiguous",
               evidence=f"{len(ghost)} scoring accounts started a trial and show 0 active users; "
                        f"in training these convert at 11.0% (8 of 73), better than trials with 1-2 users",
               severity="medium", owner="pipeline",
               action="Ask product whether these are provisioned-but-never-used or missing seat "
                      "telemetry. If telemetry, instrument it — the field is currently unreadable.",
               cost="one question to product; instrumentation if it is the second",
               expect="a real signal becomes readable instead of being two different things in one field",
               source="HYGIENE")

    # audit §3.6 — a zero that might mean "not measured"
    s.find(what="web_touchpoints_90d cannot distinguish 'no visits' from 'not measured'",
           evidence=f"{int((a.web_touchpoints_90d == 0).sum())} scoring accounts show 0; in training, "
                    f"0 converts at 7.4% vs 4.5% for 1-3 (Fisher p = 0.119 — directional, not established)",
           severity="medium", owner="vendor",
           action="Data contract with the attribution vendor: return NULL when no measurement was "
                  "taken. Until then, treat 0 as unknown rather than as a measured zero.",
           cost="a contract change, no engineering",
           expect="a 40%-coverage problem stops being invisible because it looks like data",
           source="HYGIENE")

    # THE blocking one. audit §3.5.
    s.find(what="It is unknown whether sales_contacts_90d precedes the outcome window or overlaps it",
           evidence="sales_contacts_90d is a 90-day count and the label is 'converted within 90 days'. "
                    "Nothing in the files states the relationship. This is the only feature with "
                    "credible signal (OR 2.2 at >=4, robust to every adjustment)",
           severity="blocking", owner="pipeline",
           action="One question to the data owner: does the contact window PRECEDE the snapshot, or "
                  "is it the same 90 days in which conversion is measured? If it overlaps, the one "
                  "signal in this dataset is leakage and nothing built on it is real.",
           cost="one email",
           expect="either the continue arm is justified, or the whole dataset is known to be unusable",
           source="HYGIENE")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def VERDICT(s: State) -> State:
    """Is THIS run worth anything? Run weekly, on the instrument rather than the accounts.

    This is the node that would have caught the previous model dying. It reports nothing
    without a recommendation for this week."""
    a, t = s.accounts, s.training

    def psi(x, y, bins=10):
        e = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
        e[0], e[-1] = -np.inf, np.inf
        px = np.clip(np.histogram(x, e)[0] / len(x), 1e-6, None)
        py = np.clip(np.histogram(y, e)[0] / len(y), 1e-6, None)
        return float(((py - px) * np.log(py / px)).sum())

    psis = {c: psi(t[c].dropna(), a[c].dropna()) for c in FEATURES if c not in CAT}
    worst = max(psis, key=psis.get)
    s.artifacts["psi"] = psis
    s.say(f"  feature PSI vs training: max {psis[worst]:.3f} ({worst}) — "
          f"{'stable' if psis[worst] < 0.1 else 'CHECK'}")

    # week-over-week: the audit showed a third of the top 30 moves on the seed alone
    prev_path = OUT / "last_top30.json"
    top30 = sorted(a.nsmallest(30, "p_rank").account_id.tolist())
    ov = None
    if prev_path.exists():
        blob = json.loads(prev_path.read_text())
        prev_date = blob.get("reference_date") if isinstance(blob, dict) else None
        prev = set(blob.get("top30", []) if isinstance(blob, dict) else blob)
        if prev_date == str(TODAY.date()):
            s.say("  week-over-week overlap: the run on file has the same reference date — this is the first "
                  "week; overlap is tracked from the next one (the audit: a third of the top 30 moves on the seed alone)")
        else:
            ov = len(set(top30) & prev)
            s.say(f"  top-30 overlap with the previous run ({prev_date or 'undated'}): {ov}/30")
    else:
        s.say("  no previous run on file — overlap starts being tracked from next week")
    prev_path.write_text(json.dumps({"reference_date": str(TODAY.date()), "top30": top30}))
    s.artifacts["top30_overlap_prev_run"] = ov

    s.artifacts["run_verdict"] = llm.draft(
        "run_verdict", mode=s.args.llm, date=f"{TODAY:%Y-%m-%d}",
        psi_summary=f"every feature is stable against training (max PSI {psis[worst]:.2f}, {worst})",
        overlap=f"{ov}/30" if ov is not None else "not yet tracked (first week — same reference date on file)",
        concentration=f"the model's top-30 shares only {s.artifacts['top30_overlap_model_vs_rule']}/30 "
                      f"accounts with a plain sort by contact count",
        clean=s.artifacts["clean_in_top30"], sum_p=f"{s.artifacts['sum_p']:.1f}",
        n=len(a), mean_p=f"{s.artifacts['mean_p']:.1%}")
    print(s.artifacts["run_verdict"])

    s.find(what="The model's ranking has never been validated out of sample in production",
           evidence="audit §2: in-sample AUC 0.759 sits at the median of what the same "
                    "architecture scores on random labels (p = 0.575); out-of-fold 0.573; "
                    "forward in time 0.474, below chance",
           severity="high", owner="model",
           action="Re-run the permutation null and the forward-chaining split (audit §2.2, §2.6a) "
                  "whenever the model or the data pipeline changes. No metric gets reported "
                  "without a temporal split — that is how the last one shipped.",
           cost="the notebook, ~4 minutes",
           expect="the next model cannot die quietly the way this one did",
           source="VERDICT")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def PRESCRIBE(s: State) -> State:
    """Findings in, prioritised actions out.

    Nothing reaches the manager as 'this is wrong'. Everything reaches them as 'this is
    wrong, here is who fixes it, here is what it costs, here is what changes'."""
    order = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
    ranked = sorted(s.findings, key=lambda f: (order.get(f.severity, 9), f.owner))
    s.artifacts["actions"] = [f.as_dict() for f in ranked]

    by_owner = {}
    for f in ranked:
        by_owner.setdefault(f.owner, []).append(f)

    s.say(f"  {len(ranked)} findings → actions, by owner:")
    for owner, fs in sorted(by_owner.items()):
        s.say(f"    {owner:<9} {len(fs)}")
    for f in ranked:
        mark = "🛑" if f.severity == "blocking" else "•"
        s.say(f"  {mark} [{f.severity}/{f.owner}] {f.what}")
        s.say(f"      → {f.action.splitlines()[0][:110]}")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def HITL(s: State) -> State:
    """The signature. Agents propose; a human executes.

    One approval point, not ten -- Gartner's finding is that agentic projects fail on
    unclear scope between an agent's ability to act and its access, so this is the only
    place the graph can cause a write."""
    pending = {"arms": s.artifacts.get("arms", {}),
               "actions": len(s.artifacts.get("actions", [])),
               "hygiene_batches": sum(1 for k in s.artifacts if k.startswith("hygiene_"))}
    if s.args.approve:
        s.approvals = {"approved_at_reference_date": str(TODAY.date()),
                       "approved_by": "SDR manager (simulated)", **pending}
        s.say(f"  ✓ approved: {pending}")
        s.say("  CRM writes would now be released (dry run — nothing is actually written)")
    else:
        s.approvals = {"status": "PENDING", **pending}
        s.say(f"  ⏸ awaiting approval: {pending}")
        s.say("  nothing is written to Salesforce. Re-run with --approve to simulate sign-off.")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def EMIT(s: State) -> State:
    """What each audience gets. Note what the rep does NOT get: a score."""
    OUT.mkdir(exist_ok=True)
    a = s.accounts

    ranked = a.sort_values("rank_pos")[["rank_pos", "account_id", "action", "segment", "cell", "evidence_pts", "arm",
                                        "sales_contacts_90d", "trial_started", "age_days", "flags"]]
    ranked.to_csv(OUT / "ranked.csv", index=False)
    # No `arm` column: a rep who knows "this one is the system's" works it harder, and the rate
    # rises for a reason the policy did not earn. They see the action and the reason on the row.
    rep = a[a.arm.isin(["continue", "first-call", "ask"])][
        ["account_id", "arm", "segment", "account_type", "industry", "employee_count",
         "sales_contacts_90d", "age_days", "flags"]].copy()
    rep.insert(1, "action", np.where(rep.arm == "ask", "ask", "call"))
    # The question is the disagreement_question agent's contract, rendered from the row.
    # In live mode that agent drafts it; the template is the documented spot it plugs into.
    rep["question"] = np.where(
        rep.action == "ask",
        "You have logged " + rep.sales_contacts_90d.astype(int).astype(str)
        + " contacts here with no result. What do you know that the data does not — "
          "and is the next hour worth it, or should this one rest?",
        "")
    rep = rep.drop(columns="arm").sort_values(["action", "segment", "account_id"])
    rep.to_csv(OUT / "rep_worklist.csv", index=False)

    dis = a[a.disagreement != ""][["account_id", "disagreement", "sales_contacts_90d", "flags"]]
    dis.to_csv(OUT / "disagreements.csv", index=False)

    pd.DataFrame(s.artifacts["actions"]).to_csv(OUT / "actions.csv", index=False)
    _write_cases(s)

    # markdown table by hand -- tabulate is not in requirements.txt and this is one table
    def md_table(rows, cols):
        head = "| " + " | ".join(cols) + " |"
        rule = "|" + "|".join("---" for _ in cols) + "|"
        body = ["| " + " | ".join(str(r[c]).replace("\n", " ").replace("|", "/") for c in cols) + " |"
                for r in rows]
        return "\n".join([head, rule, *body])

    _write_brief(s, md_table)

    spec, eco = s.artifacts["metric_spec"], s.artifacts["hours_economics"]
    ns, wk = spec["north_star"], spec["weekly_headline"]
    (OUT / "metrics.md").write_text("\n\n".join([
        f"# The metric — run of {TODAY:%Y-%m-%d}",
        "## The scorecard",
        _scorecard_md(s),
        "_Two numbers, and the hierarchy between them is structural rather than typographic. "
        "The fast one is printed as a bet with the date it settles and the result that falsifies "
        "it, so it cannot be read as an outcome. The previous scoring effort had no such record, "
        "which is why nobody could write up why it stopped working._",

        "## What an hour costs today",
        f"- **{eco['contacts_per_conversion']} logged contacts per conversion** "
        f"({eco['rep_hours_per_conversion']} rep-hours at {eco['minutes_per_contact_assumed']} "
        f"min/contact — a parameter, not a finding; it cancels out of every arm-vs-arm comparison)\n"
        f"- **{eco['batch_concentration']['contacts_they_hold']} of {eco['batch_contacts']} contacts "
        f"({eco['batch_concentration']['share_of_batch_effort']:.0%})** sit in "
        f"{eco['batch_concentration']['accounts_ge_4_contacts']} of 300 accounts\n"
        f"- **{eco['recoverable_stock_contacts']} contacts** of historical effort went into accounts "
        f"that never converted — a *stock*, spent once",
        "And the reason none of this can be optimised directly: the same yield curve says "
        "*call more* read as a rate and *never call twice* read as a cost. Contact count is an "
        "effect of intent as much as a cause of conversion, so **no observational cut of this data "
        "yields conversions-per-hour**. The arms are the instrument.",
        md_table(eco["yield_curve"],
                 ["contacts", "accounts", "conversions", "conv rate", "contacts per conversion"]),

        "## 1 · North star — *not readable yet, and that is the honest answer*",
        f"**{ns['metric']}**",
        f"- needs **{max(ns['n_per_arm_for_50pct_lift'].values()):,} accounts per arm** to detect a "
        f"50% relative lift at the field rate ({min(ns['n_per_arm_for_50pct_lift'].values()):,} at "
        f"the training rate)\n"
        f"- at today's {min(ARM_DEFAULTS.values())} per cycle in the smallest arm: **{ns['weeks_at_current_allocation']} weeks**. "
        f"Assigning **{ns['accounts_per_arm_for_two_quarter_readout']} per arm** instead lands it "
        f"in two quarters, with no new rep hours.",

        "## 2 · Weekly headline — *a bet, not a result*",
        f"**{wk['metric']}** — {wk['status']}\n\n- {wk['decays_by_design']}",
        "### Bets outstanding",
        md_table(s.artifacts["bets"], ["bet", "claim", "settles", "falsified_if"]),

        "## Guardrails — what must not get worse while the bets mature",
        md_table(spec["guardrails"], ["guardrail", "must_not", "why"]),

        "## Proxy validity — the writeup nobody did last time",
        f"{spec['proxy_validity']['check']}  \n**Rule:** {spec['proxy_validity']['rule']}",

        "## Kill switch",
        spec["kill_switch"],
    ]))

    sc = s.artifacts["scorecard"]
    g = sc["rows"][3]["hist"][0]; b = [r["hist"][0] for r in sc["rows"][:3] if r["hist"][0] is not None]
    s.say(f"  scorecard             graph {g:.1%} vs best baseline {max(b):.1%} on real outcomes · "
          f"refuses {sc['rows'][3]['refuses_h']:.0f} rep-h/quarter · prospective column: "
          f"{'filled (simulated)' if sc['prospective_simulated'] else 'filled' if sc['prospective_available'] else 'empty until READOUT'}")
    s.say(f"  ranked.csv            all {len(ranked)} accounts: position · action · segment · evidence · arm")
    s.say(f"  rep_worklist.csv      {int((rep.action == 'call').sum())} to call + "
          f"{int((rep.action == 'ask').sum())} to ask, with flags and NO score"
          + f" — no arm column; observe {s.artifacts['cohorts'].get('observe', 0)}, skip {s.artifacts['cohorts'].get('skip', 0)} and the control third absent")
    s.say(f"  disagreements.csv     {len(dis)} accounts where the voices disagree")
    s.say(f"  actions.csv           {len(s.artifacts['actions'])} prescriptions with an owner")
    s.say(f"  manager_brief.md      verdict + experiment card + action table")
    s.say(f"  metrics.md            the metric contract: north star, bets, guardrails, kill switch")
    s.say("  → Salesforce would receive: flags, intent_known, snapshot date. Never the probability.")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def READOUT(s: State) -> State:
    """Day 90. The first honest number Cordilla will have had.

    In --demo this runs on SIMULATED outcomes, drawn from the brief's own field rate with
    NO difference between arms. That is deliberate: the point of the demo is to show the
    shape of the readout and how little 30 accounts per arm can tell you -- not to
    manufacture a result that flatters the design."""
    a = s.accounts
    assigned = a[a.arm.notna()].copy()

    if not s.has("outcomes_90d") or not len(assigned):
        s.bypass(node="READOUT",
                 reason="90-day outcomes for the accounts assigned today do not exist yet",
                 unblocked_by="one cycle of the arms above, with outcomes written back per account",
                 would_produce="conversions per logged contact by arm with confidence intervals; the "
                               "the system's two thirds against the control third, every account counted; "
                               "first-call against observe by segment; and the allocation update -- "
                               "arms move only when intervals separate, never below the floor",
                 still_computed=f"the arms are assigned and recorded: {s.artifacts.get('arms', {})}")
        s.say("  with 30 accounts per arm at ~6%, the first readout will be noisy. It accumulates:")
        s.say("  cycle 1 = 30/arm, cycle 2 = 60, cycle 3 = 90. The point is that it starts.")
        return s

    # SIMULATED. Same rate for every arm -- we are showing the instrument, not the answer.
    TRUE_RATE = 0.03                       # the brief's field rate, not training's 6.5%
    cyc_path = OUT / "cycles.jsonl"
    n_prev = len(cyc_path.read_text().splitlines()) if cyc_path.exists() else 0
    rng = np.random.default_rng(2026 + n_prev)          # a fresh draw per demo cycle
    assigned["converted"] = rng.random(len(assigned)) < TRUE_RATE

    def wilson(k, n_, z=1.96):
        if n_ == 0:
            return (np.nan, np.nan)
        ph, d = k / n_, 1 + z**2 / n_
        c = (ph + z**2 / (2 * n_)) / d
        h = z * np.sqrt(ph * (1 - ph) / n_ + z**2 / (4 * n_**2)) / d
        return max(0, c - h), min(1, c + h)

    rows = []
    for arm, d in assigned.groupby("arm"):
        k, n_ = int(d.converted.sum()), len(d)
        lo, hi = wilson(k, n_)
        rows.append({"arm": arm, "accounts": n_, "conversions": k, "rate": k / n_,
                     "95% CI": f"[{lo:.1%}, {hi:.1%}]",
                     "": {"ask": "← cohort: 5+ contacts, rep asked first", "idle": "← the system's share, not touched this week",
                          "control": "← the rep's third, worked as usual — the comparison that counts",
                          "skip": "← cohort: web/MQL-only, calling never helped", "observe": "← cohort: untouched trials NOT called — the uplift control"}.get(arm, "")})
    tab = pd.DataFrame(rows).set_index("arm")
    s.say("  SIMULATED 90-day readout by arm (there is NO true difference between arms):")
    s.say("    " + tab.to_string().replace("\n", "\n    "))
    s.artifacts["readout"] = tab.reset_index().to_dict("records")
    tab = tab[~tab.index.isin(["ask", "skip", "observe", "idle"])]   # the spread compares policies; cohorts are not


    # THE policy comparison: the system's third against the control third, every account counted
    # (intention-to-treat), because the coin flip made them exchangeable.
    if "half" in assigned:
        hs, hc = assigned[assigned.half == "system"], assigned[assigned.half == "control"]
        ks, ns, kc, nc = int(hs.converted.sum()), len(hs), int(hc.converted.sum()), len(hc)
        if ns and nc:
            ps, pc = ks / ns, kc / nc
            se = float(np.sqrt(ps * (1 - ps) / ns + pc * (1 - pc) / nc))
            s.say(f"  POLICY, causal — the system's two thirds vs the control third, intention-to-treat:")
            s.say(f"    system  {ks}/{ns} = {ps:.1%}   control  {kc}/{nc} = {pc:.1%}   difference {100 * (ps - pc):+.1f} pts  "
                  f"95% [{100 * (ps - pc - 1.96 * se):+.1f}, {100 * (ps - pc + 1.96 * se):+.1f}]")
            s.say(f"    incremental conversions this cycle: {ks - pc * ns:+.1f} — the number the VP repeats, once the interval excludes zero")
            if getattr(s.args, "demo", False) and (ps - pc - 1.96 * se) > 0:
                s.say("    ⚠ SIMULATED with NO true difference — and the interval excludes zero anyway. This is what a false")
                s.say("      positive looks like at one cycle of ~300. It is why the readout dates are fixed in advance and")
                s.say("      why nothing is read before the pre-registered n. Do not repeat this number.")
            s.artifacts["policy_readout"] = {"system": {"k": ks, "n": ns}, "control": {"k": kc, "n": nc},
                                             "diff_pts": round(100 * (ps - pc), 1),
                                             "ci95": [round(100 * (ps - pc - 1.96 * se), 1), round(100 * (ps - pc + 1.96 * se), 1)],
                                             "incremental_conversions": round(ks - pc * ns, 2)}
    fc, ob = assigned[assigned.arm == "first-call"], assigned[assigned.arm == "observe"]
    if len(fc) and len(ob):
        rows_u = []
        for sg in sorted(set(fc.segment) | set(ob.segment)):
            c, o = fc[fc.segment == sg], ob[ob.segment == sg]
            if len(c) and len(o):
                rows_u.append({"segment": sg, "called": f"{int(c.converted.sum())}/{len(c)}", "observed": f"{int(o.converted.sum())}/{len(o)}",
                               "uplift_real_pts": round((c.converted.mean() - o.converted.mean()) * 100, 1)})
        if rows_u:
            s.say("  day-90 uplift, UNBIASED — first-call (called) vs observe (not called), by segment:")
            s.say("    " + pd.DataFrame(rows_u).to_string(index=False).replace("\n", "\n    "))
            s.say("    (this is the column the audit's +10 upper bound gets replaced by; n is small until it accumulates)")
            s.artifacts["uplift_day90"] = rows_u
    if "f_stale_180" in assigned and assigned.f_stale_180.any():
        sv = assigned[assigned.arm.isin(["continue", "first-call", "control"])].groupby("f_stale_180").converted.agg(
            accounts="size", conversions="sum")
        sv.index = sv.index.map({True: "stale (>180d)", False: "fresh"})
        s.say("  stale vs fresh within the arms — the 'still actionable' hypothesis, being tested:")
        s.say("    " + sv.to_string().replace("\n", "\n    "))
        s.artifacts["stale_hypothesis"] = sv.reset_index().to_dict("records")

    _settle_bets(s, assigned)

    rates = tab["rate"]
    spread = rates.max() - rates.min()
    s.say(f"\n  observed spread between arms: {spread:.1%} — and the true difference is ZERO by")
    s.say("  construction. With 30 accounts per arm at a 3% rate, that is what noise looks like.")
    s.find(what="One cycle of 30 accounts per arm cannot resolve a realistic difference",
           evidence=f"simulated at the brief's 1-3% field rate with NO true difference between arms, "
                    f"the observed spread is {spread:.1%} and every confidence interval overlaps "
                    f"every other. Detecting a 50% relative lift at this base rate needs roughly "
                    f"1,500 accounts per arm",
           severity="high", owner="process",
           action="Run the arms continuously and read cumulatively, not once. Commit to the cycle "
                  "for at least two quarters before drawing a conclusion, and say so up front so "
                  "nobody reads cycle 1 as an answer.",
           cost="patience, and saying this to the VP before the first readout rather than after",
           expect="nobody kills or ships the approach on a number that cannot support either",
           source="READOUT")
    _learn(s, assigned)
    return s


# ═════════════════════════════════════════════════════════════════════════════
def _settle_bets(s: State, assigned: pd.DataFrame) -> State:
    """Day 90: the bets filed in VALUE come back and are marked. Today there is one -- that
    redirected hours convert better than the hours they replaced -- and it settles only once
    the arms are powered. Filing it with a date and a falsifier is the point: the previous
    scoring effort had no such record, so nobody could say when it stopped working."""
    bets = s.artifacts.get("bets", [])
    if not bets:
        return s
    n_need = max(s.artifacts["metric_spec"]["north_star"]["n_per_arm_for_50pct_lift"].values())
    per_arm = min(s.artifacts.get("arms", {"x": 0}).values())
    settled = [{"bet": b["bet"], "settles": b["settles"], "verdict": "OPEN", "observed": f"{per_arm}/arm this cycle",
                "reads": f"not settleable before {n_need:,}/arm — reporting it now would be the mistake this pipeline exists to avoid"}
               for b in bets]
    s.say("\n  ── settling the bets filed on 2026-08-01 ──")
    s.say("    " + pd.DataFrame(settled).to_string(index=False).replace("\n", "\n    "))
    s.artifacts["bets_settled"] = settled
    mp = OUT / "metrics.md"
    if mp.exists():
        cols = ["bet", "verdict", "observed", "reads"]
        head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|"
        body = "\n".join("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |" for r in settled)
        mp.write_text(mp.read_text() + "\n\n".join(["", "---", "## Settlement — day 90 (SIMULATED outcomes, see READOUT)", head + "\n" + body, ""]))
    return s


RECONCILE_LABEL = {
    "rep_insists_model_low":     "model says low, the rep keeps working it",
    "model_high_nobody_looked":  "model says high, nobody has contacted it",
    "high_effort_no_result":     "4+ contacts and no conversion",
    "":                           "the two voices agree",
}


def _write_cases(s: State) -> None:
    """cases.md — named accounts, real data, no transcript. A manager is persuaded by an
    account they recognise with the rule that placed it beside the model's number. Four
    kinds of case, each with what it proves today and what only day 90 can prove:

      the model's top picks that this system will not call as-is   (ask / skip)
      the untouched trials — the highest-uplift first call in the book (first-call / observe)
      the accounts the model buries that continue calls first        (continue, low model rank)
      the skip bucket — hours that stop going where calling never helped"""
    a = s.accounts.copy()
    a["model_rank"] = a.p.rank(ascending=False, method="first").astype(int)
    U = s.artifacts.get("uplift", {}); tr = {r["segment"]: r for r in U.get("cuts", {}).get("train", [])}

    def row(r, why):
        ev = f"{r.evidence_pts:+.1f} pts uplift (train)" if r.sales_contacts_90d == 0 and pd.notna(r.evidence_pts) else \
             f"{r.evidence_pts:.1f}% in conversation (train)" if pd.notna(r.evidence_pts) else "—"
        return (f"| `{r.account_id}` | #{r.model_rank} | {r.p:.1%} | {int(r.sales_contacts_90d)} | {r.segment} | "
                f"{'yes' if r.trial_started else '—'} | {int(r.age_days)}d | {r.action} → `{r.arm if pd.notna(r.arm) else '—'}` | {ev} | {why} |")
    head = ("| account | model rank | score | contacts | segment | trial | age | here | evidence | why |\n"
            "|---|---|---|---|---|---|---|---|---|---|")

    top_not_called = a[(a.model_rank <= 30) & a.action.isin(["ask", "skip"])].sort_values("model_rank")
    untouched_trials = a[(a.action == "first-call") & (a.segment == "trial")].sort_values(["arm", "web_touchpoints_90d"], ascending=[True, False])
    buried = a[(a.arm == "continue") & (a.model_rank > 150)].sort_values("model_rank", ascending=False)
    skip = a[a.action == "skip"]
    ask = a[a.action == "ask"]

    parts = [
        f"# Cases — run of {TODAY:%Y-%m-%d}",
        "_Named accounts, real data, no transcript. Each case shows the model's rank beside the rule "
        "that places it here and the evidence behind that rule, estimated on the older labelled rows. "
        "What every case proves today: a decision the model would have made differently, and why. What "
        "none can prove yet: that this decision converts better — that is day 90._",

        f"## The model's top 30 this system will not call as-is — {len(top_not_called)} accounts",
        "_The model ranks them high because of the contacts already spent (its strongest feature). "
        "Here they go to `ask` (5+ contacts, no result — one question to the rep before the next hour) "
        "or `skip` (web-only or MQL-only — calling never helped on any cut)._",
        head + "\n" + "\n".join(row(r, "sunk cost — the rep answers first" if r.action == "ask" else "calling never helped this segment") for _, r in top_not_called.iterrows()),

        f"## The untouched trials — {len(untouched_trials)} accounts, the highest-uplift first call",
        f"_Someone is using the product and nobody has called. History: untouched trials convert at "
        f"{tr.get('trial', {}).get('rate_uncalled', 0):.1%}; with 1–4 calls, {tr.get('trial', {}).get('rate_called', 0):.1%} — **{tr.get('trial', {}).get('uplift_pts', 0):+.0f} points**, an upper "
        f"bound (reps chose whom to call). Half are called (`first-call`), half held back (`observe`), so day 90 "
        f"measures the real number. The model ranks them at median #{int(untouched_trials.model_rank.median()) if len(untouched_trials) else 0} of 300._",
        head + "\n" + "\n".join(row(r, "called this week" if r.arm == "first-call" else "held back at random — the control for the +10") for _, r in untouched_trials.iterrows()),

        f"## Buried by the model, called first here — {len(buried)} accounts",
        "_In conversation (1–4 contacts) with a trial or a vendor record; the model ranks them below #150. "
        "`continue` takes them ahead of the model's picks._",
        head + "\n" + ("\n".join(row(r, f"{r.segment} segment, in conversation") for _, r in buried.head(12).iterrows()) if len(buried) else "| — |"),

        f"## The skip bucket — {len(skip)} accounts, {int(skip.sales_contacts_90d.sum())} contacts already sunk",
        f"_Web-only or MQL-only. On every cut of history, calling these segments changed nothing (uplift ≤ 0). "
        f"**{skip.sales_contacts_90d.sum() * CONTACT_MINUTES / 60:.0f} rep-hours** went here last quarter; none go here this week. "
        f"They stay tracked: if they convert anyway, the rule was wrong._",
        f"By segment: {skip.segment.value_counts().to_dict()} · with contacts already: {int((skip.sales_contacts_90d > 0).sum())}",

        f"## The ask cohort — {len(ask)} accounts, {int(ask.sales_contacts_90d.sum())} contacts already sunk",
        f"_5+ contacts and no conversion. The model loves them (median rank #{int(ask.model_rank.median()) if len(ask) else 0}). History says accounts like these "
        f"convert at ~17% *if you keep calling* — and cost ~6 calls each to get there. The rep gets one question; "
        f"the answer sends each to `continue` or to rest. **{ask.sales_contacts_90d.sum() * CONTACT_MINUTES / 60:.0f} rep-hours** held._",

        "## How to read the levels",
        "| level | when | what it proves | what it cannot |\n|---|---|---|---|\n"
        "| named cases (above) | today | a decision the model would have made differently, with the rule and its evidence | that the decision converts better |\n"
        "| uplift by segment | today | where a call changed the outcome in history — as an upper bound | the true effect of a call |\n"
        "| first-call vs observe | day 90 | the true effect of the first call on a trial account | — |\n"
        "| conversions per 100 contacts by arm | quarter 2 | that the hours went to a better place | — |",
    ]
    (OUT / "cases.md").write_text("\n\n".join(parts))
    s.say(f"  cases.md              {len(top_not_called)} of the model's top 30 not called as-is · {len(untouched_trials)} untouched trials · "
          f"{len(buried)} buried-then-called · skip {len(skip)} · ask {len(ask)}")


# ═════════════════════════════════════════════════════════════════════════════
def _agent_text(s: State, name: str) -> str:
    """What the agent said, as text a manager reads. In template mode draft() returns the
    rendered prompt box; the worked example inside it is the paragraph. Live mode returns
    the paragraph itself. Either way the full render goes to the appendix."""
    raw = s.artifacts.get(name, "")
    if raw.startswith("┌"):
        ex = llm.AGENTS[name].example
        if not ex:
            return "_(no worked example on file — the rendered prompt is in the appendix)_"
        return ex if isinstance(ex, str) else json.dumps(ex, indent=2)
    return raw


def _write_brief(s: State, md_table) -> None:
    """manager_brief.md — the weekly page. Ordered for the reader, not the pipeline:
    what to think, what changed, where the metric stands, what to sign, what is dark.
    The agent prompts move to an appendix: the reviewer still sees every word; the manager
    no longer reads a prompt where a verdict should be."""
    a, spec = s.accounts, s.artifacts["metric_spec"]
    eco, ns = s.artifacts["hours_economics"], spec["north_star"]
    arms = s.artifacts.get("arms", {})
    per_arm = min(arms.values()) if arms else 0
    n_need = max(ns["n_per_arm_for_50pct_lift"].values())
    settle = (TODAY + pd.Timedelta(days=90)).date()

    # ── what changed ─────────────────────────────────────────────────────────
    acts = a.action.value_counts(); co = s.artifacts.get("cohorts", {})
    c_ask = int(a[a.arm == "ask"].sales_contacts_90d.sum()); c_skip = int(a[a.arm == "skip"].sales_contacts_90d.sum())
    changed = [
        f"**{acts.get('first-call', 0)} first-call candidates** — never contacted, trial or vendor record; "
        f"{arms.get('first-call', 0)} called this week, {co.get('observe', 0)} held back at random so day 90 can measure what the first call does.",
        f"**{acts.get('continue', 0)} in conversation** — 1–4 contacts, trial > vendor > none; {arms.get('continue', 0)} on this week's list, none over-invested.",
        f"**{co.get('ask', 0)} asked, not called** — 5+ contacts, no result: {c_ask} contacts (**{c_ask * CONTACT_MINUTES / 60:.0f} rep-hours**) held pending one question to the rep.",
        f"**{co.get('skip', 0)} skipped** — web-only or MQL-only, where calling never helped on any cut: {c_skip} contacts (**{c_skip * CONTACT_MINUTES / 60:.0f} rep-hours**) not spent again.",
        "Every account, by position and rule, in `ranked.csv`. Named cases in `cases.md`.",
    ]
    headline = f"**{(c_ask + c_skip) * CONTACT_MINUTES / 60:.0f} rep-hours** held or not spent this week — observable on the row; whether they convert better elsewhere is the bet"

    # ── metric status ────────────────────────────────────────────────────────
    bets = s.artifacts.get("bets", [])
    # cycles.jsonl is READOUT's memory; the brief reads it so cycle 4 does not call itself first
    cyc_path = OUT / "cycles.jsonl"
    hist = [json.loads(l) for l in cyc_path.read_text().splitlines() if l.strip()] if cyc_path.exists() else []
    hist = [h for h in hist if bool(h.get("simulated")) == bool(getattr(s.args, "demo", False))]
    n_cycle = len(hist) + 1
    n_settled = sum(1 for h in hist for b in h.get("bets_settled", [])
                    if b.get("verdict") in ("WON", "LOST"))
    n_pending = sum(1 for h in hist for b in h.get("bets_settled", [])
                    if b.get("verdict") in ("UNDERPOWERED", "NOT SETTLEABLE"))
    bets_line = (f"{len(bets)} open · {n_settled} settled"
                 + (f" · {n_pending} came back underpowered" if n_pending else "")
                 + (f" · cycle {n_cycle}" if hist else " · first cycle"))
    arms_line = " · ".join(f"{k} {n}" for k, n in arms.items())
    arms_line += " · cohorts " + " · ".join(f"{k} {v}" for k, v in s.artifacts.get("cohorts", {}).items() if v)
    metric = "\n".join([
        "| | |", "|---|---|",
        f"| **North star** · conversions per 100 contacts, by arm | **not readable** · "
        f"{per_arm}/{n_need:,} per arm · {ns['weeks_at_current_allocation']} weeks at this pace, "
        f"two quarters at {ns['accounts_per_arm_for_two_quarter_readout']}/arm |",
        f"| **Weekly headline** · rep-hours redirected | {headline} |",
        f"| **Bets** | {bets_line} |",
        f"| **Price of a conversion today** | {eco['contacts_per_conversion']} contacts · "
        f"{eco['rep_hours_per_conversion']} rep-hours |",
        f"| **Arms this cycle** | {arms_line} |",
    ])

    (OUT / "manager_brief.md").write_text("\n\n".join([
        f"# Cordilla — week of {TODAY:%Y-%m-%d}",
        "_No ranked call list, no probability on any account. The audit found this model's "
        "ranking indistinguishable from noise; it is used only where it disagrees with "
        "something else._",

        "## The scorecard — the graph against three baselines",
        _scorecard_md(s),

        "## This week's verdict",
        _agent_text(s, "run_verdict"),

        "## What changed this week",
        "\n\n".join(changed),

        "## The model's top 30, and what happens to each here",
        _model_vs_us_md(s),

        "## Where the metric stands",
        metric,

        "## On real outcomes — each policy's list of 90, and how many converted",
        _outcomes_md(s),

        "## The prediction test — 300 accounts none of the methods saw",
        _heldout_md(s),
        "_The weekly number is filed as a bet with its falsifier; it cannot be read as a result. "
        "Detail, guardrails and the kill switch in `metrics.md`._",

        "## How this becomes a number",
        _ladder_md(s),

        "## This week's allocation — the experiment you are approving",
        _agent_text(s, "experiment_card"),

        "## Actions awaiting your signature",
        md_table(s.artifacts["actions"], ["severity", "owner", "what", "action"]),

        "## Not running today",
        md_table([b.as_dict() for b in s.bypassed] + ([] if s.has("outcomes_90d") else [{
            "node": "READOUT", "reason": "90-day outcomes for the accounts assigned today do not exist yet",
            "unblocked_by": "one cycle, with outcomes written back per account — first read 2026-10-30"}]),
                 ["node", "reason", "unblocked_by"]),

        "## Proposed, not wired — the conversation layer",
        "The one input that is not a function of Cordilla's own effort is what the prospect said on the "
        "call. A layer that extracts it is designed, measured on synthetic transcripts (1.00 on the routing "
        "field, quotes grounded 20/20) and deliberately kept out of this graph until real transcripts with "
        "outcomes exist. It would work the margin — the accounts no column separates. See `extensions/conversation_layer/`.",

        "---",
        "## Appendix — the agents, as rendered",
        "_Every prompt, verbatim, with the worked example that stands in for a live call. "
        "For the reviewer; the manager stops at the line above._",
        "### run_verdict", "```\n" + s.artifacts["run_verdict"] + "\n```",
        "### experiment_card", "```\n" + s.artifacts["experiment_card"] + "\n```",
    ]))


# ═════════════════════════════════════════════════════════════════════════════
N_MIN_TO_MOVE = 99       # the n at which a zero-conversion result means something at 3%
STEP = 5                 # accounts moved per update
FLOOR_SHARE = 0.10       # no arm ever drops below this share -- exploration never dies


def _learn(s: State, assigned: pd.DataFrame) -> State:
    """The loop. READOUT writes what happened to cycles.jsonl, reads everything that has
    happened so far, and tells the next BUDGET what to do.

    Three things learn here, each gated on having enough data to learn from:
      · ALLOCATION   the arm with the best cumulative lower bound grows by STEP; no arm
                     falls below FLOOR_SHARE. Nothing moves until every arm has passed
                     N_MIN_TO_MOVE -- below that the rule would be chasing noise, and the
                     demo (no true difference between arms) shows exactly that noise.
      · THE AGENT    its real precision accumulates from the settled bets: how often
                     'released' accounts converted anyway, how often 'rescued' ones did.
                     Reported beside the synthetic 1.00 until it can replace it.
      · THE METRIC   proxy validity needs the same history; this is where it will read.

    The file is the memory Cordilla has never had. It is append-only on purpose."""
    path = OUT / "cycles.jsonl"
    history = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
    cycle = len(history) + 1
    a = s.accounts

    per_arm = {arm: {"n": int(len(d)), "k": int(d.converted.sum())}
               for arm, d in assigned.groupby("arm")}
    rec = {
        "cycle": cycle, "reference_date": str(TODAY.date()),
        "arm_sizes_requested": s.artifacts.get("arm_sizes_requested", {}),
        "arms": per_arm,
        "bets_settled": [{"bet": b["bet"], "verdict": b["verdict"]} for b in s.artifacts.get("bets_settled", [])],
        "simulated": True,
    }
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    history.append(rec)

    # ── cumulative ────────────────────────────────────────────────────────────
    cum = {}
    for h in history:
        for arm, v in h["arms"].items():
            c = cum.setdefault(arm, {"n": 0, "k": 0}); c["n"] += v["n"]; c["k"] += v["k"]
    def wilson(k, n_, z=1.96):
        if n_ == 0:
            return 0.0, 1.0
        ph, d = k / n_, 1 + z**2 / n_
        c = (ph + z**2 / (2 * n_)) / d
        h = z * np.sqrt(ph * (1 - ph) / n_ + z**2 / (4 * n_**2)) / d
        return max(0.0, c - h), min(1.0, c + h)

    arms_only = {k_: v for k_, v in cum.items() if k_ in ("continue", "first-call")}   # control is a third, not a size to move
    s.say(f"\n  ── the loop · cycle {cycle} ──")
    s.say(f"  cumulative, all cycles:  " + " · ".join(
        f"{k_} {v['k']}/{v['n']}" for k_, v in cum.items()))

    # ── allocation update ─────────────────────────────────────────────────────
    sizes = dict(s.artifacts.get("arm_sizes_requested", {k_: 30 for k_ in arms_only}))
    total = sum(sizes.values())
    floor = int(np.ceil(FLOOR_SHARE * total))
    min_n = min(v["n"] for v in arms_only.values()) if arms_only else 0
    ci = {k_: wilson(v["k"], v["n"]) for k_, v in arms_only.items()}
    moved = None
    if min_n < N_MIN_TO_MOVE:
        reason = (f"holding — smallest arm has n={min_n}, needs {N_MIN_TO_MOVE} before any move; "
                  f"below that the rule chases noise")
    else:
        # Move only on EVIDENCE: the best arm's lower bound must clear the worst arm's upper
        # bound. "Best point estimate" would move on noise every cycle -- and with no true
        # difference between arms, the demo shows exactly that if you let it.
        best = max(ci, key=lambda k_: ci[k_][0])
        donors = [k_ for k_ in sizes if k_ != best and sizes[k_] - 1 > floor]
        worst = min(donors, key=lambda k_: ci[k_][1]) if donors else None
        if worst is None:
            reason = f"every other arm is at the floor ({floor}); nothing to move"
        elif ci[best][0] > ci[worst][1]:
            take = min(STEP, sizes[worst] - floor)
            sizes[worst] -= take; sizes[best] += take
            moved = (worst, best, take)
            reason = (f"moved {take} from {worst} (CI up to {ci[worst][1]:.1%}) to {best} "
                      f"(CI from {ci[best][0]:.1%}) — intervals separated; floor {floor}/arm holds")
        else:
            n_need = max(s.artifacts["metric_spec"]["north_star"]["n_per_arm_for_50pct_lift"].values())
            reason = (f"holding — {best} [{ci[best][0]:.1%}, {ci[best][1]:.1%}] and {worst} "
                      f"[{ci[worst][0]:.1%}, {ci[worst][1]:.1%}] overlap at n={min_n}; "
                      f"separating a 50% lift needs ~{n_need:,}/arm")
    nxt = {"cycle": cycle, "arm_sizes": sizes, "reason": reason, "written_by": "READOUT",
           "cumulative": cum, "floor_per_arm": floor, "simulated": bool(s.args.demo)}
    (OUT / "next_cycle.json").write_text(json.dumps(nxt, indent=2))
    s.artifacts["next_cycle"] = nxt
    s.say(f"  allocation update:  {reason}")
    s.say(f"  next cycle:  " + " · ".join(f"{k_} {v}" for k_, v in sizes.items()))
    if moved is None:
        s.say(f"  (with no true difference between arms, a rule that moved now would be rewarding "
              f"whichever arm got lucky — that is what the gate is for)")

    # ── the track record, into the same file the bets were filed in ─────────
    mp = OUT / "metrics.md"
    if mp.exists():
        rows = "\n".join(f"| {h['cycle']} | " + " · ".join(f"{k_} {v['k']}/{v['n']}" for k_, v in h["arms"].items()) + " |" for h in history)
        mp.write_text(mp.read_text() + "\n\n".join([
            "", f"## Track record — {cycle} cycle{'s' if cycle > 1 else ''} so far (SIMULATED)",
            "| cycle | conversions/assigned by arm and cohort |", "|---|---|\n" + rows,
            f"**Cumulative:** " + " · ".join(f"{k_} {v['k']}/{v['n']}" for k_, v in cum.items()),
            f"**Next allocation:** {reason}", ""]))
    return s


def _model_vs_us_md(s: State) -> str:
    """The head-to-head as the manager reads it: the model's answer is 'call these 30'; this
    is what happens to each of the 30 here, with the reason on the row."""
    mv = s.artifacts.get("model_vs_us")
    if not mv:
        return "_(not computed this run)_"
    lines = ["| the model's top 30 | count |", "|---|---|"]
    lines += [f"| {k} | **{v}** |" for k, v in mv["top30_fates"].items()]
    lines.append(f"\n**Of the 30 the model says to call, {mv['called_as_is']} are called as-is.** "
                 f"Every other verdict is a flag or a cohort the row itself shows.")
    lines.append("\n| rank | account | score | contacts | age | flags | here |\n|---|---|---|---|---|---|---|")
    for r in mv["top9"]:
        lines.append(f"| #{r['rank']} | `{r['account_id']}` | {r['p']:.1%} | {r['contacts']} | "
                     f"{r['age_days']}d | {r['flags'] or '—'} | {r['fate']} |")
    return "\n".join(lines)



def _outcomes_md(s: State) -> str:
    mv = s.artifacts.get("model_vs_graph_outcomes")
    if not mv:
        return "_(audit/oof_predictions.npy not found)_"
    lines = [f"_{mv['n_clean_rows']} labelled training rows with a closed 90-day window · base rate "
             f"{mv['base_rate']:.1%} · {mv['note']}._", "",
             "| who builds the list of 90 | converted | rate | 95% CI | lift | contacts already sunk | rep-hours sunk |",
             "|---|---|---|---|---|---|---|"]
    for r in mv["rows"]:
        b = "**" if ("out-of-fold" in r["policy"] or "worklist" in r["policy"]) else ""
        lines.append(f"| {b}{r['policy']}{b} | {r['converted']} | {b}{r['rate']:.1%}{b} | {r['ci95']} | "
                     f"{r['lift']}× | {r['contacts_already_sunk']} | {r['rep_hours_sunk']} |")
    mem, oof = mv["rows"][0], mv["rows"][1]
    lines.append(f"\n**The model from memory: {mem['rate']:.1%}. The model on rows it never saw: "
                 f"{oof['rate']:.1%}.** The first is what a dashboard would show; the second is what it knows.")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
def _scorecard(s: State) -> dict:
    """THE metric of the whole graph, against three baselines, in one table.

    Metric: of the list a policy says to call, what share converts. Two evidence levels
    in two columns -- historical (today, on the 1,099 labelled rows, observational) and
    prospective (day 90, arms against control, causal). The second column is empty until
    READOUT runs, and fills in on its own. Alongside: the hours each policy refuses to
    spend -- the graph's second dimension, which no baseline has."""
    mv = s.artifacts.get("model_vs_graph_outcomes", {})
    R = {r["policy"]: r for r in mv.get("rows", [])}
    a = s.accounts
    ask_c = int(a[a.arm == "ask"].sales_contacts_90d.sum()) if "arm" in a else 0
    skip_c = int(a[a.arm == "skip"].sales_contacts_90d.sum()) if "arm" in a else 0
    ro = {r["arm"]: r for r in s.artifacts.get("readout", [])}     # prospective, if READOUT ran

    def hist(key):
        r = R.get(key); return (r["rate"], r["ci95"], r["converted"]) if r else (None, "", None)
    def prosp(arms):
        ks = [ro[x] for x in arms if x in ro]
        if not ks: return None, ""
        k, n = sum(x["conversions"] for x in ks), sum(x["accounts"] for x in ks)
        return k / n if n else None, f"{k}/{n}"

    rows = [
        {"policy": "model alone — the dashboard the VP asked for", "list": "top 90 by score",
         "hist": hist("model — out-of-fold (what it actually knows)"),
         "memory": R.get("model — in-sample (what a dashboard shows)", {}).get("rate"),
         "prosp": (None, ""), "refuses_h": 0.0, "role": "baseline"},
        {"policy": "random — no system", "list": "90 at random",
         "hist": hist("random (mean of 200 draws)"), "prosp": (None, ""), "refuses_h": 0.0, "role": "baseline"},
        {"policy": "the team today — rep's own picks", "list": "accounts the team chose to work",
         "hist": (mv.get("team_today_rate"), mv.get("team_today_ci", ""), mv.get("team_today_k")),
         "prosp": prosp(["control"]), "refuses_h": 0.0, "role": "baseline · control arm"},
        {"policy": "THE GRAPH — its worklist", "list": "continue 45 + first-call 15 · ask, observe and skip tracked, not called",
         "hist": hist("graph worklist (continue 75 + first-call 15)"),
         "prosp": prosp(["continue", "first-call"]),
         "refuses_h": round((ask_c + skip_c) * CONTACT_MINUTES / 60, 1), "role": "system"},
        {"policy": "the graph — confident picks only", "list": "continue alone",
         "hist": hist("graph continue (1-4 contacts: trial > vendor > none)"), "prosp": prosp(["continue"]),
         "refuses_h": None, "role": "system · no exploration"},
    ]
    s.artifacts["scorecard"] = {"rows": rows, "ask_contacts": ask_c, "skip_contacts": skip_c,
                                "prospective_available": bool(ro),
                                "prospective_simulated": bool(ro) and bool(getattr(s.args, "demo", False))}
    return s.artifacts["scorecard"]


def _scorecard_md(s: State) -> str:
    sc = s.artifacts.get("scorecard") or _scorecard(s)
    sim = " **(SIMULATED)**" if sc["prospective_simulated"] else ""
    R = {r["policy"]: r for r in s.artifacts.get("model_vs_graph_outcomes", {}).get("rows", [])}
    def recall_of(policy_key):
        r = R.get(policy_key); return f" · finds **{r['recall']:.0%}** of buyers" if r and r.get("recall") is not None else ""
    keymap = {"model alone — the dashboard the VP asked for": "model — out-of-fold (what it actually knows)",
              "random — no system": "random (mean of 200 draws)",
              "THE GRAPH — its worklist": "graph worklist (continue 75 + first-call 15)",
              "the graph — confident picks only": "graph continue (1-4 contacts: trial > vendor > none)"}
    head = ("| | the list it says to call | historical, real outcomes — of the 90 called, how many convert · of the buyers, how many found | "
            f"prospective, day 90{sim} | rep-hours it refuses to spend |")
    lines = [head, "|---|---|---|---|---|"]
    for r in sc["rows"]:
        h, ci, k = r["hist"]
        hist = (f"**{h:.1%}** {ci}" + recall_of(keymap.get(r["policy"], ""))) if h is not None else "—"
        if r.get("memory"): hist += f" · *from memory: {r['memory']:.1%}*"
        p, pn = r["prosp"]
        prosp = f"**{p:.1%}** ({pn})" if p is not None else "_not yet — READOUT_"
        ref = "—" if r["refuses_h"] is None else (f"**{r['refuses_h']:.0f} h / quarter**" if r["refuses_h"] else "0 — calls everything it ranks")
        b = "**" if r["role"] == "system" else ""
        lines.append(f"| {b}{r['policy']}{b} | {r['list']} | {hist} | {prosp} | {ref} |")
    lines.append("\n_Historical: each policy builds its list from the 1,099 labelled training rows with a closed "
                 "90-day window, and we count who converted — observational, the comparison is fair, the levels "
                 "are not causal. Prospective: the arms READOUT assigns today, read at day 90 against control — "
                 "causal, and not readable before ~2,500 per arm. The graph must beat the first three rows on "
                 "both columns, or it is retired._")
    return "\n".join(lines)



def _heldout_md(s: State) -> str:
    """audit/heldout_comparison.py: the most recent 300 labelled accounts held out, each method
    builds its list, we count who converted. No model is fitted; the model's score is its
    out-of-fold prediction. Precision = of the K you said to call, how many converted.
    Recall = of everyone who converted in the 300, how many your list found."""
    h = s.artifacts.get("heldout")
    if not h:
        return "_(audit/heldout_comparison.json not found — run `python audit/heldout_comparison.py`)_"
    lines = [f"_Test: the {h['test_n']} most recent labelled accounts ({h['test_window'][0]} → {h['test_window'][1]}), "
             f"{h['test_converters']} converted ({h['test_base_rate']:.1%}). Train: the {h['train_n']} before them. "
             f"Fits performed: {h['fits_performed']} — the model's score is its out-of-fold prediction._"]
    for K in ("30", "60"):
        lines += ["", f"**K = {K}**", "",
                  "| who builds the list | converted | precision | 95% CI | recall | contacts sunk |", "|---|---|---|---|---|---|"]
        for r in h["by_K"][K]:
            b = "**" if (r["policy"].startswith("continue alone") or r["policy"].startswith("THE GRAPH")) else ""
            if r["precision"] is None:
                lines.append(f"| {r['policy']} | — | — | {r['ci95']} | — | — |"); continue
            lines.append(f"| {b}{r['policy']}{b} | {r['converted']} | {b}{r['precision']:.1%}{b} | {r['ci95']} | "
                         f"{r['recall']:.0%} | {r['contacts_sunk']} |")
    lines.append("\n**What this test can judge:** the model against the rules — continue beats the model's honest "
                 "score about 2×, and adding the model's picks to continue removes conversions. **What it cannot "
                 "judge:** first-call and the conversation layer. Both pick accounts history never called; their historical rate is "
                 "*what happens when nobody calls*, which is the question the arms exist to answer. Reading explore's "
                 "row as its value would be the same confounding error in reverse.")
    return "\n".join(lines)



def _ladder_md(s: State) -> str:
    """The ladder of numbers by maturity, and the sentence they fill. What is real this week is
    arithmetic; what becomes real at day 90 is the randomised comparison; the sentence the VP can
    repeat is spoken with its interval and without its point until the interval excludes zero."""
    a = s.accounts; co = s.artifacts.get("cohorts", {}); hv = s.artifacts.get("halves", {})
    c_ask = int(a[a.arm == "ask"].sales_contacts_90d.sum()); c_skip = int(a[a.arm == "skip"].sales_contacts_90d.sum())
    n_fc = int(((a.arm == "first-call") & (a.segment == "trial")).sum()); n_ob = co.get("observe", 0)   # the causal pair: trials only
    n_need = max(s.artifacts["metric_spec"]["north_star"]["n_per_arm_for_50pct_lift"].values())
    return "\n".join([
        "| rung | what | unit and formula | real when |",
        "|---|---|---|---|",
        f"| **this week** | hours held or not spent | ask {c_ask} + skip {c_skip} contacts × {CONTACT_MINUTES} min = **{(c_ask + c_skip) * CONTACT_MINUTES / 60:.0f} rep-h** — a count on the row, not a result | now |",
        f"| **day 90 · the first causal number** | first call on an untouched trial: called vs observed, randomised | uplift = k_called/n_called − k_obs/n_obs, in points, with its interval · today {n_fc} called / {n_ob} observed | readable at ~138 per group |",
        f"| **day 90 · the policy** | the system's two thirds vs the control third, **every account counted** (intention-to-treat) | I = (p_system − p_control) × N_system = incremental conversions, with a two-proportion interval · today {hv.get('system', 0)} vs {hv.get('control', 0)} | interval excludes zero |",
        f"| **quarter 2** | conversions per 100 rep-hours, system vs control, cumulative | 100 × k / contacts logged after assignment × 5 | ~{n_need:,} per side |",
        "",
        "**The sentence, when it reads:** *\"Over N accounts assigned between [date] and [date], the system produced I more conversions than the reps' own picks would have — between lo and hi — for the same rep-hours, and it stopped spending H hours where calling has never converted.\"* Until then it is spoken with the interval and without the point. No dollars: there is no deal size on file, and a dollar figure is read as a point. Readout dates are fixed in advance; nothing is read before the pre-registered n.",
    ])
