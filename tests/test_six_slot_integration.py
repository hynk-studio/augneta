from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from augneta.config import Config, canonical
from augneta.estimation import Belief
from augneta.experiment import Trial, ChangeEvent
from augneta.recording import Recorder, replay
from augneta.tactile import CodeSpec, TactileProfile
from augneta.task_presentation import CONDITIONS, SixSlotSchedule, export_candidate, import_candidate
from augneta.web import create_app


@pytest.fixture
def candidate():
    return export_candidate(replace(TactileProfile(), gains=(.5,.75,1,.5,.75,1)), 'synthetic')


@pytest.fixture
def short_config():
    return Config(steps=40, evaluation_start_step=5, evaluation_end_step=40, sensor_dropout_probability=0)


def belief(step=0, **kwargs):
    return replace(Belief(step, (.7,.5), .09, step, 'fresh', False, 0, 'rw-kalman-v1'), **kwargs)


def test_candidate_roundtrip_freeze_and_gain_meaning(candidate, short_config):
    profile = import_candidate(candidate)
    trial = Trial(short_config, CONDITIONS[0], candidate=candidate)
    candidate['profile']['gains'][0] = 1
    assert trial.candidate['profile']['gains'][0] == .5
    with pytest.raises(FrozenInstanceError):
        trial.presentation.profile.gains = (1,)*6
    code = profile.spec.code(0, 2)
    base = TactileProfile().matched_preview(code)
    calibrated = profile.matched_preview(code)
    assert calibrated['visual'] == base['visual']
    assert calibrated['command']['left'][0] == .5 * base['command']['left'][0]
    with pytest.raises(ValueError, match='freezes'):
        Trial(short_config, CONDITIONS[0], candidate=trial.candidate,
              changes=[ChangeEvent(3, 'estimator', 'rw-kalman-v2')])
    with pytest.raises(ValueError, match='explicit'):
        Trial(short_config, 'dashboard', candidate=trial.candidate)


@pytest.mark.parametrize('mutation', ['hash', 'code', 'gain', 'evidence', 'kind', 'missing', 'extra', 'incompatible'])
def test_invalid_imports(candidate, mutation):
    if mutation == 'hash': candidate['profile_sha256'] = 'bad'
    if mutation == 'code': candidate['code_id'] = 'polar8-v1'
    if mutation == 'gain': candidate['profile']['gains'][0] = .6
    if mutation == 'evidence': candidate['hardware_verified'] = True
    if mutation == 'kind': candidate['kind'] = 'calibration_simulation'
    if mutation == 'missing': del candidate['profile_sha256']
    if mutation == 'extra': candidate['latent_model'] = {}
    if mutation == 'incompatible':
        candidate = export_candidate(replace(TactileProfile(), spec=CodeSpec(max_magnitude=2)), 'synthetic')
    with pytest.raises(ValueError): import_candidate(candidate)


def test_scheduler_boundary_matching_hold_gap_and_no_task_inputs(candidate):
    profile = import_candidate(candidate)
    a, b = SixSlotSchedule(profile, .02), SixSlotSchedule(profile, .02)
    assert list(inspect.signature(a.packet).parameters) == ['belief','complete']
    for step in range(40):
        observation = belief(step, mean=(.7 if step % 2 else -.7, .5))
        pa, pb = a.packet(observation), b.packet(observation)
        assert pa == pb
        if step % 16 < 8:
            assert pa['phase'] == 'pulse'
            assert pa['payload']['status']['emitted_step'] == step // 16 * 16
            assert pa['payload']['semantic_state']['direction'] == 2
        else:
            assert pa['phase'] == 'gap' and pa['payload'] is None
            assert pa['remaining_pulse_ms'] == 0
    with pytest.raises(ValueError, match='Belief'):
        a.packet({'mean': [.7,.5], 'target':[1,0], 'truth':[1,1]})


@pytest.mark.parametrize('changes,reason', [({'last_sample_step':None},'waiting'),
    ({'dropped':True,'sensor_status':'dropout'},'dropout'), ({'last_sample_step':0},'stale')])
def test_shared_suppression_and_latched_status(changes, reason):
    schedule = SixSlotSchedule(TactileProfile(), .05)
    packet = schedule.packet(belief(12, **changes))
    assert packet['payload']['suppression'] == reason
    assert packet['payload']['visual'] is None and packet['payload']['semantic_state'] is None
    assert packet['payload']['command']['left'] + packet['payload']['command']['right'] == [0]*6
    held = schedule.packet(belief(13))
    assert held['payload'] == packet['payload']
    assert schedule.packet(belief(15))['payload'] is None


@pytest.mark.parametrize('task', ['tracking','safe_zone'])
def test_equal_packets_for_views_and_direct_actions(task, candidate, short_config):
    cfg = replace(short_config, task=task)
    trials = [Trial(cfg, c, candidate=candidate) for c in CONDITIONS]
    for step in range(cfg.steps):
        assert trials[0].view()['feedback'] == trials[1].view()['feedback']
        for t in trials:
            record, _ = t.advance((.25,-.5))
            assert record['action'] == record['applied_action'] == [.25,-.5]
            assert record['feedback_packet']['encoder_id'] != 'polar8-v1'
    assert all(t.view()['feedback']['phase']=='complete' and t.view()['feedback']['payload'] is None for t in trials)


def test_same_flow_meaning_between_tasks(candidate, short_config):
    trials = [Trial(replace(short_config, task=task), CONDITIONS[0], candidate=candidate) for task in ('tracking','safe_zone')]
    for _ in range(short_config.steps):
        assert trials[0].view()['feedback'] == trials[1].view()['feedback']
        trials[0].advance((.5,0)); trials[1].advance((0,-.5))


@pytest.mark.parametrize('task', ['tracking','safe_zone'])
@pytest.mark.parametrize('condition', CONDITIONS)
@pytest.mark.parametrize('finish', [True,False])
def test_api_lifecycle_complete_partial_and_replay(tmp_path, candidate, short_config, task, condition, finish):
    app = create_app(tmp_path, participant_kind='synthetic', config=short_config)
    client = app.test_client()
    response = client.post('/api/trials', json={'task':task,'condition':condition,'candidate':candidate})
    assert response.status_code == 200
    view = response.json
    def step(v):
        return client.post('/api/step', json={'trial_id':v['trial_id'],'expected_step':v['visible']['step'],
            'presentation_epoch':v['feedback']['epoch'],'action':[1,0]})
    view = step(view).json
    previous = deepcopy(view)
    response = client.post('/api/presentation-lifecycle', json={'trial_id':view['trial_id'], 'action':'pause','expected_epoch':0})
    assert response.status_code == 200
    view = response.json
    assert view['feedback']['phase']=='paused' and view['feedback']['payload'] is None
    assert step(previous).status_code == 400
    assert step(view).status_code == 400
    response = client.post('/api/presentation-lifecycle', json={'trial_id':view['trial_id'], 'action':'resume','expected_epoch':1})
    view = response.json
    assert view['feedback']['epoch']==2
    assert view['feedback']['payload']['status']['emitted_step']==view['visible']['step']
    if finish:
        while not view['complete']:
            result = step(view); assert result.status_code == 200
            view = result.json
    else:
        view = step(view).json
    stopped = client.post('/api/stop', json={'trial_id':view['trial_id']})
    assert stopped.status_code==200
    result = replay(view['recording'])
    assert result['replay_verified']
    assert (result['status']=='complete') == finish
    if not finish:
        assert result['normalized_tracking_rmse' if task=='tracking' else 'normalized_outside_distance'] is None
    assert step(view).status_code==400
    meta=json.loads((Path(view['recording'])/'metadata.json').read_text())
    assert meta['candidate']==candidate and meta['schema_version']==2
    assert meta['response_provenance']=='synthetic'
    assert meta['presentation']['status_channel']=='shared_visual_only'
    host=[json.loads(x) for x in (Path(view['recording'])/'transport.jsonl').read_text().splitlines()]
    assert all(r['browser_render_ms'] is None and r['measured_onset_ms'] is None for r in host)


def test_replay_rejects_packet_and_lifecycle_tampering(tmp_path, candidate, short_config):
    trial=Trial(short_config, CONDITIONS[0], candidate=candidate)
    recorder=Recorder(tmp_path/'run',trial,participant_kind='synthetic')
    recorder.append(*trial.advance((0,0)))
    recorder.transition(trial,'pause',0)
    recorder.finish(trial)
    assert replay(recorder.directory)['replay_verified']
    path=recorder.directory/'lifecycle.jsonl';original=path.read_text()
    lines=[json.loads(x) for x in original.splitlines()]
    lines[0]['packet']['epoch']=99
    path.write_text('\n'.join(map(canonical,lines)))
    with pytest.raises(ValueError, match='lifecycle'): replay(recorder.directory)
    path.write_text(original)
    path=recorder.directory/'trace.jsonl';record=json.loads(path.read_text())
    record['presentation_after']['payload']['command']['left'][0]=.123
    path.write_text(canonical(record)+'\n')
    with pytest.raises(ValueError, match='mismatch'): replay(recorder.directory)


def test_invalid_import_does_not_replace_active_trial(tmp_path, candidate, short_config):
    client=create_app(tmp_path,config=short_config).test_client()
    old=client.post('/api/trials',json={}).json
    broken=deepcopy(candidate);broken['profile_sha256']='bad'
    assert client.post('/api/trials',json={'condition':CONDITIONS[0],'candidate':broken}).status_code==400
    assert client.post('/api/trials',json={'condition':CONDITIONS[0]}).status_code==400
    assert client.post('/api/step',json={'trial_id':old['trial_id'],'expected_step':0,'action':[0,0]}).status_code==200
    exported=client.post('/api/candidate-profile',json={'profile':candidate['profile']}).json
    assert exported['participant_kind']=='developer'
    assert client.post('/api/candidate-import',json={'candidate':exported}).status_code==200
    client.post('/api/stop',json={'trial_id':old['trial_id']})


def test_legacy_trace_truth_and_summary_equal_pr5_snapshot():
    frozen=json.loads((Path(__file__).parent/'fixtures/legacy-pr5-baseline.json').read_text())
    for row in frozen['rows']:
        t=Trial(Config.from_dict(row['config']),row['condition'])
        outputs=[]
        for k in range(t.config.steps): outputs.append(t.advance((.25 if k%3 else -.5,.1)))
        assert hashlib.sha256(canonical(outputs).encode()).hexdigest()==row['trace_truth_sha256']
        assert t.summary()==row['summary']


def test_pending_start_cancel_before_and_after_creation(tmp_path, candidate, short_config):
    import uuid
    client=create_app(tmp_path,participant_kind='synthetic',config=short_config).test_client()
    identifier=str(uuid.uuid4())
    assert client.post('/api/cancel-start',json={'start_id':identifier}).status_code==200
    assert client.post('/api/trials',json={'condition':CONDITIONS[0],'candidate':candidate,'start_id':identifier}).status_code==400
    identifier=str(uuid.uuid4())
    request={'condition':CONDITIONS[0],'candidate':candidate,'start_id':identifier}
    response=client.post('/api/trials',json=request)
    assert response.status_code==200 and response.json['trial_id']==identifier
    assert client.post('/api/trials',json=request).status_code==400
    assert client.post('/api/cancel-start',json={'start_id':identifier}).status_code==200
    result=replay(response.json['recording'])
    assert result['steps']==0 and result['status']=='incomplete_or_invalid'
    assert client.post('/api/step',json={'trial_id':identifier,'expected_step':0,'presentation_epoch':0,'action':[0,0]}).status_code==400


def test_profile_override_and_stale_lifecycle_rejected(tmp_path, candidate, short_config):
    client=create_app(tmp_path,participant_kind='synthetic',config=short_config).test_client()
    v=client.post('/api/trials',json={'condition':CONDITIONS[0],'candidate':candidate}).json
    assert client.post('/api/step',json={'trial_id':v['trial_id'],'expected_step':0,'presentation_epoch':0,'action':[0,0],'candidate':candidate}).status_code==400
    request={'trial_id':v['trial_id'],'action':'pause','expected_epoch':0}
    assert client.post('/api/presentation-lifecycle',json=request).status_code==200
    assert client.post('/api/presentation-lifecycle',json=request).status_code==400
    request['action']='resume'
    assert client.post('/api/presentation-lifecycle',json=request).status_code==400
    client.post('/api/stop',json={'trial_id':v['trial_id']})
    assert replay(v['recording'])['steps']==0


def test_completion_overtakes_pause_without_reviving_output(tmp_path, candidate):
    config=Config(steps=1,evaluation_start_step=0,evaluation_end_step=1,sensor_delay_steps=0)
    client=create_app(tmp_path,participant_kind='synthetic',config=config).test_client()
    v=client.post('/api/trials',json={'condition':CONDITIONS[0],'candidate':candidate}).json
    complete=client.post('/api/step',json={'trial_id':v['trial_id'],'expected_step':0,'presentation_epoch':0,'action':[0,0]}).json
    paused=client.post('/api/presentation-lifecycle',json={'trial_id':v['trial_id'],'action':'pause','expected_epoch':0})
    assert paused.status_code==200 and paused.json['feedback']['phase']=='complete'
    assert paused.json['feedback']['payload'] is None and paused.json['summary']==complete['summary']
    assert replay(v['recording'])['status']=='complete'
