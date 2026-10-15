from dataclasses import FrozenInstanceError, fields, replace
import inspect
import json
import random

import pytest

from augneta import calibration_simulation as sim
from augneta import selective_calibration as allocation
from augneta.cli import main
from augneta.config import canonical
from augneta.recording import write_json
from augneta.tactile import TactileProfile


@pytest.fixture(scope='module')
def case():
    # Engineering fixture outside the declared development/check seeds.
    return sim.simulate_case(999, 'localized')


def test_frozen_design_and_unchanged_profile():
    d = sim.design()
    assert not set(d['development_seeds']) & set(d['check_seeds'])
    assert d['budgets'] == [78,156]
    assert d['base_profile'] == TactileProfile().to_dict()
    assert [p.gains[0] for p in allocation.catalogue().profiles] == d['gain_candidates']
    assert set(d['scenarios']) == {'stable','localized','broad','attenuated'}
    assert d['receiver']['noise_std'] == sim.VirtualReceiver((1.0,)*6).noise_std


@pytest.mark.parametrize('budget', [78,156])
@pytest.mark.parametrize('method', ['uniform','selective'])
def test_budget_catches_minimum_exploration_and_shared_fitter(case, budget, method):
    r = case['runs'][f'{method}-{budget}']
    assert r['response_count'] == len(r['calibration']) == budget
    assert r['catch_count'] == budget//13
    assert sum(r['allocation'].values()) == budget
    warmup = [x['query'] for x in r['calibration'][:39] if x['query']['level']]
    assert {(q['direction'],q['candidate'],q['level']) for q in warmup} == {
        (d,g,lev) for d in range(6) for g in range(3) for lev in (1,2)}
    assert len(warmup) == 36
    history = tuple(allocation.Observation(allocation.Query(**x['query']),
                    tuple(x['command']['left']+x['command']['right']), allocation.Response(**x['response']))
                    for x in r['calibration'])
    assert allocation.fit_profile(allocation.catalogue(),history).identity == r['profile_sha256']
    for i,record in enumerate(r['calibration']):
        assert (record['query']['level']==0) == ((i+1)%13==0)
        assert record['budget_remaining'] == budget-i-1
    if method=='uniform':
        assert len(set(v for k,v in r['allocation'].items() if not k.startswith('zero'))) == 1
    assert case['runs']['no_recalibration']['response_count'] == 0
    assert case['runs']['no_recalibration']['calibration'] == []


def test_determinism_method_order_and_budget_prefix(case):
    assert sim.simulate_case(999,'localized',tuple(reversed(sim.METHODS))) == case
    for method in ('uniform','selective'):
        short = case['runs'][f'{method}-78']['calibration']
        long = case['runs'][f'{method}-156']['calibration'][:78]
        # Remaining budget differs; everything observed/issued is the same prefix.
        assert [{k:v for k,v in x.items() if k!='budget_remaining'} for x in short] == [
               {k:v for k,v in x.items() if k!='budget_remaining'} for x in long]


def test_evaluation_covers_every_code_and_matched_draws(case):
    reference = case['runs']['no_recalibration']['evaluation']
    keys = [r['draw_key'] for r in reference['records']]
    assert len(keys) == len(set(map(canonical,keys))) == 13*32
    for run in case['runs'].values():
        e = run['evaluation']
        assert [r['draw_key'] for r in e['records']] == keys
        assert len(e['confusion']) == 13
        assert all(sum(row.values())==32 for row in e['confusion'].values())
        hits = sum(row[name] for name,row in e['confusion'].items())
        assert e['balanced_heldout_joint_error'] == pytest.approx(1-hits/(13*32))
        assert {r['command']['profile_sha256'] for r in e['records']} == {run['profile_sha256']}
        assert not set(map(canonical,keys)) & {canonical(r['draw_key']) for r in run['calibration']}
        assert run['participant_kind']=='synthetic' and run['human_evidence'] is False
        assert run['hardware_verified'] is False and run['profile_status']=='unvalidated_hardware_candidate'


def test_actual_policy_boundary_and_no_hidden_scenario_input(monkeypatch):
    seen=[]
    original=allocation.choose_query
    def spy(catalogue, history, remaining_budget, method):
        assert type(catalogue) is allocation.Catalogue
        assert type(history) is tuple
        assert {f.name for f in fields(allocation.Observation)} == {'query','command','response'}
        assert {f.name for f in fields(allocation.Catalogue)} == {'profiles'}
        assert all(type(o) is allocation.Observation for o in history)
        seen.append(len(history))
        return original(catalogue,history,remaining_budget,method)
    monkeypatch.setattr(sim,'choose_query',spy)
    # Different private scenarios/seeds but identical permitted answer history.
    model=sim.VirtualReceiver((1.0,)*6,noise_std=0,lapse_probability=1)
    a=sim.calibrate(model,999,'stable',78,'selective')
    b=sim.calibrate(model,1000,'attenuated',78,'selective')
    assert [r['query'] for r in a['calibration']] == [r['query'] for r in b['calibration']]
    assert a['frozen_profile'] == b['frozen_profile']
    assert seen==list(range(78))*2
    # An evaluation object or model capability cannot be smuggled into the history.
    with pytest.raises(ValueError,match='history'):
        original(allocation.catalogue(),({'scenario':'stable','evaluation_error':0},),1,'selective')
    assert list(inspect.signature(allocation.fit_profile).parameters)==['candidates','history']


def test_all_profiles_frozen_before_evaluation(monkeypatch):
    fitted=[]
    original_fit=sim.fit_profile
    original_evaluate=sim.evaluate
    def fit(c,h):
        p=original_fit(c,h)
        fitted.append(p)
        return p
    def evaluate(*args):
        assert len(fitted)==4
        profile=args[-1]
        before=profile.identity
        with pytest.raises(FrozenInstanceError):
            profile.gains=(0.5,)*6
        result=original_evaluate(*args)
        assert profile.identity==before
        return result
    monkeypatch.setattr(sim,'fit_profile',fit)
    monkeypatch.setattr(sim,'evaluate',evaluate)
    sim.simulate_case(998,'stable')


def test_receiver_uses_rendered_command_not_intended_label():
    model=sim.VirtualReceiver((2.0,1,1,1,1,1),noise_std=0,lapse_probability=0)
    p=TactileProfile()
    code=p.spec.code(0,1)
    assert model.respond(p.render(code),random.Random(1))==allocation.Response('identified',0,2)
    reduced=replace(p,gains=(0.5,)*6)
    assert model.respond(reduced.render(code),random.Random(1))==allocation.Response('identified',0,1)
    assert p.matched_preview(code)['visual']==reduced.matched_preview(code)['visual']
    with pytest.raises(ValueError,match='fields'):
        model.respond({**p.render(code),'expected':code},random.Random(1))


def test_zero_unknown_and_uncorrectable_negative_cases():
    p=TactileProfile()
    perfect=sim.VirtualReceiver((1.0,)*6,noise_std=0,lapse_probability=0)
    unknown=replace(perfect,lapse_probability=1)
    for code in sim.codes():
        assert allocation.correct(code,perfect.respond(p.render(code),random.Random(2)))
        assert not allocation.correct(code,unknown.respond(p.render(code),random.Random(2)))
    attenuated=replace(perfect,multipliers=(0.0,)*6)
    errors=[]
    for candidate in allocation.catalogue().profiles:
        result=sim.evaluate(attenuated,999,'attenuated',candidate)
        errors.append(result['balanced_heldout_joint_error'])
        assert result['response_counts']=={'zero':416}
    assert errors==pytest.approx([12/13]*3)
    ambiguous=replace(perfect,multipliers=(1.,)*6)
    command=p.render(p.spec.code(0,1))
    command['left'][1]=0.25
    assert ambiguous.respond(command,random.Random(2)).kind=='unknown'


@pytest.mark.parametrize('args', [('zero',0,0),('identified',None,0),('unknown',0,None),('bad',None,None),('identified',True,1)])
def test_malformed_responses(args):
    with pytest.raises(ValueError): allocation.Response(*args)


@pytest.mark.parametrize('values', [(True,'stable'),(-1,'stable'),(1,'missing')])
def test_invalid_model_selection(values):
    with pytest.raises(ValueError): sim.receiver(*values)


@pytest.mark.parametrize('budget', [True,0,39,79,157])
def test_invalid_budgets(budget):
    with pytest.raises(ValueError): sim.calibrate(sim.receiver(999,'stable'),999,'stable',budget,'uniform')


def test_invalid_history_and_incomplete_fit():
    c=allocation.catalogue()
    with pytest.raises(ValueError,match='exploration'): allocation.fit_profile(c,())
    with pytest.raises(ValueError,match='budget'): allocation.choose_query(c,(),0,'uniform')
    fake=allocation.Observation(allocation.Query(0,1,0),(0.,)*6,allocation.Response('zero',None,0))
    with pytest.raises(ValueError,match='command'): allocation.fit_profile(c,(fake,))
    with pytest.raises(ValueError): allocation.Catalogue(tuple(reversed(c.profiles)))


def test_cli_rejects_overwrite_and_bad_record(tmp_path,capsys):
    path=tmp_path/'existing';path.mkdir()
    (path/'keep').write_text('retained')
    assert main(['calibration-sim','--out',str(path)])==2
    assert (path/'keep').read_text()=='retained'
    assert main(['calibration-replay',str(path)])==2
    assert 'augneta:' in capsys.readouterr().err


def test_persisted_reconstruction_and_tampering(tmp_path,case):
    path=tmp_path/'case.json'
    saved={'split':'development',**case}
    write_json(path,saved)
    assert sim.reconstruct_case(json.loads(path.read_text())) == saved
    changed=json.loads(path.read_text())
    changed['runs']['selective-78']['calibration'][0]['response']={'kind':'unknown','direction':None,'level':None}
    # Ensure the change differs even when the first recorded response was unknown.
    if changed==saved:
        changed['runs']['selective-78']['calibration'][0]['response']={'kind':'zero','direction':None,'level':0}
    with pytest.raises(ValueError,match='reconstruction'):
        sim.reconstruct_case(changed)
    changed=json.loads(path.read_text())
    changed['runs']['selective-156']['evaluation']['balanced_heldout_joint_error']=42
    with pytest.raises(ValueError,match='reconstruction'):
        sim.reconstruct_case(changed)


def test_no_response_can_select_a_gain_without_minimum_exploration():
    with pytest.raises(ValueError,match='exploration'):
        allocation.fit_profile(allocation.catalogue(),())
    always_unknown=sim.VirtualReceiver((1.0,)*6,noise_std=0,lapse_probability=1)
    fit=sim.calibrate(always_unknown,999,'stable',78,'uniform')
    assert fit['frozen_profile']==TactileProfile().to_dict()  # Equal data, declared default tie.


def test_gain_probe_cannot_remap_meanings_and_receiver_is_order_independent():
    default=TactileProfile()
    for candidate in allocation.catalogue().profiles:
        assert candidate.spec==default.spec and candidate.patterns==default.patterns
        assert candidate.intensities==default.intensities
        assert (candidate.pulse_ms,candidate.gap_ms)==(150,150)
    keys=[sim._key(999,'localized','calibration',0,1,0,n) for n in range(5)]
    model=sim.receiver(999,'localized')
    command=default.render(default.spec.code(0,1))
    forward=[model.respond(command,sim._rng(k)) for k in keys]
    backward=[model.respond(command,sim._rng(k)) for k in reversed(keys)]
    assert forward==backward[::-1]
