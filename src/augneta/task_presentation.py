"""Six-slot software presentation. Only causal belief enters the scheduler."""

from copy import deepcopy
import math

from .estimation import Belief
from .tactile import CodeSpec, TactileProfile

CONDITIONS = ('six_slot_dashboard', 'six_slot_preview')
ENCODER_ID = 'six-slot-belief-v1'
SCHEDULER_ID = 'six-slot-pulse-v1'
CANDIDATE_STATUS = 'unvalidated_hardware_candidate'


def export_candidate(profile, participant_kind):
    if participant_kind not in ('developer', 'synthetic'):
        raise ValueError('candidate requires development provenance')
    return {'schema_version': 1, 'kind': 'tactile_candidate',
            'profile': profile.to_dict(), 'profile_sha256': profile.identity,
            'code_id': profile.spec.identity, 'profile_status': CANDIDATE_STATUS,
            'participant_kind': participant_kind, 'human_evidence': False,
            'hardware_verified': False, 'output_mode': 'software_only'}


def import_candidate(data, *, for_task=True):
    if not isinstance(data, dict) or set(data) != set(export_candidate(TactileProfile(), 'developer')):
        raise ValueError('versioned candidate envelope required; re-export hashless profiles in calibration rehearsal')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != 'tactile_candidate':
        raise ValueError('unsupported candidate format')
    profile = TactileProfile.from_dict(data['profile'])
    if (data['hardware_verified'] is not False or data['human_evidence'] is not False
            or data != export_candidate(profile, data['participant_kind'])):
        raise ValueError('candidate hash, meaning or software evidence labels mismatch')
    if for_task and profile.spec != CodeSpec():
        raise ValueError('task rehearsal requires the nominal six-direction, two-level code and magnitude scale')
    return profile


class SixSlotSchedule:
    """Tick-based sample-and-hold; no wall clock, task, target or model access."""

    def __init__(self, profile, dt_s):
        self.profile = profile
        self.dt_s = dt_s
        self.pulse_steps = math.ceil(profile.pulse_ms / (1000 * dt_s) - 1e-9)
        self.gap_steps = math.ceil(profile.gap_ms / (1000 * dt_s) - 1e-9)
        self.anchor = 0
        self.epoch = 0
        self.lifecycle = 'running'
        self.cycle = None
        self.latched = None

    def contract(self):
        return {'encoder_id': ENCODER_ID, 'scheduler_id': SCHEDULER_ID,
                'code_id': self.profile.spec.identity, 'profile_sha256': self.profile.identity,
                'profile_status': CANDIDATE_STATUS, 'dt_s': self.dt_s,
                'pulse_steps': self.pulse_steps, 'gap_steps': self.gap_steps,
                'stale_after_s': 0.5, 'status_channel': 'shared_visual_only',
                'hardware_verified': False, 'human_evidence': False}

    def transition(self, action, step, expected_epoch=None):
        if action not in ('pause', 'resume', 'stop'):
            raise ValueError('unsupported lifecycle action')
        if self.lifecycle in ('complete', 'stopped'):
            raise ValueError('trial presentation already terminal')
        if action != 'stop' and (type(expected_epoch) is not int or expected_epoch != self.epoch):
            raise ValueError('stale presentation epoch')
        if (action == 'pause' and self.lifecycle != 'running') or (action == 'resume' and self.lifecycle != 'paused'):
            raise ValueError('invalid lifecycle transition')
        self.epoch += 1
        self.lifecycle = {'pause': 'paused', 'resume': 'running', 'stop': 'stopped'}[action]
        self.anchor = step
        self.cycle = self.latched = None

    def packet(self, belief, *, complete=False):
        if type(belief) is not Belief:
            raise ValueError('presentation accepts causal Belief only')
        if complete:
            self.lifecycle = 'complete'
        step = belief.now_step
        cycle, offset = divmod(max(0, step - self.anchor), self.pulse_steps + self.gap_steps)
        packet = {**self.contract(), 'step': step, 'epoch': self.epoch, 'cycle': cycle,
                  'phase': self.lifecycle, 'remaining_pulse_ms': 0, 'payload': None}
        if self.lifecycle != 'running':
            return packet
        if cycle != self.cycle:
            # First tick of a cycle is the only sample visible in either view.
            self.cycle = cycle
            age = None if belief.last_sample_step is None else step - belief.last_sample_step
            stale = age is None or age * self.dt_s > 0.5 + 1e-12
            reason = 'waiting' if age is None else 'dropout' if belief.dropped else 'stale' if stale else None
            status = {'uncertainty_level': min(8, int(math.floor(math.sqrt(belief.variance) / .25 + .5))),
                      'age_steps': age, 'last_sample_step': belief.last_sample_step,
                      'sensor_status': belief.sensor_status, 'dropped': belief.dropped,
                      'stale': stale, 'delayed': age is not None and age > 0,
                      'emitted_step': step, 'estimator_id': belief.estimator_id}
            code = self.profile.spec.encode(belief)
            preview = self.profile.matched_preview(code)
            self.latched = {'status': status, 'suppression': reason,
                            'semantic_state': None if reason else code,
                            'visual': None if reason else preview['visual'],
                            'command': self.profile.render(self.profile.spec.code(None, 0)) if reason else preview['command']}
        if offset < self.pulse_steps:
            packet.update(phase='pulse', remaining_pulse_ms=min(self.profile.pulse_ms,
                          (self.pulse_steps - offset) * self.dt_s * 1000), payload=deepcopy(self.latched))
        else:
            packet['phase'] = 'gap'
        return packet
