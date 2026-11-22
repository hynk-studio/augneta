from concurrent.futures import ThreadPoolExecutor
import math

import pytest

from app import create_app
from study import ARMS, FORMS, PRACTICE_SLOTS, SIGNAL_FIELDS, TRAINING, Conflict, Study
from augneta.simulation import World


def advance(study, token, state, action, value=None):
    return study.event(token, state["revision"], action, value)


def prepare(study, token):
    state = study.current(token)
    for slot in PRACTICE_SLOTS:
        assert state["channels"].index(max(state["channels"])) == slot
        state = advance(study, token, state, "identify", slot)
        assert state["expected_slot"] == slot
        state = advance(study, token, state, "continue")
    assert state["phase"] == "training_ready"
    return state


def test_atomic_randomization_and_stale_or_invalid_events(tmp_path):
    study = Study(tmp_path/"pilot.db", "synthetic")
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(study.start, [None]*8))
    assert len(set(tokens)) == 8
    with study.connection() as db:
        cells = [(r["arm"],r["form"]) for r in db.execute("SELECT * FROM sessions ORDER BY rowid")]
    for block in (cells[:4], cells[4:]):
        assert set(block) == {(arm, form) for arm in ARMS for form in FORMS}
    token = tokens[0]
    assert study.start(token) == token
    with pytest.raises(Conflict):
        study.event(token, 0, "choose", "right")
    assert study.current(token)["revision"] == 0
    first = study.event(token, 0, "identify", 2)
    with pytest.raises(Conflict):
        study.event(token, 0, "identify", 2)
    assert study.current(token) == first
    with pytest.raises(ValueError):
        Study(tmp_path/"pilot.db", "developer")


def test_end_to_end_equated_exposure_first_responses_and_restart(tmp_path):
    database = tmp_path/"pilot.db"
    clock = [10000.]
    study = Study(database, "synthetic", clock=lambda: clock[0])
    tokens = [study.start() for _ in range(4)]
    states = [prepare(study,t) for t in tokens]
    signatures, gate_inputs = {}, {}
    with study.connection() as db:
        assignments = {r["id"]:(r["arm"],r["form"]) for r in db.execute("SELECT * FROM sessions")}
    for token, state in zip(tokens,states):
        arm, form = assignments[token]
        signals, rms = [], []
        for block, cfg in enumerate(TRAINING):
            world = World(cfg)
            errors = []
            state = advance(study, token, state, "begin")
            for tick in range(cfg.steps):
                if block == 0 and tick == 13:
                    study = Study(database, "synthetic", clock=lambda: clock[0])
                    assert study.current(token) == state
                    with pytest.raises(ValueError):
                        advance(study, token, state, "steer", {"action":[3,0],"active_ms":50})
                    assert study.current(token) == state
                assert state["phase"] == "training" and state["step"] == tick
                assert set(state["signal"]) == set(SIGNAL_FIELDS)
                assert state["position"] == list(world.position)
                signals.append((state["emitted_step"], state["signal"]))
                # Distinct actions on purpose: sensor/feedback does not depend on steering.
                action = (1 if arm == "arrow" else -1, -1 if tick % 10 < 5 else 0)
                world.advance(action)
                errors.append(sum(p*p for p in world.position))
                state = advance(study, token, state, "steer", {"action":action,"active_ms":50.})
            rms.append(math.sqrt(sum(errors)/len(errors)))
        signatures[token] = signals
        assert state["phase"] == "transfer_ready"
        state = advance(study, token, state, "begin")
        sequence = []
        for index in range(16):
            assert state["phase"] == "transfer" and state["index"] == index
            item = state["item"]
            assert set(item) == {"geometry","goal","signal"} and set(item["signal"]) == set(SIGNAL_FIELDS)
            assert not {"correct","answer","result","score"} & state.keys()
            sequence.append(item)
            if index == 5:
                study = Study(database, "synthetic", clock=lambda: clock[0])
                assert study.current(token) == state
            clock[0] += .75
            side = "left" if arm == "code" else study.keys[form][index]
            prior = state
            state = advance(study, token, state, "choose", side)
            with pytest.raises(Conflict):
                advance(study, token, prior, "choose", "right")
        gate_inputs[(arm,form)] = sequence
        assert state["phase"] == "reflection" and "result" not in state
        assert study.summary()["arms"][arm]["first_blocks_completed"] >= 1
        state = advance(study, token, state, "finish","")
        out = state["result"]
        assert out["correct"] == (8 if arm == "code" else 16)
        assert [b["center_rmse"] for b in out["training"]] == pytest.approx(rms)
        assert [b["simulation_s"] for b in out["training"]] == [30.,30.]
        assert [b["foreground_s"] for b in out["training"]] == [30.,30.]
        assert all(r["elapsed_ms"] == 750 for r in out["items"])
        assert out["human_evidence"] is False and out["hardware_verified"] is False
    assert all(seq == signatures[tokens[0]] for seq in signatures.values())
    assert all(gate_inputs[("code",f)] == gate_inputs[("arrow",f)] for f in FORMS)
    assert study.summary()["arms"]["code"]["mean_first_block_accuracy"] == .5
    assert study.summary()["arms"]["arrow"]["mean_first_block_accuracy"] == 1.
    assert study.summary()["first_block_code_minus_arrow_percentage_points"] == -50.


def test_only_current_item_and_local_json_controls(tmp_path):
    app = create_app(tmp_path/"pilot.db", "developer")
    c = app.test_client()
    assert c.get("/api/session").json["phase"] == "welcome"
    assert c.post("/api/start", json={"arm":"arrow","form":"A"}).status_code == 400
    assert c.post("/api/start", json={}, headers={"Origin":"https://example.com"}).status_code == 403
    assert c.post("/api/start", data="{}").status_code == 415
    assert c.post("/api/start", json={}).json == c.post("/api/start",json={}).json
    assert c.post("/api/new",json={}).status_code == 409
    for url in ("/results/item-key.csv","/item-key.csv","/preview/form-a.json","/api/score","/ui/item-key.csv"):
        assert c.get(url).status_code == 404
    assert c.get("/display.js").status_code == 200
    assert c.get("/api/session").json["participant_kind"] == "developer"
