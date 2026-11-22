"""First-session P1 rehearsal. SQLite owns the history; simulation caches are disposable."""

from contextlib import closing, contextmanager
import csv
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import secrets
import sqlite3
import time

from augneta.config import Config, canonical
from augneta.experiment import evidence, Trial
from augneta.simulation import validate_action


BANK = Path(__file__).resolve().parents[1]
ARMS = ("code", "arrow")
FORMS = ("A", "B")
PRACTICE_SLOTS = (2, 7, 4, 1, 6, 3, 0, 5)
TRAINING = tuple(Config(seed=seed, evaluation_start_step=0) for seed in (710003, 710029))
SIGNAL_FIELDS = ("channels", "uncertainty_level", "age_steps", "dropped", "sensor_status")
PROTOCOL = "p1-first-session-v1"


class Conflict(ValueError):
    pass


def load_bank():
    stimuli = {f: json.loads((BANK / "preview" / f"form-{f.lower()}.json").read_text()) for f in FORMS}
    with (BANK / "results/item-key.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    keys = {}
    for form, items in stimuli.items():
        selected = [r for r in rows if r["form"] == form]
        if len(items) != 16 or len(selected) != len(items):
            raise ValueError("Incomplete first-test form")
        for i, (r, item) in enumerate(zip(selected, items), 1):
            if int(r["position"]) != i or r["goal"] != item["goal"] or r["answer"] not in ("left", "right"):
                raise ValueError("First-test key and form do not align")
        keys[form] = [r["answer"] for r in selected]
    return stimuli, keys


class Study:
    def __init__(self, database, kind, *, clock=time.time):
        self.database, self.kind, self.clock = Path(database), kind, clock
        self.labels = evidence(kind)
        self.items, self.keys = load_bank()
        self.cache = {}
        settings = {"protocol": PROTOCOL, "kind": kind, "training": [c.to_dict() for c in TRAINING],
                    "estimator": "rw-kalman-v1", "encoder": "polar8-v1", "changes": [],
                    "practice_slots": list(PRACTICE_SLOTS),
                    "bank_sha256": hashlib.sha256(canonical([self.items, self.keys]).encode()).hexdigest()}
        self.settings = settings
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS setup (id INTEGER PRIMARY KEY, settings TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO setup VALUES (1, ?)", (canonical(settings),))
            if db.execute("SELECT settings FROM setup WHERE id=1").fetchone()[0] != canonical(settings):
                raise ValueError("Database belongs to a different protocol, item bank or rehearsal kind.")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, arm TEXT NOT NULL, form TEXT NOT NULL, state TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS ticks (
                session TEXT, block INTEGER, step INTEGER, ax REAL, ay REAL,
                radius_squared REAL, active_ms REAL, PRIMARY KEY(session,block,step))""")

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.database, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            yield db

    def start(self, existing=None):
        with self.connection() as db:
            if existing and db.execute("SELECT 1 FROM sessions WHERE id=?", (existing,)).fetchone():
                return existing
            # A randomized permutation of the four condition/form cells in every allocation block.
            recent = db.execute("SELECT arm,form FROM sessions ORDER BY rowid DESC LIMIT "
                                "(SELECT COUNT(*) % 4 FROM sessions)").fetchall()
            used = {tuple(row) for row in recent}
            arm, form = secrets.choice([cell for cell in product(ARMS, FORMS) if cell not in used])
            token = existing or secrets.token_urlsafe(24)
            state = {"phase": "practice", "revision": 0, "practice": [], "block": 0, "step": 0,
                     "choices": [], "created_at": self.clock()}
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token, arm, form, canonical(state)))
        return token

    def session(self, db, token):
        row = db.execute("SELECT * FROM sessions WHERE id=?", (token,)).fetchone()
        if row is None:
            raise KeyError("Unknown local rehearsal")
        return row, json.loads(row["state"])

    def trial(self, db, row, state):
        token, block, step = row["id"], state["block"], state["step"]
        cached = self.cache.get(token)
        if cached and cached[0] == block and cached[1].step == step:
            return cached[1]
        mode = "sensory_preview" if row["arm"] == "code" else "dashboard"
        trial = Trial(TRAINING[block], mode)
        actions = db.execute("SELECT ax,ay FROM ticks WHERE session=? AND block=? ORDER BY step", (token, block))
        for action in actions:
            trial.advance(tuple(action))
        if trial.step != step:
            raise ValueError("The recorded training inputs do not match the saved tick.")
        self.cache[token] = (block, trial)
        return trial

    def view(self, db, row, s):
        phase = s["phase"]
        public = {"phase": phase, "revision": s["revision"], "participant_kind": self.kind}
        if phase == "practice":
            index = len(s["practice"])
            channels = [0.] * 8
            channels[PRACTICE_SLOTS[index]] = .75
            public.update(index=index, total=8, channels=channels)
        elif phase == "practice_feedback":
            index = len(s["practice"]) - 1
            public.update(index=index, total=8, expected_slot=PRACTICE_SLOTS[index],
                          chosen_slot=s["practice"][index])
        elif phase in ("training_ready", "training"):
            cfg = TRAINING[s["block"]]
            public.update(arm=row["arm"], block=s["block"] + 1, blocks=len(TRAINING),
                          step=s["step"], steps=cfg.steps, dt_ms=round(cfg.dt_s * 1000))
            if phase == "training":
                view = self.trial(db, row, s).view()
                packet = view["feedback"]
                public.update(position=view["visible"]["position"], emitted_step=packet["emitted_step"],
                              signal={field: packet[field] for field in SIGNAL_FIELDS})
        elif phase == "transfer":
            index = len(s["choices"])
            public.update(index=index, total=len(self.items[row["form"]]), item=self.items[row["form"]][index])
        elif phase == "complete":
            public["result"] = self.result(db, row, s)
        return public

    def current(self, token):
        with self.connection() as db:
            row, state = self.session(db, token)
            return self.view(db, row, state)

    def event(self, token, revision, action, value):
        with self.connection() as db:
            row, s = self.session(db, token)
            if type(revision) is not int or revision != s["revision"]:
                raise Conflict("The rehearsal has advanced. Reload the current step.")
            phase = s["phase"]
            if (phase, action) == ("practice", "identify"):
                if type(value) is not int or value not in range(8):
                    raise ValueError("Choose one of eight slots.")
                s["practice"].append(value)
                s["phase"] = "practice_feedback"
            elif (phase, action) == ("practice_feedback", "continue"):
                s["phase"] = "training_ready" if len(s["practice"]) == 8 else "practice"
            elif (phase, action) == ("training_ready", "begin"):
                s["phase"] = "training"
            elif (phase, action) == ("training", "steer"):
                self.steer(db, row, s, value)
            elif (phase, action) == ("transfer_ready", "begin"):
                s.update(phase="transfer", item_opened=self.clock())
            elif (phase, action) == ("transfer", "choose"):
                if value not in ("left", "right"):
                    raise ValueError("Choose a gate.")
                now = self.clock()
                s["choices"].append({"side": value, "elapsed_ms": round(max(0, now - s["item_opened"]) * 1000)})
                s["item_opened"] = now
                if len(s["choices"]) == len(self.items[row["form"]]):
                    s.update(phase="reflection", transfer_finished_at=now)
            elif (phase, action) == ("reflection", "finish"):
                if not isinstance(value, str) or len(value) > 600:
                    raise ValueError("Use up to 600 characters.")
                s.update(phase="complete", note=value.strip(), completed_at=self.clock())
            else:
                raise Conflict("This action is unavailable in the current phase.")
            s["revision"] += 1
            db.execute("UPDATE sessions SET state=? WHERE id=?", (canonical(s), token))
            return self.view(db, row, s)

    def steer(self, db, row, s, value):
        if not isinstance(value, dict) or set(value) != {"action", "active_ms"}:
            raise ValueError("A direct action and active interval are required.")
        action = validate_action(value["action"])
        ms = value["active_ms"]
        if type(ms) not in (float, int) or not math.isfinite(ms) or ms < 0:
            raise ValueError("Invalid active interval.")
        trial = self.trial(db, row, s)
        record, _ = trial.advance(action)
        radius2 = sum(x*x for x in record["visible_after"]["position"])
        db.execute("INSERT INTO ticks VALUES(?,?,?,?,?,?,?)", (row["id"], s["block"], s["step"], *action, radius2, ms))
        s["step"] = trial.step
        if trial.complete:
            self.cache.pop(row["id"], None)
            s["block"] += 1
            s["step"] = 0
            s["phase"] = "transfer_ready" if s["block"] == len(TRAINING) else "training_ready"

    def result(self, db, row, s):
        form = row["form"]
        if len(s["choices"]) != len(self.keys[form]):
            raise ValueError("The first transfer block is incomplete.")
        review = [{"item": i + 1, "goal": item["goal"], **choice, "answer": answer,
                   "correct": choice["side"] == answer}
                  for i, (item, choice, answer) in enumerate(zip(self.items[form], s["choices"], self.keys[form]))]
        metrics = db.execute("""SELECT block, COUNT(*) AS n, AVG(radius_squared) AS mse, SUM(active_ms) AS ms
                                FROM ticks WHERE session=? GROUP BY block ORDER BY block""", (row["id"],))
        return {
            **self.labels, "protocol": PROTOCOL, "arm": row["arm"], "form": form,
            "estimator": self.settings["estimator"], "encoder": self.settings["encoder"],
            "bank_sha256": self.settings["bank_sha256"],
            "practice_correct": sum(a == b for a, b in zip(s["practice"], PRACTICE_SLOTS)),
            "practice_total": len(PRACTICE_SLOTS), "correct": sum(r["correct"] for r in review), "total": len(review),
            "by_goal": {g: {"correct": sum(r["correct"] for r in review if r["goal"] == g),
                            "total": sum(r["goal"] == g for r in review)} for g in ("reach", "release")},
            "training": [{"block": m["block"] + 1, "seed": TRAINING[m["block"]].seed, "steps": m["n"],
                          "simulation_s": m["n"] * TRAINING[m["block"]].dt_s, "foreground_s": m["ms"] / 1000,
                          "center_rmse": math.sqrt(m["mse"])} for m in metrics],
            "items": review, "reflection": s.get("note"), "first_block_finished_at": s["transfer_finished_at"],
        }

    def summary(self):
        arms = {arm: {"started": 0, "first_blocks_completed": 0, "sessions_finished": 0,
                      "mean_first_block_accuracy": None} for arm in ARMS}
        with self.connection() as db:
            for row in db.execute("SELECT * FROM sessions ORDER BY rowid"):
                s = json.loads(row["state"])
                group = arms[row["arm"]]
                group["started"] += 1
                if s["phase"] in ("reflection", "complete"):
                    results = self.result(db, row, s)
                    group["first_blocks_completed"] += 1
                    group["sessions_finished"] += int(s["phase"] == "complete")
                    total = group["first_blocks_completed"]
                    old = group["mean_first_block_accuracy"] or 0.
                    group["mean_first_block_accuracy"] = old + (results["correct"] / results["total"] - old) / total
        code_mean = arms["code"]["mean_first_block_accuracy"]
        arrow_mean = arms["arrow"]["mean_first_block_accuracy"]
        difference = None if code_mean is None or arrow_mean is None else 100 * (code_mean - arrow_mean)
        return {**self.labels, "protocol": PROTOCOL, "arms": arms,
                "first_block_code_minus_arrow_percentage_points": difference}
