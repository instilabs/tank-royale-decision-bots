import json, math, os, sys, time, urllib.request
from robocode_tank_royale.bot_api.bot import Bot
from robocode_tank_royale.bot_api.events import ScannedBotEvent, BotDeathEvent, DeathEvent

BOTNAME = "OpenAICodex"

# OpenAI-compatible Chat Completions endpoint (defaults to local codex-bridge).
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8787/v1").rstrip("/")
OPENAI_CHAT_URL = os.environ.get("OPENAI_CHAT_URL", f"{OPENAI_BASE_URL}/chat/completions")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("OPENAI_MODEL", "codex-local")
TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT_S", "30"))
MIN_INTERVAL_S = float(os.environ.get("OPENAI_MIN_INTERVAL_S", "0"))

_MODES = ("aggressive", "evasive", "probe")
_SYSTEM = (
    "You are the combat brain of a Robocode tank. "
    "Reply with exactly one word: aggressive, evasive, or probe. "
    "Aggressive pursuit wins battles - prefer it."
)


class OpenAICodexBot(Bot):
    """Robocode Tank Royale bot driven by an OpenAI-compatible /chat/completions
    endpoint (such as codex-bridge)."""

    def __init__(self):
        super().__init__()
        self.mode = "hesitate"
        self.enemy = "none"
        self.ex = self.ey = None
        self.last_seen = -999
        self.last_call = 0.0

    def run(self):
        self.adjust_radar_for_gun_turn = True
        while self.running:
            if self.turn_number % 40 == 0:
                self.mode = self.decide()
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

    def decide(self):
        now = time.time()
        if MIN_INTERVAL_S > 0 and self.last_call and now - self.last_call < MIN_INTERVAL_S:
            return self.mode
        self.last_call = now

        state = (
            f"Robocode tank battle. My energy={int(self.energy)}. "
            f"Enemy: {self.enemy}"
        )
        body = {
            "model": MODEL,
            "max_tokens": 16,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": state},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

        t0 = time.time()
        try:
            req = urllib.request.Request(
                OPENAI_CHAT_URL,
                data=json.dumps(body).encode(),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                text = json.load(r)["choices"][0]["message"].get("content") or ""
            out = self._parse_choice(text)
            ms = int((time.time() - t0) * 1000)
            print(
                f"DECIDE[{BOTNAME}] model={MODEL} result={out} energy={int(self.energy)} ms={ms}",
                file=sys.stderr,
                flush=True,
            )
            return out or "hesitate"
        except Exception as ex:
            ms = int((time.time() - t0) * 1000)
            print(
                f"DECIDE[{BOTNAME}] model={MODEL} error={ex} energy={int(self.energy)} ms={ms}",
                file=sys.stderr,
                flush=True,
            )
            return "hesitate"

    @staticmethod
    def _parse_choice(text):
        words = text.lower().replace(".", " ").replace(",", " ").split()
        for w in words:
            if w in _MODES:
                return w
        return None


def main():
    OpenAICodexBot().start()


if __name__ == "__main__":
    main()
