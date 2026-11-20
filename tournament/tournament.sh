#!/bin/sh
# Round-robin 1v1 tournament: every pair battles, logs to tourney-logs/.
# Usage: sh tournament.sh <bots-dir> <runner-jar> [rounds-per-battle]
set -e
BOTS="${1:-./bots}"
JAR="${2:-./robocode-tankroyale-runner-1.4.0.jar}"
ROUNDS="${3:-3}"
mkdir -p tourney-logs .pairs
for a in "$BOTS"/*/; do
  for b in "$BOTS"/*/; do
    [ "$a" = "$b" ] && continue
    an=$(basename "$a"); bn=$(basename "$b")
    pair=$(printf '%s\n%s\n' "$an" "$bn" | sort | tr '\n' '-' | sed 's/-$//')
    [ -f ".pairs/$pair" ] && continue
    touch ".pairs/$pair"
    log="tourney-logs/$pair.log"
    echo "=== $pair -> $log"
    java -Xmx512M -cp "$JAR" RunTourney.java "$a" "$b" "$ROUNDS" > "$log" 2>&1
    grep RESULT "$log"
  done
done
rm -rf .pairs
echo "Tournament done. Analyze: python3 analyze.py tourney-logs"
