"""Offline virtual receivers, paired evaluation and deterministic artifacts.

Private receiver/key state stays here; selection/fitting use only the value
objects defined in selective_calibration. No UI or physical driver is invoked.
"""

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import random
import statistics

from .config import canonical
from .recording import software_identity, write_json
from .selective_calibration import (SPEC, Observation, Query, Response, catalogue,
                                    choose_query, correct, fit_profile)
from .tactile import TactileProfile, number

DESIGN_SHA256 = "8946de7a0291f3c4781257976c6ee900433c0fb4dc19907851bfeeefb8ca55f1"
METHODS = ("no_recalibration", "uniform", "selective")


def labels():
    return {"participant_kind": "synthetic", "human_evidence": False, "hardware_verified": False,
            "profile_status": "unvalidated_hardware_candidate", "evidence_scope": "assumed_virtual_response_models_only"}


def design():
    data = json.loads(files("augneta").joinpath("data/selective_calibration_v1.json").read_text())
    if hashlib.sha256(canonical(data).encode()).hexdigest() != DESIGN_SHA256:
        raise ValueError("frozen design changed; version and review before evaluation")
    return data


def _seed(seed):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("virtual individual seed must be uint32")


def _rng(key):
    return random.Random(int.from_bytes(hashlib.sha256(canonical(key).encode()).digest(), "big"))


def _key(seed, scenario, phase, *parts):
    return ["selective-calibration-v1", seed, scenario, phase, *parts]


def codes():
    return [SPEC.code(d, lev) for d in range(6) for lev in (1, 2)] + [SPEC.code(None, 0)]


def code_name(direction, level):
    return "zero" if level == 0 else f"D{direction}/L{level}"


@dataclass(frozen=True, slots=True)
class VirtualReceiver:
    multipliers: tuple
    noise_std: float = 0.025
    lapse_probability: float = 0.04

    def __post_init__(self):
        if type(self.multipliers) is not tuple or len(self.multipliers) != 6 or not all(number(v, 0, 3) for v in self.multipliers):
            raise ValueError("six bounded latent multipliers required")
        if not number(self.noise_std, 0, 1) or not number(self.lapse_probability, 0, 1):
            raise ValueError("invalid receiver noise/lapse")

    def respond(self, command, rng):
        # No intended code, expected answer, method, or evaluation score is accepted.
        if not isinstance(command, dict) or set(command) != {"left", "right", "pulse_ms", "gap_ms", "profile_sha256", "output_mode", "hardware_verified"}:
            raise ValueError("invalid rendered command fields")
        for side in ("left", "right"):
            if not isinstance(command[side], list) or len(command[side]) != 3 or not all(number(v, 0, 1) for v in command[side]):
                raise ValueError("invalid rendered command slots")
        if (type(command['pulse_ms']) is not int or type(command['gap_ms']) is not int
                or command['pulse_ms'] != 150 or command['gap_ms'] != 150
                or command['hardware_verified'] is not False or command['output_mode'] != 'command_preview'):
            raise ValueError("v1 receiver requires fixed software preview timing")
        lapse = rng.random()
        sensed = [max(0.0, u * gain + rng.gauss(0, self.noise_std))
                  for u, gain in zip(command["left"] + command["right"], self.multipliers)]
        if lapse < self.lapse_probability:
            return Response("unknown", None, None)
        order = sorted(range(6), key=lambda i: (-sensed[i], i))
        top, second = order[:2]
        if sensed[top] < 0.12:
            return Response("zero", None, 0)
        if sensed[top] - sensed[second] < 0.04:
            return Response("unknown", None, None)
        return Response("identified", top, 1 if sensed[top] < 0.375 else 2)


def receiver(seed, scenario):
    _seed(seed)
    settings = design()["scenarios"]
    if scenario not in settings:
        raise ValueError("unknown virtual scenario")
    rng = _rng(_key(seed, scenario, "latent"))
    rule = settings[scenario]
    gains = [rng.uniform(*rule["ordinary_multiplier_range"]) for _ in range(6)]
    if rule["disturbed_slots"] == "one_seeded_slot":
        gains[rng.randrange(6)] = rng.uniform(*rule["disturbed_multiplier_range"])
    # 'all' uses the same range as ordinary for v1; no extra draws.
    return VirtualReceiver(tuple(gains))


def calibrate(model, seed, scenario, budget, method):
    if type(budget) is not int or budget not in (78, 156):
        raise ValueError("v1 budget must be 78 or 156")
    if method not in ("uniform", "selective"):
        raise ValueError("unknown calibration method")
    candidates = catalogue()
    history, trace, occurrences = (), [], Counter()
    while len(history) < budget:
        query = choose_query(candidates, history, budget - len(history), method)
        command = candidates.profiles[query.candidate].render(query.code)
        occurrence = occurrences[query]
        occurrences[query] += 1
        key = _key(seed, scenario, "calibration", query.direction, query.level, query.candidate, occurrence)
        answer = model.respond(command, _rng(key))
        history += (Observation(query, tuple(command['left'] + command['right']), answer),)
        trace.append({"index": len(trace), "query": asdict(query), "expected": query.code,
                      "command": command, "response": answer.to_dict(), "draw_key": key,
                      "budget_remaining": budget - len(history), **labels()})
    frozen = fit_profile(candidates, history)
    allocation = Counter(code_name(o.query.direction, o.query.level) + f"/G{o.query.candidate}" for o in history)
    return {"method": method, "response_count": len(trace), "catch_count": sum(o.query.level == 0 for o in history),
            "allocation": dict(sorted(allocation.items())), "calibration": trace,
            "frozen_profile": frozen.to_dict(), "profile_sha256": frozen.identity, **labels()}


def evaluate(model, seed, scenario, profile):
    # Frozen profile only: this function never has a selector/fitter callback.
    records = []
    names = [code_name(c['direction'], c['level']) for c in codes()]
    confusion = {name: dict.fromkeys(names + ['unknown'], 0) for name in names}
    for code in codes():
        command = profile.render(code)
        for repeat in range(32):
            key = _key(seed, scenario, "evaluation", code['direction'], code['level'], repeat)
            answer = model.respond(command, _rng(key))
            expected = code_name(code['direction'], code['level'])
            received = 'unknown' if answer.kind == 'unknown' else code_name(answer.direction, answer.level)
            confusion[expected][received] += 1
            records.append({"expected": code, "command": command, "response": answer.to_dict(),
                            "draw_key": key, **labels()})
    per_code = {name: 1 - row[name] / sum(row.values()) for name, row in confusion.items()}
    return {"records": records, "balanced_heldout_joint_error": math.fsum(per_code.values()) / len(per_code),
            "per_code_error": per_code, "confusion": confusion, "evaluation_response_count": len(records),
            "response_counts": dict(Counter(r['response']['kind'] for r in records)), **labels()}


def simulate_case(seed, scenario, methods=METHODS):
    _seed(seed)
    if not isinstance(methods, (tuple, list)) or len(methods) != 3 or set(methods) != set(METHODS):
        raise ValueError("each of the three methods is required exactly once")
    model = receiver(seed, scenario)
    runs = {}
    for method in methods:
        if method == 'no_recalibration':
            p = TactileProfile()
            runs[method] = {"method": method, "response_count": 0, "catch_count": 0, "allocation": {},
                            "calibration": [], "frozen_profile": p.to_dict(), "profile_sha256": p.identity, **labels()}
        else:
            for budget in (78, 156):
                runs[f'{method}-{budget}'] = calibrate(model, seed, scenario, budget, method)
    # All fitting ends here, before any evaluation outcome exists.
    for name in sorted(runs):
        run = runs[name]
        run['evaluation'] = evaluate(model, seed, scenario, TactileProfile.from_dict(run['frozen_profile']))
    return json.loads(canonical({"seed": seed, "scenario": scenario, "latent_model": asdict(model),
                                 "runs": {k: runs[k] for k in sorted(runs)}, **labels()}))


def summarize(cases):
    cells = []
    for split in ('development', 'check'):
        for scenario in design()['scenarios']:
            for budget in (78, 156):
                rows = []
                for case in cases:
                    if case['split'] != split or case['scenario'] != scenario:
                        continue
                    selected = {m: case['runs'][m if m == 'no_recalibration' else f'{m}-{budget}'] for m in METHODS}
                    errors = {m: run['evaluation']['balanced_heldout_joint_error'] for m, run in selected.items()}
                    rows.append({'seed': case['seed'], 'errors': errors,
                                 'response_counts': {m:r['response_count'] for m,r in selected.items()},
                                 'profile_sha256': {m:r['profile_sha256'] for m,r in selected.items()},
                                 'selective_minus_uniform': errors['selective'] - errors['uniform'],
                                 'uniform_minus_reference': errors['uniform'] - errors['no_recalibration'],
                                 'selective_minus_reference': errors['selective'] - errors['no_recalibration']})
                differences = [r['selective_minus_uniform'] for r in rows]
                cells.append({'split': split, 'scenario': scenario, 'budget': budget, 'seeds': rows,
                              'mean_errors': {m:statistics.mean(r['errors'][m] for r in rows) for m in METHODS},
                              'mean_paired_difference': statistics.mean(differences),
                              'sample_sd_paired_difference': statistics.stdev(differences) if len(rows)>1 else None,
                              'range_paired_difference': [min(differences),max(differences)],
                              'win_tie_loss': [sum(d < -1e-12 for d in differences), sum(abs(d)<=1e-12 for d in differences), sum(d>1e-12 for d in differences)]})
    return {'cells': cells, 'unit': 'virtual individual; repeated responses, budgets and scenarios are not independent individuals', **labels()}


def split_summary(cases, split):
    return {'cases': [
        {'seed':c['seed'], 'scenario':c['scenario'],
         'errors':{k:r['evaluation']['balanced_heldout_joint_error'] for k,r in c['runs'].items()}}
        for c in cases if c['split']==split], **labels()}


def reconstruct_case(saved):
    actual = {'split': saved['split'], **simulate_case(saved['seed'], saved['scenario'])}
    if saved != actual:
        raise ValueError('case reconstruction mismatch')
    return actual


def run_simulation(directory):
    directory = Path(directory)
    frozen_design = design()
    source = software_identity()
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': 1, 'design': frozen_design, 'design_sha256': DESIGN_SHA256,
                'source': source, 'status': 'running', 'case_files': [], **labels()}
    write_json(directory/'manifest.json', manifest)  # before any receiver evaluation
    cases = []
    for split in ('development','check'):
        for scenario in frozen_design['scenarios']:
            for seed in frozen_design[f'{split}_seeds']:
                case = {'split':split, **simulate_case(seed, scenario)}
                filename = f'{split}-{scenario}-{seed}.json'
                write_json(directory/filename, case)
                cases.append(case)
                manifest['case_files'].append(filename)
        # Save development before exposing check results.
        write_json(directory/f'{split}-summary.json', split_summary(cases, split))
    summary = summarize(cases)
    write_json(directory/'summary.json', summary)
    manifest['status'] = 'complete'
    write_json(directory/'manifest.json', manifest)
    return {'directory': str(directory), 'cases':len(cases), 'cells':len(summary['cells']),
            'design_sha256': DESIGN_SHA256, **labels()}


def reconstruct(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if (manifest.get('schema_version') != 1 or manifest.get('status') != 'complete'
            or manifest.get('design') != design() or manifest.get('design_sha256') != DESIGN_SHA256
            or any(manifest.get(k) != v for k,v in labels().items())):
        raise ValueError("invalid/incomplete design or evidence manifest")
    current = software_identity()
    if any(manifest['source'].get(k) != current[k] for k in ('source_sha256','python','package_version')):
        raise ValueError('reconstruction requires matching implementation and Python')
    expected_files = [f'{split}-{scenario}-{seed}.json' for split in ('development','check')
                      for scenario in design()['scenarios'] for seed in design()[f'{split}_seeds']]
    if manifest['case_files'] != expected_files:
        raise ValueError('case list mismatch')
    cases=[]
    for filename in expected_files:
        saved = json.loads((directory/filename).read_text())
        split, scenario, seed = filename.removesuffix('.json').split('-')
        if (saved.get('split'), saved.get('scenario'), saved.get('seed')) != (split,scenario,int(seed)):
            raise ValueError('case identity mismatch')
        cases.append(reconstruct_case(saved))
    for split in ('development','check'):
        if json.loads((directory/f'{split}-summary.json').read_text()) != split_summary(cases, split):
            raise ValueError('split summary reconstruction mismatch')
    if json.loads((directory/'summary.json').read_text()) != summarize(cases):
        raise ValueError('summary reconstruction mismatch')
    return {'reconstruction_verified':True, 'cases':len(cases), **labels()}
