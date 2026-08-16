#!/usr/bin/env bash
# Randomized end-to-end check: does the agent relay the tool's number faithfully?
#
# For each case: compute ground truth from the tool directly, ask the agent the
# same thing in plain English (never naming the tool), then compare. Parameters
# are deliberately awkward so a memorised textbook answer cannot pass.
#
# Usage: ./randomized_check.sh [model] [n_cases]
set -u
MODEL="${1:-ollama/qwen3.5}"
N="${2:-6}"
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"
cd "$(dirname "$0")"

pass=0; fail=0
for i in $(seq 1 "$N"); do
  # Awkward values; two slots reserved for edge cases (no contributions, no capital).
  read -r CAP RATE MON YRS <<EOF
$(python3 - "$i" "$N" <<'PY'
import random, sys
i, n = int(sys.argv[1]), int(sys.argv[2])
random.seed()
if i == n - 1:      # edge: no monthly contributions (pure compound growth)
    cap, mon = random.randint(1000, 90000), 0
elif i == n:        # edge: no starting capital (pure annuity)
    cap, mon = 0, random.randint(50, 900)
else:
    cap, mon = random.randint(137, 88000), random.randint(17, 1450)
rate = round(random.uniform(0.011, 0.119), 4)   # 1.1%-11.9%, 4dp
yrs  = random.choice([2, 3, 7, 11, 16, 23, 29, 34, 41])
print(cap, rate, mon, yrs)
PY
)
EOF

  GT=$(python3 -c "
from retirement import future_value
print(f'{future_value($CAP, $RATE, $MON, $YRS):.2f}')")
  PCT=$(python3 -c "print(round($RATE*100, 2))")

  Q="I have \$$CAP invested at a ${PCT}% annual return and add \$$MON every month. What will it be worth in $YRS years?"

  openclaw agent --local --json --session-key "rnd-$i-$RANDOM" \
    --model "$MODEL" --thinking off --timeout 900 \
    --message "$Q" 2>/dev/null > "/tmp/rnd$i.json"

  RESULT=$(GT="$GT" python3 - "$i" <<'PY'
import json, os, re, sys
gt = float(os.environ["GT"])
try:
    d = json.load(open(f"/tmp/rnd{sys.argv[1]}.json"))
except Exception as e:
    print(f"ERROR no-json {e}"); raise SystemExit
ts  = d.get("meta", {}).get("toolSummary", {})
txt = " ".join(p.get("text", "") for p in d.get("payloads", []))
nums = []
for m in re.findall(r"\d[\d,]*(?:\.\d+)?", txt):
    try: nums.append(float(m.replace(",", "")))
    except ValueError: pass
# accept whole-dollar rounding
hit = any(abs(n - gt) <= 1.0 for n in nums)
print(f"{'PASS' if hit else 'FAIL'} calls={ts.get('calls')} failures={ts.get('failures')} "
      f"| said={[n for n in nums if abs(n-gt)<=1.0] or nums[:2]}")
PY
)
  echo "case $i: cap=$CAP rate=${PCT}% mon=$MON yrs=$YRS -> truth=$GT"
  echo "         $RESULT"
  case "$RESULT" in PASS*) pass=$((pass+1));; *) fail=$((fail+1));; esac
done

echo
echo "TOTAL: $pass passed, $fail failed (model=$MODEL)"
