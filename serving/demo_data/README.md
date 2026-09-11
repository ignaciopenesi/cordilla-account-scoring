# demo_data/ — synthetic, and labelled as such

> ⚠️ **Everything in this directory is fabricated.** It is not Cordilla data, it never
> touches `data/training_data.csv` or `data/accounts_to_score.csv`, and nothing derived
> from it is presented as a finding. Any output the pipeline produces from it is marked
> `demo` or `SIMULATED`.

## Why it exists

Three nodes cannot run on the two CSVs, because the inputs do not exist:
`CONVERSATION_INTENT` needs call transcripts, `CALIBRATE_VENDOR` needs the output of that,
and `READOUT` needs 90-day outcomes. Declaring them bypassed is honest, but a design you
cannot execute is hard to judge — and harder to poke holes in.

So: `python serving/pipeline.py --demo` runs the whole graph on synthetic inputs. **The
method is the deliverable; the numbers are not.**

## What is here

| file | what it is |
|---|---|
| `make_transcripts.py` | generates 20 transcripts from known intent levels, attached to real `account_id`s from the scoring file so the quadrant logic is exercised properly |
| `transcripts/*.txt` | the generated calls — 12 for accounts with a vendor record, 8 without, spread across all six intent levels |
| `ground_truth.json` | **the level each transcript was written to express**, plus role and next-step |
| `intents.json` | what the extraction agent actually returned, plus its measured accuracy |

## The part that is not just a demo

Because each transcript was generated *from* a known level, running the extractor over
them is a **measurement of the agent**, not a demonstration of it:

```bash
python serving/extract_intents.py          # batch, cached, resumable
```

It reports exact-level accuracy, within-one accuracy, hot-vs-cold accuracy, role accuracy
and mean self-reported confidence — and those numbers go into the pipeline's findings. If
the agent is not good enough to act on, the pipeline says so, in the same table as every
other defect.

That is deliberate. This repo spent a day establishing that the inherited model was trusted
without ever being measured. Introducing a new instrument and *not* measuring it would be
the same mistake with better branding.

## The readout is simulated under the null

`READOUT --demo` draws outcomes at the brief's own field rate (3%) with **no difference
between arms**. Not because that is the expected result — because the point of running it
is to show the shape of the readout and how little one cycle of 30 accounts per arm can
resolve. A demo that manufactured a flattering lift would be worth less than no demo.

## What a real deployment replaces

`transcripts/` → recorded calls with per-call disclosure and transcript-only storage
(Dialpad Ai Call Purpose / Custom Moments, or any ASR). `ground_truth.json` → nothing; in
production the agent is calibrated against conversion outcomes rather than against labels
someone wrote. `READOUT`'s simulated outcomes → the real ones, 90 days later.
