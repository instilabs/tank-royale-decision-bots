#!/bin/sh
# Generates bot dirs from template.py; bots differ only in MODEL, name, and
# brain ARCH (s1 = one fast decision model, s2 = one reasoning model,
# twotier = background S2 strategist + fast S1 tactician).
#
# Default: the four LOCAL bots (decima / largha / laya:en / winnow:e4b) that
# run against the local ollaya daemon. This is the set to point the
# Tank Royale GUI at.
# Cloud bots are opt-in: pass --with-cloud to also generate OllayaCloud,
# OllayaReasoner and OllayaTwoTier (they need OPENROUTER_API_KEY in the env;
# see tournament/README.md).
# Usage: sh make_bots.sh [--with-cloud] [target-dir]  (default: ./bots)
set -e
WITH_CLOUD=0
[ "$1" = "--with-cloud" ] && { WITH_CLOUD=1; shift; }
T="${1:-./bots}"
mkdir -p "$T"
gen() {
  name="$1"; model="$2"; arch="$3"; ormode="${4:-False}"; s2local="${5:-winnow:e4b}"
  mkdir -p "$T/$name"
  sed -e "s|__MODEL__|$model|" -e "s|__BOTNAME__|$name|" -e "s|__ARCH__|$arch|" -e "s|__OR_MODE__|$ormode|" -e "s|__S2LOCAL__|$s2local|" template.py > "$T/$name/$name.py"
  printf '{"name": "%s", "version": "1.5", "authors": ["instibit"], "description": "Ollaya-driven tank (%s, %s)", "homepage": "", "countryCodes": ["sg"], "platform": "Python", "programmingLang": "Python 3", "license": "Apache-2.0"}' "$name" "$model" "$arch" > "$T/$name/$name.json"
  { printf '%s\n' '#!/bin/sh' 'cd "$(dirname "$0")"' '# Prefer a project .venv (repo root or this bot dir); fall back to system python3.' 'if [ -x "../.venv/bin/python3" ]; then' '  PY="../.venv/bin/python3"' 'elif [ -x ".venv/bin/python3" ]; then' '  PY=".venv/bin/python3"' 'else' '  PY="python3"' 'fi'; printf 'exec "$PY" %s.py\n' "$name"; } > "$T/$name/$name.sh"
  chmod +x "$T/$name/$name.sh"
  echo "wrote $T/$name ($model, $arch)"
}
# The four local bots (default set - point the Tank Royale GUI at these)
gen OllayaDecima decima:small s1
gen OllayaLargha largha s1
gen OllayaLaya laya:en s1
gen OllayaWinnow winnow:e4b s1
if [ "$WITH_CLOUD" = 1 ]; then
  # System-1-only cloud guest (OpenRouter)
  gen OllayaCloud nvidia/nemotron-3.5-lightning:free s1 True
  # System-2-only: one reasoning model, blocking (cloud default; local via MODEL)
  gen OllayaReasoner nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free s2 True
  # Two-tier: local S1 tactician + S2 strategist (cloud default; local via MODEL)
  gen OllayaTwoTier decima:small twotier True
fi
