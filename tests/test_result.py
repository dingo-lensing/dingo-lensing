import dingo.gw.result as dingo_gw_result
import numpy as np
import pandas as pd
import pytest
from bilby.core.prior import Constraint, DeltaFunction, PriorDict, Uniform
from dingo.gw.result import Result as DingoGWResult

from dingo_lensing import interpolation
from dingo_lensing.result import LensedGWResult

TYPE_II = np.pi / 2
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


def result_with_prior(monkeypatch, priors, samples):
    def build_prior(self):
        self.prior = PriorDict(dict(priors))
        self.geocent_time_prior = None
        self.phase_prior = None

    monkeypatch.setattr(DingoGWResult, "_build_prior", build_prior)
    result = object.__new__(LensedGWResult)
    result.samples = pd.DataFrame(samples)
    result.importance_sampling_metadata = {}
    result.log_evidence = None
    result._build_prior()
    return result


def test_unsampled_lens_parameter_is_split_off(monkeypatch):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "mass_1": Constraint(5, 150),
        "Delta_phase": Uniform(0, np.pi),
    }
    samples = {"chirp_mass": np.linspace(20, 40, 5)}
    result = result_with_prior(monkeypatch, priors, samples)
    assert "Delta_phase" not in result.prior
    assert "mass_1" in result.prior
    assert result.unsampled_priors == {"Delta_phase": Uniform(0, np.pi)}
    assert "Delta_phase" not in result.samples


def test_sampled_lens_parameter_is_kept(monkeypatch):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "Delta_phase": Uniform(0, np.pi),
    }
    samples = {
        "chirp_mass": np.linspace(20, 40, 5),
        "Delta_phase": np.full(5, 1.0),
    }
    result = result_with_prior(monkeypatch, priors, samples)
    assert "Delta_phase" in result.prior
    assert result.unsampled_priors == {}
    np.testing.assert_array_equal(result.samples["Delta_phase"], 1.0)


def test_fixed_lens_parameter_is_added_to_samples(monkeypatch):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "Delta_phase": DeltaFunction(TYPE_II),
    }
    samples = {"chirp_mass": np.linspace(20, 40, 5)}
    result = result_with_prior(monkeypatch, priors, samples)
    assert isinstance(result.prior["Delta_phase"], DeltaFunction)
    assert result.unsampled_priors == {}
    np.testing.assert_array_equal(result.samples["Delta_phase"], TYPE_II)


@pytest.mark.parametrize("value", [str(TYPE_II), TYPE_II])
def test_hypothesis_fixes_lens_parameter(monkeypatch, value):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "Delta_phase": Uniform(0, np.pi),
    }
    samples = {"chirp_mass": np.linspace(20, 40, 5)}
    result = result_with_prior(monkeypatch, priors, samples)
    result.update_prior({"Delta_phase": value})
    assert result.unsampled_priors == {}
    assert isinstance(result.prior["Delta_phase"], DeltaFunction)
    np.testing.assert_array_equal(result.samples["Delta_phase"], TYPE_II)
    np.testing.assert_allclose(result.samples["weights"], 1.0)
    assert result.importance_sampling_metadata["prior_update"] == {
        "Delta_phase": value
    }


def test_hypothesis_must_be_one_value(monkeypatch):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "Delta_phase": Uniform(0, np.pi),
    }
    samples = {"chirp_mass": np.linspace(20, 40, 5)}
    result = result_with_prior(monkeypatch, priors, samples)
    update = {"Delta_phase": "bilby.core.prior.Uniform(minimum=0, maximum=1)"}
    with pytest.raises(ValueError, match="Delta_phase is not sampled"):
        result.update_prior(update)
    assert result.importance_sampling_metadata == {}


def test_likelihood_needs_hypothesis(monkeypatch):
    priors = {
        "chirp_mass": Uniform(10, 100),
        "Delta_phase": Uniform(0, np.pi),
    }
    samples = {"chirp_mass": np.linspace(20, 40, 5)}
    result = result_with_prior(monkeypatch, priors, samples)
    with pytest.raises(ValueError, match="Not sampled: Delta_phase"):
        result._build_likelihood()
