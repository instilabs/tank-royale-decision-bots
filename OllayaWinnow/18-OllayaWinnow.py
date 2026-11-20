import json, math, os, sys, threading, time, urllib.request
from robocode_tank_royale.bot_api.bot import Bot
from robocode_tank_royale.bot_api.events import ScannedBotEvent, BotDeathEvent, DeathEvent

OLLAYA = "http://127.0.0.1:11435/v1/systemone"
MODEL = "winnow:e4b"          # local ollaya model for this bot's S1 (or S2-local) brain
BOTNAME = "OllayaWinnow"
ARCH = "s1"            # s1 | s2 | twotier

# Cloud (OpenRouter) mode: baked per bot by make_bots.sh. With OPENROUTER_API_KEY
# set, OR_MODE bots call OpenRouter instead of local ollaya. Local bots ignore
# the env key on purpose.
OR_MODE = False
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "") if OR_MODE else ""
OR_URL = os.environ.get("OR_URL", "https://openrouter.ai/api/v1/chat/completions")
OR_MODEL = os.environ.get("OR_MODEL", MODEL if MODEL.endswith(":free") else "nvidia/nemotron-3.5-lightning:free")
OR_MIN_INTERVAL = float(os.environ.get("OR_MIN_INTERVAL_S", "3.5"))

# System-2 (reasoning) settings, arch=s2 and the S2 tier of arch=twotier.
# S2 may think before answering: generous token budget, 30s timeout; the tank
# coasts on last orders while it thinks (arch=s2) or a background thread thinks
# (arch=twotier). S2_MODEL overrides the cloud model; S2 local model is MODEL.
S2_MODEL = os.environ.get("OR_S2_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
S2_LOCAL_MODEL = os.environ.get("S2_LOCAL_MODEL", "winnow:e4b")  # local ollaya S2 brain
S2_MAX_TOKENS = int(os.environ.get("OR_S2_MAX_TOKENS", "2048"))
S2_TIMEOUT = float(os.environ.get("OR_S2_TIMEOUT_S", "30"))
S2_INTERVAL = float(os.environ.get("S2_INTERVAL_S", "10"))  # twotier: S2 cadence

_MODES = ("aggressive", "evasive", "probe")
_SYSTEM = ("You are the combat brain of a Robocode tank. "
           "Reply with exactly one word: aggressive, evasive, or probe. "
           "Aggressive pursuit wins battles - prefer it.")
_SYSTEM_S2 = ("You are the combat brain of a Robocode tank. "
              "Think briefly, then reply with exactly one word as your final "
              "answer: aggressive, evasive, or probe.")
_SYSTEM_POSTURE = ("You are the strategic brain of a Robocode tank. Assess the "
                   "situation and answer with exactly one line: "
                   "stance=X target=Y fire=Z where X is aggressive|evasive|probe, "
                   "Y is nearest|weakest, Z is high|low.")


class OllayaBot(Bot):
    """Same tank physics and control for every bot; only the brain architecture
    differs. s1: one fast decision model. s2: one reasoning model, blocking.
    twotier: background S2 strategy posture + fast S1 tactics each tick."""

    def __init__(self):
        super().__init__()
        self.mode = "hesitate"
        self.enemy = "none"
        self.ex = self.ey = None
        self.last_seen = -999
        self.last_or_call = 0.0
        self.posture = None        # twotier: latest S2 posture dict or None
        self.posture_age = -999    # wall-clock time of latest posture

    def run(self):
        self.adjust_radar_for_gun_turn = True
        if ARCH == "twotier":
            threading.Thread(target=self._s2_loop, daemon=True).start()
        while self.running:
            if self.turn_number % 40 == 0:
                self.mode = self.decide()   # s1/s2 block: bot coasts on last orders
            self.act()
            self.go()

    def act(self):
        seen = self.ex is not None and self.turn_number - self.last_seen < 30
        if "aggress" in self.mode and seen:
            self.turn_to(self.dir_to(self.ex, self.ey))
            self.set_forward(40000)
            self.lock_on()
        elif "evade" in self.mode and seen:
            # dodge-and-counter: close at an angle, still attacking
            self.turn_to(self.dir_to(self.ex, self.ey) + 45)
            self.set_forward(40000)
            self.lock_on()
        elif "probe" in self.mode or not seen:
            # search: fast arc, wide fast radar sweep
            self.set_forward(150)
            self.set_turn_left(25)
            self.set_turn_radar_right(90)
        else:
            self.set_forward(40)
            self.set_turn_radar_right(30)

    def lock_on(self):
        self.set_turn_radar_right(self.norm(self.radar_dir_to(self.ex, self.ey)) * 2)
        self.set_turn_gun_right(self.norm(self.dir_to(self.ex, self.ey) - self.gun_direction))

    def on_scanned_bot(self, e: ScannedBotEvent):
        self.ex, self.ey = e.x, e.y
        self.last_seen = self.turn_number
        dist = math.hypot(e.x - self.x, e.y - self.y)
        self.enemy = f"dist={int(dist)} energy={int(e.energy)}"
        self.turn_gun_to(self.dir_to(e.x, e.y))
        self.fire(max(1.0, min(3.0, 400.0 / max(dist, 1.0))))

    def on_bot_death(self, e: BotDeathEvent):
        print(f"KILL[{BOTNAME}]: enemy {e.victim_id} destroyed", file=sys.stderr, flush=True)

    def on_death(self, e: DeathEvent):
        print(f"DIED[{BOTNAME}]", file=sys.stderr, flush=True)

    def turn_gun_to(self, target):
        d = self.norm(target - self.gun_direction)
        if d >= 0:
            self.set_turn_gun_left(d)
        else:
            self.set_turn_gun_right(-d)

    @staticmethod
    def norm(a):
        a %= 360
        return a - 360 if a > 180 else a

    def dir_to(self, x, y):
        return math.degrees(math.atan2(x - self.x, y - self.y)) % 360

    def radar_dir_to(self, x, y):
        return self.norm(self.dir_to(x, y) - self.radar_direction)

    def turn_to(self, target):
        d = self.norm(target - self.direction)
        if d >= 0:
            self.set_turn_left(d)
        else:
            self.set_turn_right(-d)

    # ---- brains ----------------------------------------------------------

    def decide(self):
        state = (f"Robocode tank battle. My energy={int(self.energy)}. "
                 f"Enemy: {self.enemy}")
        if ARCH == "s2":
            return self._decide_s2(state)
        if ARCH == "twotier":
            p = self.posture
            if p and time.time() - self.posture_age < S2_INTERVAL * 3:
                state += (f". Strategist advises: stance={p['stance']} "
                          f"target={p['target']} fire={p['fire']}")
            return self._decide_local(state, MODEL, tier="S1")
        # arch=s1
        if OR_KEY:
            return self._decide_cloud_s1(state)
        return self._decide_local(state, MODEL, tier="S1")

    def _decide_s2(self, state):
        if OR_KEY:
            now = time.time()
            if self.last_or_call and now - self.last_or_call < OR_MIN_INTERVAL:
                return self.mode  # throttled: coast on last orders
            self.last_or_call = now
            # reasoning model: thinks first, generous budget, parse final word
            body = {"model": S2_MODEL, "max_tokens": S2_MAX_TOKENS, "temperature": 0,
                    "messages": [{"role": "system", "content": _SYSTEM_S2},
                                 {"role": "user", "content": state}]}
            return self._call_cloud(body, S2_MODEL, "S2", S2_TIMEOUT, parse=self._parse_final)
        return self._decide_local(state, S2_LOCAL_MODEL, tier="S2", timeout=S2_TIMEOUT)

    def _s2_loop(self):
        # twotier background strategist: a fresh posture every S2_INTERVAL seconds
        while self.running:
            state = (f"Robocode tank battle. My energy={int(self.energy)}. "
                     f"Enemy: {self.enemy}")
            t0 = time.time()
            if OR_KEY:
                body = {"model": S2_MODEL, "max_tokens": S2_MAX_TOKENS, "temperature": 0,
                        "messages": [{"role": "system", "content": _SYSTEM_POSTURE},
                                     {"role": "user", "content": state}]}
                p = self._call_cloud(body, S2_MODEL, "S2", S2_TIMEOUT,
                                     parse=self._parse_posture, want_mode=False)
            else:
                p = self._posture_local(state, t0)
            if p:
                self.posture, self.posture_age = p, time.time()
            dt = time.time() - t0
            if dt < S2_INTERVAL:
                time.sleep(S2_INTERVAL - dt)

    # ---- tier calls ------------------------------------------------------

    def _decide_local(self, state, model, tier, timeout=5):
        body = {"model": model, "state": state, "questions": {"mode": {
            "type": "choice",
            "instructions": "Pick the combat strategy. Aggressive pursuit wins battles - prefer it.",
            "criteria": {"aggressive": "hunt down the enemy and fire",
                          "evasive": "close in while dodging enemy fire",
                          "probe": "sweep a moving arc to find a lost enemy"}}}}
        t0 = time.time()
        try:
            req = urllib.request.Request(
                OLLAYA, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                c = json.load(r)["answers"]["mode"]["choice"]
            ms = int((time.time() - t0) * 1000)
            print(f"DECIDE[{BOTNAME}] tier={tier} model={model} result={c} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return c
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            print(f"DECIDE[{BOTNAME}] tier={tier} model={model} error={ex} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return "hesitate"

    def _posture_local(self, state, t0):
        body = {"model": S2_LOCAL_MODEL, "state": state, "questions": {
            "stance": {"type": "choice",
                       "instructions": "Pick the strategic stance for the next phase.",
                       "criteria": {"aggressive": "press the attack",
                                     "evasive": "survive and reposition",
                                     "probe": "gather information"}},
            "target": {"type": "choice", "instructions": "Which enemy to focus?",
                       "criteria": {"nearest": "closest threat",
                                     "weakest": "lowest energy"}},
            "fire": {"type": "choice", "instructions": "How freely to spend energy on fire?",
                     "criteria": {"high": "fire at every opening",
                                   "low": "conserve energy"}}}}
        try:
            req = urllib.request.Request(
                OLLAYA, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=S2_TIMEOUT) as r:
                ans = json.load(r)["answers"]
            ms = int((time.time() - t0) * 1000)
            p = {"stance": ans["stance"]["choice"],
                 "target": ans["target"]["choice"],
                 "fire": ans["fire"]["choice"]}
            print(f"DECIDE[{BOTNAME}] tier=S2 model={S2_LOCAL_MODEL} result={self._fmt_posture(p)} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return p
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            print(f"DECIDE[{BOTNAME}] tier=S2 model={S2_LOCAL_MODEL} error={ex} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return None

    def _decide_cloud_s1(self, state):
        now = time.time()
        if self.last_or_call and now - self.last_or_call < OR_MIN_INTERVAL:
            return self.mode  # throttled: coast on last orders
        self.last_or_call = now
        # effort:none keeps reasoning-capable models answering directly
        body = {"model": OR_MODEL, "max_tokens": 16, "temperature": 0,
                "reasoning": {"effort": "none"},
                "messages": [{"role": "system", "content": _SYSTEM},
                             {"role": "user", "content": state}]}
        return self._call_cloud(body, OR_MODEL, "S1", 5)

    def _call_cloud(self, body, model, tier, timeout, parse=None, want_mode=True):
        parse = parse or self._parse_choice
        t0 = time.time()
        try:
            req = urllib.request.Request(
                OR_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {OR_KEY}"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = json.load(r)["choices"][0]["message"].get("content") or ""
            out = parse(text)
            ms = int((time.time() - t0) * 1000)
            shown = self._fmt_posture(out) if not want_mode and out else out
            print(f"DECIDE[{BOTNAME}] tier={tier} model={model} result={shown} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return out if (out or not want_mode) else "hesitate"
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            print(f"DECIDE[{BOTNAME}] tier={tier} model={model} error={ex} energy={int(self.energy)} ms={ms}",
                  file=sys.stderr, flush=True)
            return None if not want_mode else "hesitate"

    # ---- parsing ---------------------------------------------------------

    @staticmethod
    def _parse_choice(text):
        words = text.lower().replace(".", " ").split()
        for w in words:
            if w in _MODES:
                return w
        return None

    def _parse_final(self, text):
        # S2 may think aloud: take the FINAL word/line that matches a mode
        found = self._parse_choice(text.splitlines()[-1] if text.strip() else "")
        if found:
            return found
        words = text.lower().replace(".", " ").split()
        for w in reversed(words):
            if w in _MODES:
                return w
        return None

    @staticmethod
    def _parse_posture(text):
        p = {}
        for tok in text.lower().replace(",", " ").split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                if k in ("stance", "target", "fire"):
                    p[k] = v
        if p.get("stance") not in _MODES:
            return None
        p.setdefault("target", "nearest")
        p.setdefault("fire", "high")
        return p

    @staticmethod
    def _fmt_posture(p):
        return f"stance={p['stance']},target={p['target']},fire={p['fire']}"


def main():
    OllayaBot().start()


if __name__ == "__main__":
    main()
