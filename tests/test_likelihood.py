from types import SimpleNamespace

import numpy as np
import pytest
from dingo.gw.likelihood import StationaryGaussianGWLikelihood, inner_product

from dingo_lensing.likelihood import StationaryGaussianLensedGWLikelihood

IFOS = ["H1", "L1"]
N_BINS = 300
MIN_IDX = 20


def stub_likelihood(seed=0):
    rng = np.random.default_rng(seed)

    def noise():
        return rng.normal(size=N_BINS) + 1j * rng.normal(size=N_BINS)

    modes = {
        m: {"waveform": {ifo: 0.3 * noise() for ifo in IFOS}}
        for m in range(-4, 5)
    }
    likelihood = object.__new__(StationaryGaussianLensedGWLikelihood)
    likelihood.phase_marginalization = False
    likelihood.time_marginalization = False
    likelihood.waveform_generator = SimpleNamespace(spin_conversion_phase=0.0)
    likelihood.data_domain = SimpleNamespace(min_idx=MIN_IDX)
    likelihood.log_Zn = -1234.5
    likelihood.whitened_strains = {ifo: noise() for ifo in IFOS}
    likelihood.phase_grid = np.linspace(0, 2 * np.pi, 5001)
    likelihood.signal_m = lambda theta: modes
    return likelihood, modes


def test_phase_grid_matches_dingo():
    likelihood, _ = stub_likelihood()
    dingo_grid = (
        StationaryGaussianGWLikelihood._log_likelihood_phase_grid_mode_decomposed
    )
    expected = dingo_grid(likelihood, {})
    result = likelihood._log_likelihood_phase_grid_mode_decomposed({})
    assert result.shape == expected.shape
    np.testing.assert_allclose(result, expected, rtol=1e-12, atol=1e-9)


def test_phase_grid_matches_direct_likelihood():
    likelihood, modes = stub_likelihood(seed=1)
    phases = np.array([0.0, 0.4, 1.3, 2.9, 5.5])
    result = likelihood._log_likelihood_phase_grid_mode_decomposed(
        {}, phases=phases
    )
    d = likelihood.whitened_strains
    for phase, log_l in zip(phases, result):
        mu = {
            ifo: sum(
                pol["waveform"][ifo] * np.exp(-1j * m * phase)
                for m, pol in modes.items()
            )
            for ifo in IFOS
        }
        kappa2 = sum(inner_product(d[ifo], mu[ifo], MIN_IDX) for ifo in IFOS)
        rho2opt = sum(inner_product(mu[ifo], mu[ifo], MIN_IDX) for ifo in IFOS)
        expected = likelihood.log_Zn + kappa2 - rho2opt / 2
        assert log_l == pytest.approx(expected, rel=1e-12)


def test_phase_grid_rejects_unsupported_settings():
    likelihood, _ = stub_likelihood()
    likelihood.phase_marginalization = True
    with pytest.raises(ValueError, match="phase-marginalized"):
        likelihood._log_likelihood_phase_grid_mode_decomposed({})
    likelihood.phase_marginalization = False
    likelihood.time_marginalization = True
    with pytest.raises(NotImplementedError):
        likelihood._log_likelihood_phase_grid_mode_decomposed({})
    likelihood.time_marginalization = False
    likelihood.waveform_generator.spin_conversion_phase = 0.5
    with pytest.raises(ValueError, match="spin_conversion_phase"):
        likelihood._log_likelihood_phase_grid_mode_decomposed({})
