# Tournament kit: 4 local models + an optional cloud guest

Round-robin battles between identical bots whose only difference is the model
driving them. The model is the differentiator: decision speed and accuracy
decide who lives. An optional 5th bot runs on a free OpenRouter model as the
"cloud guest" - it thinks on a throttled cadence, so the audience sees the
cloud brain lag while the local brains run rings around it.

## Setup

```sh
# 1. Start ollaya (port 11435) and pull the four local models
# 2. Generate the four local bot dirs (the default set - local only)
sh make_bots.sh ./bots          # OllayaDecima / OllayaLargha / OllayaLaya / OllayaWinnow
sh make_bots.sh --with-cloud ./bots   # also: OllayaCloud / OllayaReasoner / OllayaTwoTier
```

## Cloud guest (optional, free)

OllayaCloud switches to OpenRouter when `OPENROUTER_API_KEY` is set:

```sh
export OPENROUTER_API_KEY=sk-or-...          # free key from openrouter.ai
export OR_MODEL=nvidia/nemotron-3.5-lightning:free # optional; any :free model works
export OR_MIN_INTERVAL_S=3.5                 # optional; decision cadence (seconds)
```

Free-tier limits are 20 requests/min and 50 requests/day per account, so the
default 3.5s cadence keeps it under the cap with margin. Note the 50/day cap
is roughly one full melee - rehearse sparingly, or buy $10 of credits for a
1000/day cap. On any error/429/timeout the bot hesitates, same as the local
bots. Other free models that work well: 
apodex/apodex-1.1-mini:free, nvidia/nemotron-3.5-lightning:free.

## Brain architectures (v1.5)

Three architectures share the same tank physics and control - only the brain
wiring differs (baked per bot via `__ARCH__`):

- **s1** - one fast decision model answers "aggressive / evasive / probe"
  every 40 ticks, blocking. The local bots and OllayaCloud.
- **s2 (OllayaReasoner)** - one reasoning model thinks, then answers the same
  one word. Generous token budget (`OR_S2_MAX_TOKENS=2048`), 30s timeout
  (`OR_S2_TIMEOUT_S`), throttled cadence; the tank coasts on last orders
  while it thinks. Cloud default `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
  (override with `OR_S2_MODEL`); with no `OPENROUTER_API_KEY` it uses the
  local `S2_LOCAL_MODEL` (default winnow:e4b) via ollaya.
- **twotier (OllayaTwoTier)** - a background thread runs the S2 strategist
  every `S2_INTERVAL_S` seconds (default 10), producing a posture
  (stance / target / fire). The fast local S1 (decima:small) reads the latest
  posture and decides tactics every 40 ticks. If S2 hasn't answered or fails,
  S1 fights alone. S2 is cloud when `OPENROUTER_API_KEY` is set, else local
  `S2_LOCAL_MODEL`.

DECIDE lines carry a `tier=S1|S2` tag so `analyze.py` can compare tiers:
  `DECIDE[OllayaTwoTier] tier=S2 model=... result=stance=aggressive,target=nearest,fire=high energy=83 ms=1557`

## Round-robin 1v1 tournament

```sh
sh tournament.sh ./bots robocode-tankroyale-runner-1.4.0.jar 3
python3 analyze.py tourney-logs
```

Every pair battles `3` rounds (change the last arg). Bot stderr (DECIDE/KILL
lines) goes to the runner's bot log under the default bot-log dir.

## 4-way melee (or 5-way with the cloud guest)

```sh
java -cp robocode-tankroyale-runner-1.4.0.jar RunMelee.java \
  ./bots/OllayaDecima ./bots/OllayaLargha ./bots/OllayaLaya ./bots/OllayaWinnow 5
# add ./bots/OllayaCloud for the 5-way
```

Prints `RESULT rank=...` per bot to stdout.

## Notes

- All bots share `template.py`: identical code, prompts and fallback. Only
  `__MODEL__` and `__BOTNAME__` differ. Keep it that way when editing.
- Local mode: blocking decision call every 40 ticks, 5s timeout. Cloud mode:
  at most one decision per OR_MIN_INTERVAL_S seconds, coasting on last orders
  in between - a visibly slower brain by design.
- winnow:e4b is an 8GB model - needs RAM headroom. laya:en (fp32, 853MB)
  needs roughly 2GB+ free.
- DECIDE line format, grep it from any bot log:
  `DECIDE[OllayaDecima] model=decima:small result=aggressive energy=80 ms=172`
