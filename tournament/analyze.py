import os, re, sys
from collections import defaultdict

# Parses tourney-logs/*.log: pair standings + per-model decide-time stats.
logs = sys.argv[1] if len(sys.argv) > 1 else "tourney-logs"
wins = defaultdict(int); battles = defaultdict(int)
times = defaultdict(list); fails = defaultdict(int)

for f in sorted(os.listdir(logs)):
    pair = None
    for line in open(os.path.join(logs, f), errors="replace"):
        if line.startswith("==="):
            pair = line.split()[1]
            battles[pair] += 1
        elif line.startswith("RESULT rank=1"):
            wins[re.search(r"name=(\S+)", line).group(1)] += 1
        elif "DECIDE[" in line:
            bot = re.search(r"DECIDE\[(\w+)\]", line).group(1)
            model = re.search(r"model=(\S+)", line).group(1)
            tier = re.search(r"tier=(\S+)", line)
            key = f"{model} ({tier.group(1)})" if tier else model
            ms = re.search(r"ms=(\d+)", line)
            if ms: times[key].append(int(ms.group(1)))
            if "error" in line: fails[key] += 1

print("\n== Battle wins ==")
for b, w in sorted(wins.items(), key=lambda kv: -kv[1]):
    print(f"  {b:<15} {w} win(s)")
print("\n== Per-model decide times ==")
for m, ts in sorted(times.items()):
    ts.sort()
    print(f"  {m:<15} n={len(ts):<4} median={ts[len(ts)//2]}ms  min={ts[0]}ms  max={ts[-1]}ms  errors={fails[m]}")
