# The metric — run of 2026-08-01

## The scorecard

| | the list it says to call | historical, real outcomes — of the 90 called, how many convert · of the buyers, how many found | prospective, day 90 | rep-hours it refuses to spend |
|---|---|---|---|---|
| model alone — the dashboard the VP asked for | top 90 by score | **6.7%** [3%, 14%] · finds **8%** of buyers · *from memory: 31.1%* | _not yet — READOUT_ | 0 — calls everything it ranks |
| random — no system | 90 at random | **7.3%** 5–95%: [3%, 11%] · finds **8%** of buyers | _not yet — READOUT_ | 0 — calls everything it ranks |
| the team today — rep's own picks | accounts the team chose to work | **8.3%** [6%, 11%] | _not yet — READOUT_ | 0 — calls everything it ranks |
| **THE GRAPH — its worklist** | continue 45 + first-call 15 · ask, observe and skip tracked, not called | **12.2%** [7%, 21%] · finds **14%** of buyers | _not yet — READOUT_ | **38 h / quarter** |
| the graph — confident picks only | continue alone | **15.6%** [9%, 24%] · finds **18%** of buyers | _not yet — READOUT_ | — |

_Historical: each policy builds its list from the 1,099 labelled training rows with a closed 90-day window, and we count who converted — observational, the comparison is fair, the levels are not causal. Prospective: the arms READOUT assigns today, read at day 90 against control — causal, and not readable before ~2,500 per arm. The graph must beat the first three rows on both columns, or it is retired._

_Two numbers, and the hierarchy between them is structural rather than typographic. The fast one is printed as a bet with the date it settles and the result that falsifies it, so it cannot be read as an outcome. The previous scoring effort had no such record, which is why nobody could write up why it stopped working._

## What an hour costs today

- **24.6 logged contacts per conversion** (4.9 rep-hours at 12 min/contact — a parameter, not a finding; it cancels out of every arm-vs-arm comparison)
- **260 of 481 contacts (54%)** sit in 52 of 300 accounts
- **789 contacts** of historical effort went into accounts that never converted — a *stock*, spent once

And the reason none of this can be optimised directly: the same yield curve says *call more* read as a rate and *never call twice* read as a cost. Contact count is an effect of intent as much as a cause of conversion, so **no observational cut of this data yields conversions-per-hour**. The arms are the instrument.

| contacts | accounts | conversions | conv rate | contacts per conversion |
|---|---|---|---|---|
| 0 | 487 | 23 | 4.7% | n/a |
| 1 | 188 | 13 | 6.9% | 14 |
| 2 | 176 | 11 | 6.2% | 32 |
| 3 | 159 | 9 | 5.7% | 53 |
| 4 | 100 | 10 | 10.0% | 40 |
| 5 | 59 | 8 | 13.6% | 37 |
| 6 | 18 | 1 | 5.6% | 108 |
| 7 | 10 | 2 | 20.0% | 35 |

## 1 · North star — *not readable yet, and that is the honest answer*

**conversions per 100 logged contacts, by arm, cumulative**

- needs **2,515 accounts per arm** to detect a 50% relative lift at the field rate (1,106 at the training rate)
- at today's 30 per arm per cycle: **168 weeks**. Assigning **97 per arm** instead lands it in two quarters, with no new rep hours.

## 2 · Weekly headline — *a bet, not a result*

**rep-hours held pending a question (ask) and not spent where calling never helped (skip)** — observable today, on the row -- a saving, not yet a result

- the recoverable stock is 789 contacts and is spent once; a falling number here is the system working, not failing

### Bets outstanding

| bet | claim | settles | falsified_if |
|---|---|---|---|
| redirected hours convert better than the hours they replaced | conversions per 100 rep-hours are higher in the system's third than in the control third, every account counted | not before 2,515 accounts per arm (168 weeks at 15/arm, 26 cycles at 97/arm) | the cumulative interval for the system's third sits below the control third's once the halves are powered — at which point the system is reallocating hours to worse places |

## Guardrails — what must not get worse while the bets mature

| guardrail | must_not | why |
|---|---|---|
| rep acceptance of the worklist | fall below 65% | adoption is what killed the previous effort, and it fails before any metric moves |
| contacts logged against accounts that stated a decline | rise | the release must actually take effect, not just be recommended |
| conversion of stale vs fresh accounts within each arm | diverge — stale converting materially below fresh | the working hypothesis is that a two-quarter-old description is still actionable; this is where it gets tested, and if it fails the flag becomes a filter |
| never-contacted accounts entering an arm each cycle | fall to zero | exploration going to zero is how the system stops producing unbiased data |

## Proxy validity — the writeup nobody did last time

at each 90-day readout, does the weekly headline still track the north star?  
**Rule:** if redirected hours stop predicting conversions per 100 contacts, the weekly metric is retired — in the same report, not quietly

## Kill switch

if the system third's cumulative rate sits below the control third's once both pass 2,515 accounts, the reallocation is wrong and the system stops directing hours.