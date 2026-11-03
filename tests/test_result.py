import dingo.gw.result as dingo_gw_result
import pytest
from dingo.gw.result import Result as DingoGWResult

from dingo_lensing import interpolation
from dingo_lensing.result import LensedGWResult

NAMES = [
    "interpolated_sample_and_log_prob_multi",
    "interpolated_log_prob_multi",
]


def current_draws():
    return [getattr(dingo_gw_result, name) for name in NAMES]


def test_synthetic_phase_uses_independent_draws(monkeypatch):
    used = []

    def sample(self, synthetic_phase_kwargs, inverse=False):
        used.append((current_draws(), inverse))

    originals = current_draws()
    monkeypatch.setattr(DingoGWResult, "sample_synthetic_phase", sample)
    result = object.__new__(LensedGWResult)
    result.sample_synthetic_phase({"n_grid": 11})
    result.sample_synthetic_phase({"n_grid": 11}, inverse=True)
    expected = [getattr(interpolation, name) for name in NAMES]
    assert used == [(expected, False), (expected, True)]
    assert current_draws() == originals


def test_draws_restored_after_error(monkeypatch):
    def sample(self, synthetic_phase_kwargs, inverse=False):
        raise RuntimeError("synthetic phase failed")

    originals = current_draws()
    monkeypatch.setattr(DingoGWResult, "sample_synthetic_phase", sample)
    result = object.__new__(LensedGWResult)
    with pytest.raises(RuntimeError):
        result.sample_synthetic_phase({"n_grid": 11})
    assert current_draws() == originals
