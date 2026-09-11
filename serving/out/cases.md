# Cases — run of 2026-08-01

_Named accounts, real data, no transcript. Each case shows the model's rank beside the rule that places it here and the evidence behind that rule, estimated on the older labelled rows. What every case proves today: a decision the model would have made differently, and why. What none can prove yet: that this decision converts better — that is day 90._

## The model's top 30 this system will not call as-is — 11 accounts

_The model ranks them high because of the contacts already spent (its strongest feature). Here they go to `ask` (5+ contacts, no result — one question to the rep before the next hour) or `skip` (web-only or MQL-only — calling never helped on any cut)._

| account | model rank | score | contacts | segment | trial | age | here | evidence | why |
|---|---|---|---|---|---|---|---|---|---|
| `ACC-01491` | #1 | 20.9% | 5 | trial | yes | 290d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-01064` | #3 | 18.7% | 5 | trial | yes | 94d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00122` | #7 | 14.8% | 6 | web | — | 38d | skip → `skip` | — | calling never helped this segment |
| `ACC-00646` | #8 | 14.8% | 6 | mql | — | 272d | skip → `skip` | — | calling never helped this segment |
| `ACC-00265` | #14 | 12.2% | 5 | trial | yes | 93d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00146` | #16 | 12.2% | 5 | trial | yes | 192d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-01155` | #19 | 11.6% | 7 | vendor | — | 30d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00958` | #23 | 11.2% | 5 | none | — | 409d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00686` | #25 | 11.1% | 6 | trial | yes | 143d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00832` | #26 | 11.0% | 5 | vendor | — | 52d | ask → `ask` | — | sunk cost — the rep answers first |
| `ACC-00101` | #30 | 10.7% | 6 | vendor | — | 140d | ask → `ask` | — | sunk cost — the rep answers first |

## The untouched trials — 25 accounts, the highest-uplift first call

_Someone is using the product and nobody has called. History: untouched trials convert at 6.6%; with 1–4 calls, 11.5% — **+5 points**, an upper bound (reps chose whom to call). Half are called (`first-call`), half held back (`observe`), so day 90 measures the real number. The model ranks them at median #108 of 300._

| account | model rank | score | contacts | segment | trial | age | here | evidence | why |
|---|---|---|---|---|---|---|---|---|---|
| `ACC-01157` | #88 | 7.4% | 0 | trial | yes | 130d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00433` | #136 | 5.7% | 0 | trial | yes | 515d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00802` | #36 | 10.2% | 0 | trial | yes | 113d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00285` | #95 | 7.1% | 0 | trial | yes | 143d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00086` | #108 | 6.5% | 0 | trial | yes | 109d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-01269` | #122 | 6.0% | 0 | trial | yes | 598d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-01337` | #142 | 5.6% | 0 | trial | yes | 130d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00552` | #104 | 6.8% | 0 | trial | yes | 82d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00498` | #133 | 5.7% | 0 | trial | yes | 263d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00962` | #53 | 9.2% | 0 | trial | yes | 321d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-01201` | #163 | 5.0% | 0 | trial | yes | 110d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-00483` | #126 | 5.9% | 0 | trial | yes | 32d | first-call → `first-call` | +5.0 pts uplift (train) | called this week |
| `ACC-01404` | #64 | 8.4% | 0 | trial | yes | 105d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-01394` | #57 | 8.8% | 0 | trial | yes | 81d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00076` | #34 | 10.3% | 0 | trial | yes | 87d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00011` | #137 | 5.7% | 0 | trial | yes | 148d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00200` | #68 | 8.3% | 0 | trial | yes | 116d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00398` | #98 | 7.0% | 0 | trial | yes | 129d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-01020` | #120 | 6.2% | 0 | trial | yes | 86d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00787` | #54 | 9.1% | 0 | trial | yes | 119d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00564` | #123 | 6.0% | 0 | trial | yes | 104d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-01151` | #102 | 6.9% | 0 | trial | yes | 61d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-01091` | #114 | 6.3% | 0 | trial | yes | 457d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00264` | #110 | 6.4% | 0 | trial | yes | 45d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |
| `ACC-00531` | #146 | 5.5% | 0 | trial | yes | 89d | first-call → `observe` | +5.0 pts uplift (train) | held back at random — the control for the +10 |

## Buried by the model, called first here — 9 accounts

_In conversation (1–4 contacts) with a trial or a vendor record; the model ranks them below #150. `continue` takes them ahead of the model's picks._

| account | model rank | score | contacts | segment | trial | age | here | evidence | why |
|---|---|---|---|---|---|---|---|---|---|
| `ACC-00453` | #227 | 4.4% | 3 | vendor | — | 136d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00619` | #217 | 4.5% | 3 | vendor | — | 311d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00541` | #199 | 4.6% | 3 | vendor | — | 101d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00779` | #197 | 4.7% | 3 | vendor | — | 96d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00043` | #182 | 4.8% | 3 | vendor | — | 34d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00471` | #181 | 4.8% | 3 | vendor | — | 97d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00116` | #176 | 4.8% | 3 | vendor | — | 647d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00362` | #175 | 4.9% | 3 | vendor | — | 75d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |
| `ACC-00272` | #165 | 5.0% | 3 | vendor | — | 555d | continue → `continue` | 7.3% in conversation (train) | vendor segment, in conversation |

## The skip bucket — 74 accounts, 124 contacts already sunk

_Web-only or MQL-only. On every cut of history, calling these segments changed nothing (uplift ≤ 0). **25 rep-hours** went here last quarter; none go here this week. They stay tracked: if they convert anyway, the rule was wrong._

By segment: {'mql': 38, 'web': 36} · with contacts already: 42

## The ask cohort — 23 accounts, 133 contacts already sunk

_5+ contacts and no conversion. The model loves them (median rank #35). History says accounts like these convert at ~17% *if you keep calling* — and cost ~6 calls each to get there. The rep gets one question; the answer sends each to `continue` or to rest. **27 rep-hours** held._

## How to read the levels

| level | when | what it proves | what it cannot |
|---|---|---|---|
| named cases (above) | today | a decision the model would have made differently, with the rule and its evidence | that the decision converts better |
| uplift by segment | today | where a call changed the outcome in history — as an upper bound | the true effect of a call |
| first-call vs observe | day 90 | the true effect of the first call on a trial account | — |
| conversions per 100 contacts by arm | quarter 2 | that the hours went to a better place | — |