# Cordilla — run of 2026-08-01

_Nothing here is a ranked call list, and no account carries a probability. The audit found this model's ranking indistinguishable from noise; what follows uses it only where it disagrees with something else._

## Verdict

┌──────────────────────────────────────────────────────────────────────────
│ AGENT · run_verdict   [template]
│ purpose     : Say whether this week's run is worth trusting, and recommend what to do about it
│ sensitivity : aggregate
│ routed to   : cloud
│ reads       : PSI table, overlap with previous run, score concentration, flags in top K, sum of probabilities vs the field rate
│ returns     : one paragraph, under 120 words
├─ SYSTEM ─────────────────────────────────────────────────────────────────
│ You write a weekly one-paragraph verdict on whether a scoring run is
│ worth trusting. You are allowed — expected — to say it is not. End with
│ a concrete recommendation for THIS week, not a general observation.
├─ PROMPT ─────────────────────────────────────────────────────────────────
│ Run of 2026-08-01. every feature is stable against training (max PSI 0.06, intent_score). Overlap of the top 30 with the previous run:
│ 30/30. the model's top-30 shares only 11/30 accounts with a plain sort by contact count. Of the top 30, 7 carry no flags. The model's predicted
│ probabilities sum to 19.7 expected conversions across 300 accounts (6.6%), against a
│ field rate the business reports at 1-3%.
│ 
│ Write the manager's paragraph. End with one concrete recommendation for this week.
├─ RETURNS (worked example) ───────────────────────────────────────────────
│ Run of 2026-08-01. Every feature is stable against training (max PSI 0.06); snapshot age is not — but that is how the batch was drawn, not drift. The top 30 shares 21 of 30 accounts with last week's list even though no underlying data changed, which is the model's own seed, not the market. Only 7 of the top 30 carry no flags at all. The model expects 19.7 conversions across 300 accounts (6.6%) against a field rate the business reports at 1–3%. Recommendation this week: run the exploit arm off sales_contacts, not off the score, and do not publish the probabilities.
└──────────────────────────────────────────────────────────────────────────

## Experiment

┌──────────────────────────────────────────────────────────────────────────
│ AGENT · experiment_card   [template]
│ purpose     : Write the week's allocation as an experiment the manager can approve or refuse
│ sensitivity : aggregate
│ routed to   : cloud
│ reads       : arms (name, size, selection rule), matching variables, base rate, readout date
│ returns     : markdown, ~150 words
├─ SYSTEM ─────────────────────────────────────────────────────────────────
│ You write experiment cards for an SDR manager who is not technical and
│ is sceptical of being experimented on. Be concrete about what each arm
│ is testing and what result would make us stop. Never oversell, and never
│ promise a lift number we do not have.
├─ PROMPT ─────────────────────────────────────────────────────────────────
│ This week's allocation splits 90 accounts into 3 matched arms
│ (industry and company size). Base rate is 6.5% in training, 1-3% per the business.
│ 
│ - **exploit** (30 accounts): highest logged contact count — the rule that beats the model out-of-sample
│ - **explore** (30 accounts): never contacted but carrying a signal (trial, MQL or web activity)
│ - **control** (30 accounts): the rep picks — this is what would happen without the system
│ 
│ Write the experiment card the SDR manager reads before approving. For each arm state the
│ hypothesis in one sentence, the result that would confirm it, and the result that would
│ kill it. End with the readout date and one sentence on why the control arm exists.
├─ RETURNS (worked example) ───────────────────────────────────────────────
│ (no worked example)
└──────────────────────────────────────────────────────────────────────────

## Actions awaiting your approval

| severity | owner | what | action |
|---|---|---|---|
| blocking | pipeline | It is unknown whether sales_contacts_90d precedes the outcome window or overlaps it | One question to the data owner: does the contact window PRECEDE the snapshot, or is it the same 90 days in which conversion is measured? If it overlaps, the one signal in this dataset is leakage and nothing built on it is real. |
| high | crm | Accounts are being scored on information older than the feature window | Refresh before assigning. No account over 180 days enters an arm without a refreshed snapshot. |
| high | crm | account_type does not mean what it says | Bulk-reclassify the 86 scoring accounts, and add a validation rule so an account with activity cannot be saved as Suspect. |
| high | model | The model's own arithmetic promises more conversions than the business sees | Do not publish probabilities to any user or Salesforce field. Use the score only for the disagreement analysis in RECONCILE. |
| high | model | The model ranks accounts that declined ABOVE accounts that are ready to buy | Never rank on this score. Where a conversation exists, it overrides; where it does not, use the explore arm rather than the score. Breaking the loop requires a signal that is not a function of our own past effort. |
| high | model | The model's ranking has never been validated out of sample in production | Re-run the permutation null and the forward-chaining split (audit §2.2, §2.6a) whenever the model or the data pipeline changes. No metric gets reported without a temporal split — that is how the last one shipped. |
| high | pipeline | Training labels are assigned before the 90-day window closes | Label = NULL, not 0, when snapshot_date + 90d > today. Re-label the 101 affected rows and add the rule to the labeling job. |
| high | process | Conversations that would fill the vendor's coverage gap already happen, and are not captured | Record sales calls with per-call disclosure and transcript-only storage, and extract intent per the contract in llm.py. Start with the fill_gap quadrant -- it needs no new outreach, only capture of calls that already happen. |
| high | process | The conversation layer changes decisions the score alone would get wrong | Extend recording to the 67 accounts in the fill-gap quadrant first: they already receive calls, so this needs no new rep time. Measure the same table against real outcomes at day 90. |
| medium | pipeline | Trials with zero active users are ambiguous | Ask product whether these are provisioned-but-never-used or missing seat telemetry. If telemetry, instrument it — the field is currently unreadable. |
| medium | vendor | The intent vendor overstates on accounts we can check | Run this table monthly on real calls and take it into the renewal. Pay for coverage, which predicts (p=0.003); stop paying for the score, which does not (p=0.42). |
| medium | vendor | web_touchpoints_90d cannot distinguish 'no visits' from 'not measured' | Data contract with the attribution vendor: return NULL when no measurement was taken. Until then, treat 0 as unknown rather than as a measured zero. |

## Not running today

| node | reason | unblocked_by |
|---|---|---|
| CONVERSATION_INTENT (coverage) | only 20 of 170 accounts with a logged call have a transcript, and those transcripts are synthetic | recording every call; then coverage equals the fill_gap + calibrate quadrants above |