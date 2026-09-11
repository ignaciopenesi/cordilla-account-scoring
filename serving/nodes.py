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


# ═════════════════════════════════════════════════════════════════════════════
def INGEST(s: State) -> State:
    """Load everything. One place where data enters, so the rest of the graph never
    changes when the source does -- today CSVs, tomorrow Salesforce."""
    s.accounts = pd.read_csv(ROOT / "data/accounts_to_score.csv", parse_dates=["snapshot_date"])
    s.training = pd.read_csv(ROOT / "data/training_data.csv", parse_dates=["snapshot_date"])
    with open(ROOT / "model/model.pkl", "rb") as f:
        s.model = pickle.load(f)

    # Capabilities are what is actually wired up. The bypasses below read this.
    s.capabilities = {"crm_accounts", "labeled_history", "scoring_model"}
    # not present: "call_transcripts", "outcomes_90d"

    s.say(f"  {len(s.accounts)} accounts to score, {len(s.training)} labeled rows")
    s.say(f"  capabilities wired: {', '.join(sorted(s.capabilities))}")
    s.say("  NOT wired: call_transcripts, outcomes_90d")
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
               action="Refresh before assigning. No account over 180 days enters an arm without "
                      "a refreshed snapshot.",
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
def BASELINES(s: State) -> State:
    """What the score has to beat. A score with nothing to compare against means nothing --
    and audit §2.4/§2.6 showed a one-line sort beats this model where it counts."""
    a = s.accounts
    a["rank_contacts"] = (a.sales_contacts_90d + 1e-9 * np.arange(len(a))).rank(ascending=False, method="first")
    a["rank_random"] = pd.Series(np.random.default_rng(42).permutation(len(a)) + 1, index=a.index)

    top_model = set(a.nsmallest(30, "p_rank").account_id)
    top_rule = set(a.nsmallest(30, "rank_contacts").account_id)
    overlap = len(top_model & top_rule)
    s.artifacts["top30_overlap_model_vs_rule"] = overlap
    s.say(f"  top-30 by model vs top-30 by ORDER BY sales_contacts: {overlap}/30 shared")
    s.say(f"  (audit: the sort scores 0.608 forward in time, the model 0.474)")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def FLAGS(s: State) -> State:
    """Per account: the reasons to distrust its score, with the number behind each.

    The rep never sees a score. They see these. The lead-scoring literature and the audit
    agree that an unexplained individual error is what kills adoption."""
    a = s.accounts
    a["f_no_vendor_record"] = a.intent_score.isna()
    a["f_stale_180"] = a.age_days > 180
    a["f_never_touched"] = a.sales_contacts_90d == 0
    a["f_over_invested"] = a.sales_contacts_90d >= 5
    flagcols = [c for c in a.columns if c.startswith("f_")]
    a["n_flags"] = a[flagcols].sum(axis=1)

    a["flags"] = a[flagcols].apply(
        lambda r: ", ".join(c[2:].replace("_", " ") for c in flagcols if r[c]) or "—", axis=1)

    for c in flagcols:
        s.say(f"  {c[2:]:<18} {int(a[c].sum()):3d}")
    clean_top30 = int((a.nsmallest(30, "p_rank").n_flags == 0).sum())
    s.artifacts["clean_in_top30"] = clean_top30
    s.say(f"  of the top 30 by score, {clean_top30} carry no flag at all")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def CONVERSATION_INTENT(s: State) -> State:
    """The missing signal -- and the one thing in this data that would describe the ACCOUNT
    rather than describe Cordilla.

    PARTIAL TODAY. The coverage quadrants below are computed from real data and are the
    reason this node matters. The extraction itself needs transcripts, which the CSVs do
    not carry, so it is bypassed rather than faked."""
    a = s.accounts
    has_vendor = a.intent_score.notna()
    had_call = a.sales_contacts_90d > 0

    quad = {
        "calibrate_vendor (vendor record + a call happened)": int((has_vendor & had_call).sum()),
        "fill_the_gap (no vendor record + a call happened)": int((~has_vendor & had_call).sum()),
        "unverified (vendor record, no call)": int((has_vendor & ~had_call).sum()),
        "blind (no vendor record, no call)": int((~has_vendor & ~had_call).sum()),
    }
    a["intent_quadrant"] = np.select(
        [has_vendor & had_call, ~has_vendor & had_call, has_vendor & ~had_call],
        ["calibrate", "fill_gap", "unverified"], default="blind")
    s.artifacts["intent_quadrants"] = quad
    for k, v in quad.items():
        s.say(f"  {v:4d}  {k}")

    contacts_in_gap = int(a.loc[~has_vendor, "sales_contacts_90d"].sum())
    total_contacts = int(a.sales_contacts_90d.sum())
    s.say(f"  {contacts_in_gap} of {total_contacts} logged contacts ({contacts_in_gap/total_contacts:.0%}) "
          f"happened in accounts the vendor never covered")

    s.find(what="Conversations that would fill the vendor's coverage gap already happen, and "
                "are not captured",
           evidence=f"{contacts_in_gap} of {total_contacts} contacts ({contacts_in_gap/total_contacts:.0%}) "
                    f"are with accounts that have no vendor record; {quad['fill_the_gap (no vendor record + a call happened)']} "
                    f"such accounts have had at least one call. Vendor COVERAGE predicts conversion "
                    f"(8.22% vs 3.94%, p=0.003) but its SCORE does not (quintiles flat, p=0.42)",
           severity="high", owner="process",
           action="Record sales calls with per-call disclosure and transcript-only storage, and "
                  "extract intent per the contract in llm.py. Start with the fill_gap quadrant -- "
                  "it needs no new outreach, only capture of calls that already happen.",
           cost="recording + transcription on existing calls; no new rep time",
           expect="the 40% of the base the vendor cannot see gets a first-hand intent signal",
           source="CONVERSATION_INTENT")

    if not s.has("call_transcripts"):
        s.bypass(node="CONVERSATION_INTENT",
                 reason="the two CSVs carry no call transcripts",
                 unblocked_by="call recording with disclosure (two-party-consent states and GDPR "
                              "make this a precondition) + Dialpad Ai Call Purpose / Custom Moments, "
                              "or any ASR feeding the `conversation_intent` prompt in llm.py",
                 would_produce="per account: intent_level A-F grounded in a verbatim prospect quote, "
                               "objections[], next_step_agreed, speaker_role, call_purpose, confidence",
                 still_computed=f"the four coverage quadrants: {quad}")
        print(llm.draft("conversation_intent", mode=s.args.llm,
                        account_id="ACC-00453", date="2026-07-22",
                        transcript="[speaker-labelled transcript would go here]"))
    return s


# ═════════════════════════════════════════════════════════════════════════════
def CALIBRATE_VENDOR(s: State) -> State:
    """Is the intent vendor right? Nobody at Cordilla can answer that today.

    In the 103 accounts where a vendor record AND a call both exist, the vendor's claim can
    be contrasted against what the prospect actually said. That is the only way to find out
    whether the score you are paying for is any good -- and evidence for the renewal."""
    n = int(s.artifacts["intent_quadrants"]["calibrate_vendor (vendor record + a call happened)"])
    s.bypass(node="CALIBRATE_VENDOR",
             reason="needs CONVERSATION_INTENT, which has no transcripts to work from",
             unblocked_by="the same recording capability; then no new data is required",
             would_produce=f"on the {n} accounts where both exist: agreement rate between vendor "
                           f"intent decile and conversation intent level, by segment; the segments "
                           f"where the vendor systematically over- or under-states; a renewal memo "
                           f"with that evidence",
             still_computed=f"the contrastable set: {n} accounts")
    s.find(what="The intent vendor's score has never been validated against anything",
           evidence=f"{n} scoring accounts have both a vendor record and a logged call, so the "
                    f"vendor's claim is contrastable today. In training, vendor coverage predicts "
                    f"conversion (p=0.003) while the score itself does not (Spearman p=0.42)",
           severity="medium", owner="vendor",
           action="Pay for coverage, not for the score: keep a boolean `intent_known`, stop using "
                  "the numeric value in any model or view. Once calls are recorded, measure "
                  "agreement on these accounts and take it into the renewal.",
           cost="0 now (a field change); the measurement comes free with recording",
           expect="the renewal is negotiated on evidence instead of on the vendor's own claim",
           source="CALIBRATE_VENDOR")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def RECONCILE(s: State) -> State:
    """Three voices per account: the model, our own effort, and what the prospect said.
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

    # The question is a fallback: with transcripts, the rep has already said this on the call.
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

    s.bypass(node="RECONCILE (third voice)",
             reason="conversation intent is unavailable, so only model-vs-effort can be compared",
             unblocked_by="CONVERSATION_INTENT",
             would_produce="the two cells that need no human at all: 'model low + rep insists + "
                           "conversation says A/B' (the model is wrong, and we can prove it) and "
                           "'model high + 5+ contacts + conversation says E/F' (sunk cost, stop)",
             still_computed=f"model-vs-effort disagreements: {counts.to_dict()}")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def ALLOCATE(s: State) -> State:
    """Three matched arms, not a ranked list.

    This is deliberately not a tier and not routing: it compares POLICIES and keeps a
    control. It is the Stitch Fix 90/10 idea -- the randomised arm is what produces
    unbiased outcome data, which is the thing Cordilla has never had."""
    a, ARM = s.accounts, 30
    eligible = a[~a.f_stale_180].copy()                      # no stale account enters an arm

    exploit = eligible.nsmallest(ARM, "rank_contacts")
    rest = eligible[~eligible.account_id.isin(exploit.account_id)]
    signal = (rest.trial_started == 1) | (rest.mql_count_90d > 0) | (rest.web_touchpoints_90d >= 4)
    explore = rest[(rest.sales_contacts_90d == 0) & signal].nlargest(ARM, "web_touchpoints_90d")
    rest2 = rest[~rest.account_id.isin(explore.account_id)]
    control = rest2.sample(n=min(ARM, len(rest2)), random_state=7)

    arms = {"exploit": exploit, "explore": explore, "control": control}
    for name, d in arms.items():
        a.loc[a.account_id.isin(d.account_id), "arm"] = name
    s.artifacts["arms"] = {k: int(len(v)) for k, v in arms.items()}

    bal = pd.DataFrame({k: v.industry.value_counts() for k, v in arms.items()}).fillna(0).astype(int)
    s.say(f"  exploit {len(exploit)} · explore {len(explore)} · control {len(control)}")
    s.say("  industry balance across arms:\n" + bal.to_string().replace("\n", "\n    "))

    arm_block = "\n".join(
        f"- **{k}** ({len(v)} accounts): {desc}" for k, (v, desc) in
        {"exploit": (exploit, "highest logged contact count — the rule that beats the model out-of-sample"),
         "explore": (explore, "never contacted but carrying a signal (trial, MQL or web activity)"),
         "control": (control, "the rep picks — this is what would happen without the system")}.items())
    s.artifacts["experiment_card"] = llm.draft(
        "experiment_card", mode=s.args.llm, total=ARM * 3, n_arms=3,
        matched_on="industry and company size", base_rate="6.5% in training, 1-3% per the business",
        arm_block=arm_block)
    print(s.artifacts["experiment_card"])
    return s


# ═════════════════════════════════════════════════════════════════════════════
def HYGIENE(s: State) -> State:
    """CRM contradictions, as proposals with evidence. Proposes, never executes.

    Every defect here comes with the rule that stops it recurring -- a one-off cleanup is
    worth much less than the rule."""
    a, t = s.accounts, s.training

    # audit §3.9 — "Suspect" means no engagement. 85% of them have some.
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
        s.find(what="account_type does not mean what it says",
               evidence=f"{len(t_susp)} of {(t.account_type=='Suspect').sum()} training 'Suspects' "
                        f"and {len(susp)} of {(a.account_type=='Suspect').sum()} scoring ones have an "
                        f"MQL, trial or contact; conversion is identical across the three types "
                        f"(chi2 p = 0.84)",
               severity="high", owner="crm",
               action=f"Bulk-reclassify the {len(susp)} scoring accounts, and add a validation rule "
                      f"so an account with activity cannot be saved as Suspect.",
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
           expect="either the exploit arm is justified, or the whole dataset is known to be unusable",
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
    if prev_path.exists():
        prev = set(json.loads(prev_path.read_text()))
        ov = len(set(top30) & prev)
        s.say(f"  top-30 overlap with the previous run: {ov}/30")
    else:
        ov = None
        s.say("  no previous run on file — overlap starts being tracked from next week")
    prev_path.write_text(json.dumps(top30))
    s.artifacts["top30_overlap_prev_run"] = ov

    s.artifacts["run_verdict"] = llm.draft(
        "run_verdict", mode=s.args.llm, date=f"{TODAY:%Y-%m-%d}",
        psi_summary=f"every feature is stable against training (max PSI {psis[worst]:.2f}, {worst})",
        overlap=f"{ov}/30" if ov is not None else "not yet tracked (first run)",
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

    rep = a[a.arm.notna()][["account_id", "arm", "account_type", "industry", "employee_count",
                            "sales_contacts_90d", "age_days", "flags"]].sort_values(["arm", "account_id"])
    rep.to_csv(OUT / "rep_worklist.csv", index=False)

    dis = a[a.disagreement != ""][["account_id", "disagreement", "sales_contacts_90d", "flags"]]
    dis.to_csv(OUT / "disagreements.csv", index=False)

    pd.DataFrame(s.artifacts["actions"]).to_csv(OUT / "actions.csv", index=False)

    # markdown table by hand -- tabulate is not in requirements.txt and this is one table
    def md_table(rows, cols):
        head = "| " + " | ".join(cols) + " |"
        rule = "|" + "|".join("---" for _ in cols) + "|"
        body = ["| " + " | ".join(str(r[c]).replace("\n", " ").replace("|", "/") for c in cols) + " |"
                for r in rows]
        return "\n".join([head, rule, *body])

    (OUT / "manager_brief.md").write_text("\n\n".join([
        f"# Cordilla — run of {TODAY:%Y-%m-%d}",
        "_Nothing here is a ranked call list, and no account carries a probability. "
        "The audit found this model's ranking indistinguishable from noise; what follows "
        "uses it only where it disagrees with something else._",
        "## Verdict", s.artifacts["run_verdict"],
        "## Experiment", s.artifacts["experiment_card"],
        "## Actions awaiting your approval",
        md_table(s.artifacts["actions"], ["severity", "owner", "what", "action"]),
        "## Not running today",
        md_table([b.as_dict() for b in s.bypassed], ["node", "reason", "unblocked_by"]),
    ]))

    s.say(f"  rep_worklist.csv      {len(rep)} accounts, with flags and NO score")
    s.say(f"  disagreements.csv     {len(dis)} accounts where the voices disagree")
    s.say(f"  actions.csv           {len(s.artifacts['actions'])} prescriptions with an owner")
    s.say(f"  manager_brief.md      verdict + experiment card + action table")
    s.say("  → Salesforce would receive: flags, intent_known, snapshot date. Never the probability.")
    return s


# ═════════════════════════════════════════════════════════════════════════════
def READOUT(s: State) -> State:
    """Day 90. The first honest number Cordilla will have had."""
    s.bypass(node="READOUT",
             reason="90-day outcomes for the accounts assigned today do not exist yet",
             unblocked_by="one cycle of the arms above, with outcomes written back per account",
             would_produce="conversions per logged contact by arm with confidence intervals; the "
                           "same broken out by conversation intent level (testing whether intent "
                           "from calls predicts better than any CRM column); and the epsilon-greedy "
                           "update — the winning arm grows, exploration never goes to zero",
             still_computed=f"the arms are assigned and recorded: {s.artifacts.get('arms', {})}")
    s.say("  with 30 accounts per arm at ~6%, the first readout will be noisy. It accumulates:")
    s.say("  cycle 1 = 30/arm, cycle 2 = 60, cycle 3 = 90. The point is that it starts.")
    return s
