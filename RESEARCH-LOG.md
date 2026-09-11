# Research log

Kept as I go. Timestamps are local (UTC-3). Entries are appended, never rewritten —
where I was wrong later, the correction is a new entry, not an edit of the old one.

Exercise received 2026-09-10 ~21:30 local. 24h hard deadline → 2026-09-11 ~21:30.
Suggested time-box ~4h.

**AI tooling used:** Claude (chat) for the first exploratory pass, then Claude Code
(Opus 5) inside VS Code for everything in this repo. All on my own personal account.
Every session that shaped a decision is logged below with what I asked and what I did
with the answer.

---

## Entry 0 — 2026-09-10 ~21:00 · Exploratory pass, before opening the repo

**Where I started.** The VP's ask ("build us a dashboard so reps stop guessing") is a
solution, not a problem. So the first question isn't technical: *who decides what, and
what would tell us it's working?* I parked that and went to the data, because I can't
frame the decision without knowing what the instrument can and can't say.

**What I did.** A long exploratory session with Claude (chat), working over
`training_data.csv`, `accounts_to_score.csv` and `model.pkl`. I deliberately ran it as a
*debate* rather than a Q&A: I had it argue the case from six conflicting positions (an
auditor, the VP of Sales, an SDR, a data engineer, a governance/trust lens, and an AI
product lens), each one required to attack the others with numbers. The point was to
avoid the failure mode where the model agrees with whatever frame I hand it.

**Output.** A ~270-line working document (kept out of this repo — it's scratch, in
Spanish, and half of it didn't survive verification) with roughly 80 concrete numeric
claims about the model and the data.

**What I got out of it, in one line each:**
- The model *orders* acceptably and *quantifies* badly. Those are two different products.
- Three separate contaminations: right-censored labels, median imputation of the single
  most important feature, and a feature that measures our own team's behaviour.
- The brief's own framing contradicts the data in at least two places.

**TODO(ignacio): paste the 3-4 actual prompts from this session that shaped a decision.**
The packet asks for specific prompts, not a summary. Pull them from the chat history —
particularly the one that set up the six-lens debate, and whichever follow-up made it
produce the calibration-by-decile table.

**Dead end from this session:** my first instinct was to ask "is the model any good?"
and I got back a generic model-evaluation checklist — AUC, precision/recall, class
imbalance, the usual. Correct and useless. It described what an audit *could* look like
instead of auditing anything. The packet warns about exactly this. I dropped it and
re-asked against the actual files, forcing every claim to carry a number computed from
the data.

---

## Entry 1 — 2026-09-10 ~21:40 · Repo setup, and not trusting my own first pass

**Setup.** Committed the starter scaffold untouched as commit 1, so every later diff is
visibly my own work. `.venv` on Python 3.12 with the pinned versions (scikit-learn 1.5.2
matters — the pickle was written by it).

**Decision: verify before building.** I was about to start writing `audit/` off the back
of Entry 0. I didn't, for one reason: I have to defend those ~80 numbers live, on my own,
in front of a panel. A number I got from a chat session and never recomputed is a number
I can't defend. Being able to *explain and modify the result myself* is stated as part of
what's being evaluated, and I read "explain" as including "I re-derived it."

**What I ran.** A verification pass that splits the claims into eight blocks
(model internals, calibration/lift, censoring, imputation, `sales_contacts`, taxonomy,
freshness/drift, scoring-set serving numbers), recomputes each block from the raw files
with independent code, and then re-computes *from scratch, with a second independent
script* every claim that didn't confirm on the first pass. Plus an adversarial pass whose
only job is to find what the analysis never checked and what a panel would attack.

Everything it reports goes into `audit/` only after I've read the script that produced it.

**Hypothesis going in (recorded now so I can be wrong in public):** the numbers I most
expect to move are (a) the 6.2× lift in the top 30, because it's computed in-sample *with
the censored rows still in*, and (b) the "341 Suspects with activity" figure, which is
larger than the 300-row scoring file it seemed to be describing.

**TODO(ignacio): result of that check goes in Entry 2.**

---
