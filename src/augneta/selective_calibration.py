"""Pure allocation/fitting over public calibration history. No receiver or RNG.

This module deliberately imports no simulation/evaluator module. Frozen value
objects form its complete input; no latent model or callback is accepted.
"""

from dataclasses import asdict, dataclass, replace
from fractions import Fraction
import math

from .tactile import CodeSpec, TactileProfile, number

SPEC = CodeSpec()
CATCH_EVERY = 13


@dataclass(frozen=True, slots=True)
class Response:
    kind: str
    direction: int | None
    level: int | None

    def __post_init__(self):
        if self.kind == "unknown":
            if self.direction is not None or self.level is not None:
                raise ValueError("unknown response cannot include a guess")
        elif self.kind in ("identified", "zero"):
            SPEC.code(self.direction, self.level)
            if (self.kind == "zero") != (self.level == 0):
                raise ValueError("zero and identified must remain distinct")
        else:
            raise ValueError("unknown response kind")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Query:
    direction: int | None
    level: int
    candidate: int

    def __post_init__(self):
        SPEC.code(self.direction, self.level)
        if type(self.candidate) is not int or not 0 <= self.candidate < 3:
            raise ValueError("candidate index must be 0..2")
        if self.level == 0 and self.candidate != 0:
            raise ValueError("catch trials use the default candidate")

    @property
    def code(self):
        return SPEC.code(self.direction, self.level)


@dataclass(frozen=True, slots=True)
class Observation:
    query: Query
    command: tuple
    response: Response

    def __post_init__(self):
        if type(self.query) is not Query or type(self.response) is not Response:
            raise ValueError("history needs typed query/response values")
        if type(self.command) is not tuple or len(self.command) != 6 or not all(number(v, 0, 1) for v in self.command):
            raise ValueError("history needs six finite command values")


@dataclass(frozen=True, slots=True)
class Catalogue:
    profiles: tuple

    def __post_init__(self):
        base = TactileProfile()
        if type(self.profiles) is not tuple or len(self.profiles) != 3:
            raise ValueError("three immutable probe profiles required")
        for profile, gain in zip(self.profiles, (1.0, 0.75, 0.5)):
            if type(profile) is not TactileProfile or profile != replace(base, gains=(gain,) * 6):
                raise ValueError("v1 catalogue must preserve fixed semantics, timing and gains")


def catalogue():
    return Catalogue(tuple(replace(TactileProfile(), gains=(gain,) * 6) for gain in (1.0, 0.75, 0.5)))


def correct(code, response):
    return response.kind != "unknown" and (response.direction, response.level) == (code["direction"], code["level"])


def _counts(candidates, history):
    if type(candidates) is not Catalogue or type(history) is not tuple:
        raise ValueError("only catalogue and immutable observation history are accepted")
    n = [[[0, 0] for _ in range(3)] for _ in range(6)]
    hits = [[[0, 0] for _ in range(3)] for _ in range(6)]
    for i, obs in enumerate(history):
        if type(obs) is not Observation:
            raise ValueError("unexpected history capability/fields")
        q = obs.query
        if (q.level == 0) != ((i + 1) % CATCH_EVERY == 0):
            raise ValueError("catch schedule mismatch")
        profile = candidates.profiles[q.candidate]
        expected = tuple(0.0 if q.direction is None else
                         profile.patterns[q.direction][j] * profile.gains[j] * profile.intensities[q.level]
                         for j in range(6))
        if obs.command != expected:
            raise ValueError("issued label/command mismatch")
        if q.level:
            n[q.direction][q.candidate][q.level - 1] += 1
            hits[q.direction][q.candidate][q.level - 1] += correct(q.code, obs.response)
    return n, hits


def _error(n, hits):
    # Mean over levels, not a count-weighted score that could ignore one level.
    return sum(Fraction(count - hit + 1, count + 2) for count, hit in zip(n, hits)) / 2


def choose_query(candidates, history, remaining_budget, method):
    if type(remaining_budget) is not int or remaining_budget <= 0:
        raise ValueError("no response budget remains")
    if method not in ("uniform", "selective"):
        raise ValueError("unsupported allocation method")
    n, hits = _counts(candidates, history)
    if (len(history) + 1) % CATCH_EVERY == 0:
        return Query(None, 0, 0)
    nonzero = len(history) - len(history) // CATCH_EVERY
    if method == "uniform" or nonzero < 36:
        index = nonzero % 36
        return Query(index // 6, index % 2 + 1, (index % 6) // 2)
    totals = [sum(sum(levels) for levels in direction) for direction in n]
    direction = max(range(6), key=lambda d: (_error(n[d][0], hits[d][0]) / math.sqrt(totals[d]), -d))
    candidate = min(range(3), key=lambda g: (sum(n[direction][g]), g))
    level = min(range(2), key=lambda lev: (n[direction][candidate][lev], lev)) + 1
    return Query(direction, level, candidate)


def fit_profile(candidates, history):
    n, hits = _counts(candidates, history)
    if any(count == 0 for direction in n for levels in direction for count in levels):
        raise ValueError("minimum exploration incomplete; cannot freeze a fitted profile")
    choices = [min(range(3), key=lambda g: (_error(n[d][g], hits[d][g]), g)) for d in range(6)]
    return replace(candidates.profiles[0], gains=tuple(candidates.profiles[g].gains[d] for d, g in enumerate(choices)))
