#!/usr/bin/env bash
# Smoke test: every mode exits 0, the protected inputs are byte-identical, the audit scripts run.
# Not a test suite -- the brief does not want one. It is the ten lines I was running by hand.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
fail=0
for args in "" "--demo" "--approve" "--map" "--check-llm" "--demo --cycles 2 --reset-cycles"; do
  if $PY serving/pipeline.py $args >/dev/null 2>&1; then echo "  ok   pipeline.py $args"; else echo "  FAIL pipeline.py $args"; fail=1; fi
done
for s in audit/uplift.py audit/heldout_comparison.py audit/variable_scorecard.py; do
  if $PY "$s" >/dev/null 2>&1; then echo "  ok   $s"; else echo "  FAIL $s"; fail=1; fi
done
echo "fc2cd6aa4400c6bcad2df17a1f2c5473c4c60e93255d832a180ef1cbc312d08c  model/model.pkl" | sha256sum -c --quiet && echo "  ok   model.pkl untouched" || { echo "  FAIL model.pkl changed"; fail=1; }
echo "1a09c6390634ff1bb013e11fed2b3139616fdc8ebc4ac7a429ab6ca3f1b36460  data/accounts_to_score.csv
af7ac177ceddb80c547fc6769669ee9d31ac2a39d9077350f27b62ba1dbc507d  data/training_data.csv" | sha256sum -c --quiet && echo "  ok   CSVs untouched" || { echo "  FAIL a CSV changed"; fail=1; }
rm -f serving/out/cycles.jsonl serving/out/next_cycle.json      # leave no simulated memory behind
$PY serving/pipeline.py >/dev/null 2>&1                          # leave out/ in real-mode state
exit $fail
